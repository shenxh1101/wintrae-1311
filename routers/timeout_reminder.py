from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import (
    Appointment,
    AppointmentStatus,
    ExceptionType,
    ExceptionRecord,
    TimeoutReminderConfig,
    TimeoutReminderLog,
    TimeoutReminderLevel,
)
from schemas import (
    TimeoutReminderConfigCreate,
    TimeoutReminderConfigUpdate,
    TimeoutReminderConfigResponse,
    TimeoutReminderLogResponse,
    TimeoutReminderScanResponse,
    MessageResponse,
)

router = APIRouter(prefix="/api/timeout-reminders", tags=["超时提醒"])

REMINDER_LEVEL_LABELS = {
    TimeoutReminderLevel.FRONT_DESK: "前台提醒",
    TimeoutReminderLevel.SECURITY_SUPERVISOR: "安保主管提醒",
    TimeoutReminderLevel.ADMIN: "管理员提醒",
}


def _init_default_configs(db: Session):
    existing = db.query(TimeoutReminderConfig).count()
    if existing == 0:
        defaults = [
            TimeoutReminderConfig(
                name="超时30分钟提醒前台",
                timeout_minutes=30,
                reminder_level=TimeoutReminderLevel.FRONT_DESK,
                recipient_name="前台值班员",
                is_enabled=True,
            ),
            TimeoutReminderConfig(
                name="超时2小时提醒安保主管",
                timeout_minutes=120,
                reminder_level=TimeoutReminderLevel.SECURITY_SUPERVISOR,
                recipient_name="安保主管",
                recipient_phone="13800138000",
                is_enabled=True,
            ),
        ]
        db.add_all(defaults)
        db.commit()


@router.post("/configs", response_model=TimeoutReminderConfigResponse, summary="创建超时提醒配置")
def create_config(data: TimeoutReminderConfigCreate, db: Session = Depends(get_db)):
    existing = db.query(TimeoutReminderConfig).filter(TimeoutReminderConfig.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="配置名称已存在")

    config = TimeoutReminderConfig(**data.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/configs", response_model=list[TimeoutReminderConfigResponse], summary="查询超时提醒配置列表")
def list_configs(
    is_enabled: bool = Query(None, description="是否启用"),
    reminder_level: TimeoutReminderLevel = Query(None, description="提醒级别"),
    db: Session = Depends(get_db),
):
    _init_default_configs(db)

    query = db.query(TimeoutReminderConfig)
    if is_enabled is not None:
        query = query.filter(TimeoutReminderConfig.is_enabled == is_enabled)
    if reminder_level:
        query = query.filter(TimeoutReminderConfig.reminder_level == reminder_level)

    return query.order_by(TimeoutReminderConfig.timeout_minutes.asc()).all()


@router.get("/configs/{config_id}", response_model=TimeoutReminderConfigResponse, summary="查询单个配置")
def get_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(TimeoutReminderConfig).filter(TimeoutReminderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config


@router.put("/configs/{config_id}", response_model=TimeoutReminderConfigResponse, summary="更新超时提醒配置")
def update_config(config_id: int, data: TimeoutReminderConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(TimeoutReminderConfig).filter(TimeoutReminderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return config


@router.delete("/configs/{config_id}", response_model=MessageResponse, summary="删除超时提醒配置")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(TimeoutReminderConfig).filter(TimeoutReminderConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    db.delete(config)
    db.commit()
    return MessageResponse(success=True, message="配置已删除")


@router.get("/scan", response_model=TimeoutReminderScanResponse, summary="扫描超时并触发提醒")
def scan_and_trigger_reminders(
    visit_date: str = Query(None, description="扫描日期(YYYY-MM-DD)，默认今日"),
    db: Session = Depends(get_db),
):
    _init_default_configs(db)

    if not visit_date:
        visit_date = date.today().isoformat()

    timeout_exceptions = db.query(ExceptionRecord).filter(
        ExceptionRecord.exception_type == ExceptionType.NOT_CHECKED_OUT_TIMEOUT,
        ExceptionRecord.visit_date == visit_date,
    ).all()

    scanned_count = len(timeout_exceptions)
    new_reminders = 0
    already_reminded = 0
    reminder_log_ids = []

    now = datetime.now()

    for exc in timeout_exceptions:
        if not exc.appointment_id:
            continue

        apt = db.query(Appointment).filter(Appointment.id == exc.appointment_id).first()
        if not apt or not apt.visit_time_end:
            continue

        try:
            end_time = datetime.strptime(f"{apt.visit_date} {apt.visit_time_end}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        elapsed_minutes = int((now - end_time).total_seconds() / 60)
        if elapsed_minutes <= 0:
            continue

        configs = db.query(TimeoutReminderConfig).filter(
            TimeoutReminderConfig.is_enabled == True,
            TimeoutReminderConfig.timeout_minutes <= elapsed_minutes,
        ).order_by(TimeoutReminderConfig.timeout_minutes.asc()).all()

        for config in configs:
            existing_log = db.query(TimeoutReminderLog).filter(
                TimeoutReminderLog.exception_record_id == exc.id,
                TimeoutReminderLog.config_id == config.id,
            ).first()

            if existing_log:
                already_reminded += 1
                continue

            level_label = REMINDER_LEVEL_LABELS.get(config.reminder_level, config.reminder_level.value)
            message = (
                f"【{level_label}】访客 {exc.visitor_name}（证件后四位 {exc.id_last_four}）"
                f"已超时 {elapsed_minutes} 分钟未离园，预约结束时间：{apt.visit_time_end}，"
                f"来访对象：{apt.target_employee_name}，楼栋：{apt.target_building or '未指定'}"
            )

            log = TimeoutReminderLog(
                exception_record_id=exc.id,
                appointment_id=apt.id,
                visitor_name=exc.visitor_name,
                id_last_four=exc.id_last_four,
                config_id=config.id,
                config_name=config.name,
                timeout_minutes=elapsed_minutes,
                reminder_level=config.reminder_level,
                recipient_name=config.recipient_name,
                recipient_phone=config.recipient_phone,
                message=message,
                is_sent=True,
            )
            db.add(log)
            new_reminders += 1
            reminder_log_ids.append(log.id)

    db.commit()

    return TimeoutReminderScanResponse(
        scanned_count=scanned_count,
        new_reminders=new_reminders,
        already_reminded=already_reminded,
        reminder_log_ids=reminder_log_ids,
    )


@router.get("/logs", response_model=list[TimeoutReminderLogResponse], summary="查询超时提醒日志")
def list_reminder_logs(
    start_date: str = Query(None, description="开始日期(YYYY-MM-DD)"),
    end_date: str = Query(None, description="结束日期(YYYY-MM-DD)"),
    reminder_level: TimeoutReminderLevel = Query(None, description="提醒级别"),
    config_id: int = Query(None, description="配置ID"),
    recipient_name: str = Query(None, description="接收人姓名"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(TimeoutReminderLog)

    if start_date:
        query = query.filter(TimeoutReminderLog.created_at >= f"{start_date} 00:00:00")
    if end_date:
        query = query.filter(TimeoutReminderLog.created_at <= f"{end_date} 23:59:59")
    if reminder_level:
        query = query.filter(TimeoutReminderLog.reminder_level == reminder_level)
    if config_id:
        query = query.filter(TimeoutReminderLog.config_id == config_id)
    if recipient_name:
        query = query.filter(TimeoutReminderLog.recipient_name.contains(recipient_name))

    return query.order_by(TimeoutReminderLog.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/levels", summary="获取提醒级别列表")
def get_reminder_levels():
    return {
        "levels": [
            {"value": level.value, "label": label}
            for level, label in REMINDER_LEVEL_LABELS.items()
        ]
    }

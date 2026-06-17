from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import (
    Appointment,
    AppointmentStatus,
    ReviewStatus,
    ExceptionType,
    ExceptionHandlingStatus,
    ExceptionRecord,
)
from schemas import (
    ExceptionRecordResponse,
    ExceptionListResponse,
    ExceptionHandleRequest,
    ExceptionScanResponse,
    MessageResponse,
)
from services import create_exception_record

router = APIRouter(prefix="/api/exceptions", tags=["异常记录"])

EXCEPTION_TYPE_LABELS = {
    ExceptionType.BLACKLIST_INTERCEPT: "黑名单拦截",
    ExceptionType.APPOINTMENT_CANCELLED: "预约撤销",
    ExceptionType.NOT_CHECKED_OUT_TIMEOUT: "未离园超时",
    ExceptionType.DUPLICATE_CHECKIN: "重复签到",
    ExceptionType.CHECKIN_REJECTED: "签到被拒",
}


@router.get("/scan-timeouts", response_model=ExceptionScanResponse, summary="扫描未离园超时访客")
def scan_timeouts(
    visit_date: str = Query(None, description="扫描日期(YYYY-MM-DD)，默认今日"),
    db: Session = Depends(get_db),
):
    if not visit_date:
        visit_date = date.today().isoformat()

    appointments = db.query(Appointment).filter(
        Appointment.visit_date == visit_date,
        Appointment.status == AppointmentStatus.CHECKED_IN,
    ).all()

    scanned_count = len(appointments)
    newly_created = 0
    already_existed = 0
    timeout_ids = []

    for a in appointments:
        if not a.visit_time_end:
            continue
        try:
            end_time = datetime.strptime(f"{a.visit_date} {a.visit_time_end}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if datetime.now() > end_time:
            existing = db.query(ExceptionRecord).filter(
                ExceptionRecord.exception_type == ExceptionType.NOT_CHECKED_OUT_TIMEOUT,
                ExceptionRecord.appointment_id == a.id,
            ).first()

            if existing:
                already_existed += 1
            else:
                create_exception_record(
                    db,
                    ExceptionType.NOT_CHECKED_OUT_TIMEOUT,
                    f"访客未在 {a.visit_time_end} 前离园，已超时 {datetime.now() - end_time}",
                    appointment=a,
                )
                newly_created += 1
            timeout_ids.append(a.id)

    return ExceptionScanResponse(
        scanned_count=scanned_count,
        newly_created=newly_created,
        already_existed=already_existed,
        timeout_ids=timeout_ids,
    )


@router.get("/", response_model=ExceptionListResponse, summary="查询异常记录列表")
def list_exceptions(
    exception_type: ExceptionType = Query(
        None,
        description="异常类型：blacklist_intercept / appointment_cancelled / not_checked_out_timeout / duplicate_checkin / checkin_rejected",
    ),
    handling_status: ExceptionHandlingStatus = Query(None, description="处理状态：pending / in_progress / resolved"),
    visit_date: str = Query(None, description="来访日期(YYYY-MM-DD)"),
    target_company: str = Query(None, description="按公司筛选"),
    target_building: str = Query(None, description="按楼栋筛选"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(ExceptionRecord)
    if exception_type:
        query = query.filter(ExceptionRecord.exception_type == exception_type)
    if handling_status:
        query = query.filter(ExceptionRecord.handling_status == handling_status)
    if visit_date:
        query = query.filter(ExceptionRecord.visit_date == visit_date)
    if target_company:
        query = query.filter(ExceptionRecord.target_company == target_company)
    if target_building:
        query = query.filter(ExceptionRecord.target_building == target_building)

    total = query.count()
    records = query.order_by(ExceptionRecord.created_at.desc()).offset(skip).limit(limit).all()
    return ExceptionListResponse(total=total, items=records)


@router.get("/types", summary="获取异常类型列表")
def get_exception_types():
    return {
        "types": [
            {"value": t.value, "label": label}
            for t, label in EXCEPTION_TYPE_LABELS.items()
        ]
    }


@router.get("/handling-statuses", summary="获取处理状态列表")
def get_handling_statuses():
    return {
        "statuses": [
            {"value": ExceptionHandlingStatus.PENDING.value, "label": "待处理"},
            {"value": ExceptionHandlingStatus.IN_PROGRESS.value, "label": "处理中"},
            {"value": ExceptionHandlingStatus.RESOLVED.value, "label": "已处理"},
        ]
    }


@router.get("/{exception_id}", response_model=ExceptionRecordResponse, summary="查询单条异常记录详情")
def get_exception_detail(exception_id: int, db: Session = Depends(get_db)):
    record = db.query(ExceptionRecord).filter(ExceptionRecord.id == exception_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="异常记录不存在")
    return record


@router.put("/handle", response_model=MessageResponse, summary="处理异常记录")
def handle_exception(data: ExceptionHandleRequest, db: Session = Depends(get_db)):
    record = db.query(ExceptionRecord).filter(ExceptionRecord.id == data.exception_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    record.handling_status = data.handling_status
    if data.handling_note:
        record.handling_note = data.handling_note
    record.handler_name = data.handler_name
    record.handled_at = datetime.now()

    db.commit()
    db.refresh(record)

    return MessageResponse(
        success=True,
        message="异常处理已更新",
        data={
            "exception_id": record.id,
            "handling_status": record.handling_status.value,
            "handler_name": record.handler_name,
            "handled_at": record.handled_at.isoformat() if record.handled_at else None,
        },
    )

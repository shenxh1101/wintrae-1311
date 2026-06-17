from datetime import datetime, date, timedelta
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
    BlacklistOperationLog,
    BlacklistOperationType,
)
from schemas import (
    ExceptionRecordResponse,
    ExceptionListResponse,
    ExceptionHandleRequest,
    ExceptionScanResponse,
    MessageResponse,
    ExceptionBatchHandleRequest,
    ExceptionBatchHandleResponse,
    ExceptionDetailWithTimelineResponse,
    ExceptionTimelineEvent,
    ExceptionStatsResponse,
    ExceptionStatsItem,
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


OVERDUE_HOURS = 24


def _calculate_avg_handling_minutes(records):
    resolved = [r for r in records if r.handled_at and r.created_at]
    if not resolved:
        return None
    total_minutes = sum((r.handled_at - r.created_at).total_seconds() / 60 for r in resolved)
    return round(total_minutes / len(resolved), 1)


def _is_overdue(record):
    if record.handling_status == ExceptionHandlingStatus.RESOLVED:
        return False
    delta = datetime.now() - record.created_at
    return delta.total_seconds() > OVERDUE_HOURS * 3600


def _group_stats(records, key_func):
    groups = {}
    for r in records:
        key = key_func(r)
        if key is None:
            key = "未指定"
        groups.setdefault(key, []).append(r)

    result = []
    for key, group_records in sorted(groups.items(), key=lambda x: -len(x[1])):
        pending = sum(1 for r in group_records if r.handling_status == ExceptionHandlingStatus.PENDING)
        in_progress = sum(1 for r in group_records if r.handling_status == ExceptionHandlingStatus.IN_PROGRESS)
        resolved = sum(1 for r in group_records if r.handling_status == ExceptionHandlingStatus.RESOLVED)
        overdue = sum(1 for r in group_records if _is_overdue(r))
        avg = _calculate_avg_handling_minutes(group_records)
        result.append(ExceptionStatsItem(
            group_key=key,
            pending_count=pending,
            in_progress_count=in_progress,
            resolved_count=resolved,
            total_count=len(group_records),
            avg_handling_minutes=avg,
            overdue_count=overdue,
        ))
    return result


@router.get("/statistics/summary", response_model=ExceptionStatsResponse, summary="异常处置时效统计")
def get_exception_statistics(
    start_date: str = Query(None, description="开始日期(YYYY-MM-DD)，默认近7天"),
    end_date: str = Query(None, description="结束日期(YYYY-MM-DD)，默认今日"),
    target_company: str = Query(None, description="按公司筛选"),
    target_building: str = Query(None, description="按楼栋筛选"),
    db: Session = Depends(get_db),
):
    if not end_date:
        end_date = date.today().isoformat()
    if not start_date:
        start_date = (date.today() - timedelta(days=7)).isoformat()

    query = db.query(ExceptionRecord).filter(
        ExceptionRecord.created_at >= f"{start_date} 00:00:00",
        ExceptionRecord.created_at <= f"{end_date} 23:59:59",
    )
    if target_company:
        query = query.filter(ExceptionRecord.target_company == target_company)
    if target_building:
        query = query.filter(ExceptionRecord.target_building == target_building)

    all_records = query.all()

    by_type = _group_stats(all_records, lambda r: EXCEPTION_TYPE_LABELS.get(r.exception_type, r.exception_type.value))
    by_building = _group_stats(all_records, lambda r: r.target_building)
    by_handler = _group_stats(all_records, lambda r: r.handler_name)

    overall_pending = sum(1 for r in all_records if r.handling_status == ExceptionHandlingStatus.PENDING)
    overall_in_progress = sum(1 for r in all_records if r.handling_status == ExceptionHandlingStatus.IN_PROGRESS)
    overall_resolved = sum(1 for r in all_records if r.handling_status == ExceptionHandlingStatus.RESOLVED)
    overall_overdue = sum(1 for r in all_records if _is_overdue(r))
    overall_avg = _calculate_avg_handling_minutes(all_records)

    return ExceptionStatsResponse(
        by_type=by_type,
        by_building=by_building,
        by_handler=by_handler,
        overall_pending=overall_pending,
        overall_in_progress=overall_in_progress,
        overall_resolved=overall_resolved,
        overall_overdue=overall_overdue,
        overall_avg_handling_minutes=overall_avg,
    )


@router.put("/batch-handle", response_model=ExceptionBatchHandleResponse, summary="批量处理异常记录")
def batch_handle_exceptions(data: ExceptionBatchHandleRequest, db: Session = Depends(get_db)):
    if not data.handling_status and not data.handler_name and not data.handling_note:
        raise HTTPException(status_code=400, detail="至少提供处理状态、处理人或处理说明中的一项")

    records = db.query(ExceptionRecord).filter(
        ExceptionRecord.id.in_(data.exception_ids)
    ).all()

    found_ids = {r.id for r in records}
    skipped_ids = [eid for eid in data.exception_ids if eid not in found_ids]

    now = datetime.now()
    for r in records:
        if data.handling_status:
            r.handling_status = data.handling_status
            if data.handling_status == ExceptionHandlingStatus.RESOLVED:
                r.handled_at = now
        if data.handler_name:
            r.handler_name = data.handler_name
        if data.handling_note:
            if r.handling_note:
                r.handling_note = f"{r.handling_note}\n{now.strftime('%Y-%m-%d %H:%M')} - {data.handling_note}"
            else:
                r.handling_note = f"{now.strftime('%Y-%m-%d %H:%M')} - {data.handling_note}"
        r.updated_at = now

    db.commit()

    return ExceptionBatchHandleResponse(
        success=True,
        message=f"批量处理完成，共更新 {len(records)} 条，跳过 {len(skipped_ids)} 条",
        updated_count=len(records),
        skipped_count=len(skipped_ids),
        skipped_ids=skipped_ids,
    )


@router.get("/{exception_id}/timeline", response_model=ExceptionDetailWithTimelineResponse, summary="查询异常详情（含关联事件时间轴）")
def get_exception_detail_with_timeline(exception_id: int, db: Session = Depends(get_db)):
    record = db.query(ExceptionRecord).filter(ExceptionRecord.id == exception_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    timeline = []

    if record.appointment_id:
        apt = db.query(Appointment).filter(Appointment.id == record.appointment_id).first()
        if apt:
            timeline.append(ExceptionTimelineEvent(
                event_type="预约创建",
                event_time=apt.created_at,
                description=f"提交预约申请，来访对象：{apt.target_employee_name}",
                operator=None,
                details={
                    "visit_date": apt.visit_date,
                    "visit_time": f"{apt.visit_time_start}-{apt.visit_time_end}",
                    "purpose": apt.purpose,
                },
            ))

            if apt.reviewed_at:
                review_label = {"pending": "待审核", "approved": "通过", "rejected": "拒绝"}.get(apt.review_status.value, apt.review_status.value)
                timeline.append(ExceptionTimelineEvent(
                    event_type="审核",
                    event_time=apt.reviewed_at,
                    description=f"审核结果：{review_label}，{apt.review_opinion or '无审核意见'}",
                    operator=apt.reviewer_name,
                    details={"review_status": apt.review_status.value},
                ))

            if apt.checkin_time:
                timeline.append(ExceptionTimelineEvent(
                    event_type="签到",
                    event_time=apt.checkin_time,
                    description=f"访客签到入园，核验结果：{apt.verification_result or '正常'}",
                    operator=None,
                    details={"verification_result": apt.verification_result},
                ))

            if apt.checkout_time:
                timeline.append(ExceptionTimelineEvent(
                    event_type="离园",
                    event_time=apt.checkout_time,
                    description="访客扫码离园",
                    operator=None,
                ))

            if apt.exception_reason and record.exception_type != ExceptionType.CHECKIN_REJECTED:
                timeline.append(ExceptionTimelineEvent(
                    event_type="拦截/异常",
                    event_time=apt.updated_at,
                    description=f"异常：{apt.exception_reason}",
                    operator=None,
                ))

    if record.exception_type == ExceptionType.BLACKLIST_INTERCEPT and record.id_last_four:
        blacklist_logs = db.query(BlacklistOperationLog).filter(
            BlacklistOperationLog.name == record.visitor_name,
            BlacklistOperationLog.id_last_four == record.id_last_four,
        ).order_by(BlacklistOperationLog.created_at.desc()).limit(5).all()

        for log in blacklist_logs:
            op_label = {"add": "加入黑名单", "remove": "移出黑名单", "re_add": "重新加入黑名单"}.get(log.operation_type.value, log.operation_type.value)
            timeline.append(ExceptionTimelineEvent(
                event_type="黑名单操作",
                event_time=log.created_at,
                description=f"{op_label}：{log.reason}",
                operator=log.operator_name,
                details={"operation_type": log.operation_type.value},
            ))

    timeline.append(ExceptionTimelineEvent(
        event_type="异常记录创建",
        event_time=record.created_at,
        description=f"{EXCEPTION_TYPE_LABELS.get(record.exception_type, record.exception_type.value)}：{record.exception_reason}",
        operator=None,
    ))

    if record.handled_at:
        status_label = {"pending": "待处理", "in_progress": "处理中", "resolved": "已处理"}.get(record.handling_status.value, record.handling_status.value)
        timeline.append(ExceptionTimelineEvent(
            event_type="异常处理",
            event_time=record.handled_at,
            description=f"处理状态更新为：{status_label}，{record.handling_note or '无处理说明'}",
            operator=record.handler_name,
            details={"handling_status": record.handling_status.value},
        ))

    timeline.sort(key=lambda e: e.event_time)

    return ExceptionDetailWithTimelineResponse(
        id=record.id,
        appointment_id=record.appointment_id,
        visitor_name=record.visitor_name,
        id_last_four=record.id_last_four,
        license_plate=record.license_plate,
        exception_type=record.exception_type,
        exception_reason=record.exception_reason,
        visit_date=record.visit_date,
        target_employee_name=record.target_employee_name,
        target_company=record.target_company,
        target_building=record.target_building,
        appointment_status=record.appointment_status,
        handling_status=record.handling_status,
        handling_note=record.handling_note,
        handler_name=record.handler_name,
        handled_at=record.handled_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        timeline=timeline,
    )

import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus, ReviewStatus, ExceptionRecord, ExceptionType
from schemas import ExportRequest, AppointmentListResponse, MessageResponse, ExceptionRecordResponse

router = APIRouter(prefix="/api/export", tags=["数据导出"])


def _build_export_query(data: ExportRequest, db: Session):
    query = db.query(Appointment).filter(
        Appointment.visit_date >= data.start_date,
        Appointment.visit_date <= data.end_date,
    )
    if data.target_company:
        query = query.filter(Appointment.target_company == data.target_company)
    if data.target_building:
        query = query.filter(Appointment.target_building == data.target_building)
    if data.status:
        query = query.filter(Appointment.status == data.status)
    if data.checkin_time_start:
        query = query.filter(Appointment.checkin_time >= data.checkin_time_start)
    if data.checkin_time_end:
        query = query.filter(Appointment.checkin_time <= data.checkin_time_end)
    if data.checkout_time_start:
        query = query.filter(Appointment.checkout_time >= data.checkout_time_start)
    if data.checkout_time_end:
        query = query.filter(Appointment.checkout_time <= data.checkout_time_end)
    if data.exception_reason:
        query = query.filter(Appointment.exception_reason.contains(data.exception_reason))

    return query.order_by(Appointment.visit_date.desc(), Appointment.created_at.desc())


@router.post("/query", response_model=AppointmentListResponse, summary="按时间查询访问记录")
def query_records(data: ExportRequest, db: Session = Depends(get_db)):
    appointments = _build_export_query(data, db).all()
    return AppointmentListResponse(total=len(appointments), items=appointments)


@router.post("/csv", summary="导出访问记录为CSV")
def export_csv(data: ExportRequest, db: Session = Depends(get_db)):
    appointments = _build_export_query(data, db).all()

    appointment_ids = [a.id for a in appointments]
    exception_records = db.query(ExceptionRecord).filter(
        ExceptionRecord.appointment_id.in_(appointment_ids),
    ).all()
    exc_map = {}
    for exc in exception_records:
        exc_map.setdefault(exc.appointment_id, []).append(exc)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "预约ID", "访客姓名", "证件后四位", "手机号", "车牌号", "随行人数",
        "来访对象", "来访公司", "来访楼栋", "来访事由", "来访日期",
        "来访时段", "是否临时",
        "审核结果", "审核意见", "审核人", "审核时间",
        "签到时间", "核验结果",
        "离园时间", "在园时长",
        "入离园状态",
        "超时标记",
        "异常类型", "异常原因",
        "异常记录ID", "异常处理状态", "处理人", "处理说明",
    ])

    for a in appointments:
        duration = ""
        if a.checkin_time and a.checkout_time:
            delta = a.checkout_time - a.checkin_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            duration = f"{hours}小时{minutes}分钟"

        status_label = {
            AppointmentStatus.PENDING: "待审核",
            AppointmentStatus.APPROVED: "待签到",
            AppointmentStatus.REJECTED: "已拒绝",
            AppointmentStatus.CANCELLED: "已撤销",
            AppointmentStatus.CHECKED_IN: "在园",
            AppointmentStatus.CHECKED_OUT: "已离园",
        }.get(a.status, a.status.value)

        review_label = {
            ReviewStatus.PENDING: "待审核",
            ReviewStatus.APPROVED: "通过",
            ReviewStatus.REJECTED: "拒绝",
        }.get(a.review_status, "")

        timeout_flag = ""
        exc_list = exc_map.get(a.id, [])
        timeout_exc = [e for e in exc_list if e.exception_type == ExceptionType.NOT_CHECKED_OUT_TIMEOUT]
        if timeout_exc:
            timeout_flag = "是"
        elif a.status == AppointmentStatus.CHECKED_IN and a.visit_time_end:
            try:
                end_time = datetime.strptime(f"{a.visit_date} {a.visit_time_end}", "%Y-%m-%d %H:%M")
                if datetime.now() > end_time:
                    timeout_flag = "是（未扫描）"
            except ValueError:
                pass
        else:
            timeout_flag = "否"

        exception_type = ""
        exception_reason = ""
        exception_id = ""
        exception_handling = ""
        exception_handler = ""
        exception_note = ""

        if exc_list:
            exc = exc_list[0]
            type_map = {
                ExceptionType.BLACKLIST_INTERCEPT: "黑名单拦截",
                ExceptionType.APPOINTMENT_CANCELLED: "预约撤销",
                ExceptionType.NOT_CHECKED_OUT_TIMEOUT: "未离园超时",
                ExceptionType.DUPLICATE_CHECKIN: "重复签到",
                ExceptionType.CHECKIN_REJECTED: "签到被拒",
            }
            exception_type = type_map.get(exc.exception_type, exc.exception_type.value)
            exception_reason = exc.exception_reason
            exception_id = exc.id
            handling_map = {"pending": "待处理", "in_progress": "处理中", "resolved": "已处理"}
            exception_handling = handling_map.get(exc.handling_status.value, exc.handling_status.value)
            exception_handler = exc.handler_name or ""
            exception_note = exc.handling_note or ""

        if not exception_type:
            if a.status == AppointmentStatus.CANCELLED:
                exception_type = "预约撤销"
            elif a.exception_reason and "黑名单" in a.exception_reason:
                exception_type = "黑名单拦截"
            elif a.status == AppointmentStatus.REJECTED and a.review_status == ReviewStatus.REJECTED:
                exception_type = "审核拒绝"
            elif a.status == AppointmentStatus.REJECTED and a.review_status == ReviewStatus.APPROVED:
                exception_type = "签到拦截（先通过后拦截）"

        writer.writerow([
            a.id,
            a.visitor_name,
            a.id_last_four,
            a.visitor_phone or "",
            a.license_plate or "",
            a.companions_count,
            a.target_employee_name,
            a.target_company or "",
            a.target_building or "",
            a.purpose or "",
            a.visit_date,
            f"{a.visit_time_start or ''}-{a.visit_time_end or ''}",
            "是" if a.is_temporary else "否",
            review_label,
            a.review_opinion or "",
            a.reviewer_name or "",
            a.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if a.reviewed_at else "",
            a.checkin_time.strftime("%Y-%m-%d %H:%M:%S") if a.checkin_time else "",
            a.verification_result or "",
            a.checkout_time.strftime("%Y-%m-%d %H:%M:%S") if a.checkout_time else "",
            duration,
            status_label,
            timeout_flag,
            exception_type,
            a.exception_reason or exception_reason,
            exception_id,
            exception_handling,
            exception_handler,
            exception_note,
        ])

    output.seek(0)
    filename = f"visit_records_{data.start_date}_{data.end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/exceptions/csv", summary="导出异常记录为CSV")
def export_exceptions_csv(data: ExportRequest, db: Session = Depends(get_db)):
    query = db.query(ExceptionRecord).filter(
        ExceptionRecord.created_at >= data.start_date,
        ExceptionRecord.created_at <= f"{data.end_date} 23:59:59",
    )
    if data.target_company:
        query = query.filter(ExceptionRecord.target_company == data.target_company)
    if data.target_building:
        query = query.filter(ExceptionRecord.target_building == data.target_building)

    records = query.order_by(ExceptionRecord.created_at.desc()).all()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "异常记录ID", "关联预约ID", "访客姓名", "证件后四位", "车牌号",
        "异常类型", "异常原因", "来访日期",
        "来访对象", "来访公司", "来访楼栋",
        "预约状态", "处理状态", "处理说明", "处理人", "处理时间",
        "创建时间",
    ])

    type_map = {
        ExceptionType.BLACKLIST_INTERCEPT: "黑名单拦截",
        ExceptionType.APPOINTMENT_CANCELLED: "预约撤销",
        ExceptionType.NOT_CHECKED_OUT_TIMEOUT: "未离园超时",
        ExceptionType.DUPLICATE_CHECKIN: "重复签到",
        ExceptionType.CHECKIN_REJECTED: "签到被拒",
    }
    handling_map = {"pending": "待处理", "in_progress": "处理中", "resolved": "已处理"}
    status_map = {
        AppointmentStatus.PENDING: "待审核",
        AppointmentStatus.APPROVED: "待签到",
        AppointmentStatus.REJECTED: "已拒绝",
        AppointmentStatus.CANCELLED: "已撤销",
        AppointmentStatus.CHECKED_IN: "在园",
        AppointmentStatus.CHECKED_OUT: "已离园",
    }

    for r in records:
        writer.writerow([
            r.id,
            r.appointment_id or "",
            r.visitor_name,
            r.id_last_four,
            r.license_plate or "",
            type_map.get(r.exception_type, r.exception_type.value),
            r.exception_reason,
            r.visit_date or "",
            r.target_employee_name or "",
            r.target_company or "",
            r.target_building or "",
            status_map.get(r.appointment_status, r.appointment_status.value if r.appointment_status else ""),
            handling_map.get(r.handling_status.value, r.handling_status.value),
            r.handling_note or "",
            r.handler_name or "",
            r.handled_at.strftime("%Y-%m-%d %H:%M:%S") if r.handled_at else "",
            r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    output.seek(0)
    filename = f"exception_records_{data.start_date}_{data.end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

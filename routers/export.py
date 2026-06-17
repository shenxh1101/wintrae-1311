import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus
from schemas import ExportRequest, AppointmentListResponse, MessageResponse

router = APIRouter(prefix="/api/export", tags=["数据导出"])


@router.post("/query", response_model=AppointmentListResponse, summary="按时间查询访问记录")
def query_records(data: ExportRequest, db: Session = Depends(get_db)):
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

    appointments = query.order_by(Appointment.visit_date.desc(), Appointment.created_at.desc()).all()
    return AppointmentListResponse(total=len(appointments), items=appointments)


@router.post("/csv", summary="导出访问记录为CSV")
def export_csv(data: ExportRequest, db: Session = Depends(get_db)):
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

    appointments = query.order_by(Appointment.visit_date.desc(), Appointment.created_at.desc()).all()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "预约ID", "访客姓名", "证件后四位", "手机号", "车牌号", "随行人数",
        "来访对象", "来访公司", "来访楼栋", "来访事由", "来访日期",
        "开始时间", "结束时间", "状态", "是否临时",
        "审核意见", "审核人", "审核时间",
        "签到时间", "离园时间", "核验结果", "异常原因",
        "创建时间",
    ])

    for a in appointments:
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
            a.visit_time_start or "",
            a.visit_time_end or "",
            a.status.value,
            "是" if a.is_temporary else "否",
            a.review_opinion or "",
            a.reviewer_name or "",
            a.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if a.reviewed_at else "",
            a.checkin_time.strftime("%Y-%m-%d %H:%M:%S") if a.checkin_time else "",
            a.checkout_time.strftime("%Y-%m-%d %H:%M:%S") if a.checkout_time else "",
            a.verification_result or "",
            a.exception_reason or "",
            a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    output.seek(0)
    filename = f"visit_records_{data.start_date}_{data.end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

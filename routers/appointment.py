import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus, Notification, NotificationType, ReviewStatus
from schemas import (
    AppointmentCreate,
    AppointmentReview,
    AppointmentResponse,
    AppointmentListResponse,
    MessageResponse,
)
from services import check_blacklist

router = APIRouter(prefix="/api/appointments", tags=["访客预约"])


@router.post("/", response_model=MessageResponse, summary="提交访客预约")
def create_appointment(data: AppointmentCreate, db: Session = Depends(get_db)):
    blacklist_hits = check_blacklist(db, data.visitor_name, data.id_last_four)

    if blacklist_hits:
        raise HTTPException(status_code=403, detail="该访客在黑名单中，无法预约")

    qr_code = f"VIS-{uuid.uuid4().hex[:12].upper()}"

    appointment = Appointment(
        visitor_name=data.visitor_name,
        visitor_phone=data.visitor_phone,
        id_last_four=data.id_last_four,
        license_plate=data.license_plate,
        companions_count=data.companions_count,
        target_employee_name=data.target_employee_name,
        target_employee_id=data.target_employee_id,
        target_company=data.target_company,
        target_building=data.target_building,
        purpose=data.purpose,
        visit_date=data.visit_date,
        visit_time_start=data.visit_time_start,
        visit_time_end=data.visit_time_end,
        status=AppointmentStatus.PENDING,
        qr_code=qr_code,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    notification = Notification(
        appointment_id=appointment.id,
        recipient_name=data.target_employee_name,
        notification_type=NotificationType.APPOINTMENT_CREATED,
        content=f"访客 {data.visitor_name} 预约于 {data.visit_date} 来访，请及时审核。",
    )
    db.add(notification)
    db.commit()

    return MessageResponse(
        success=True,
        message="预约提交成功",
        data={"appointment_id": appointment.id, "qr_code": qr_code},
    )


@router.put("/review", response_model=MessageResponse, summary="员工审核预约")
def review_appointment(data: AppointmentReview, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == data.appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约记录不存在")

    if appointment.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=400, detail="该预约不在待审核状态")

    if data.status not in (AppointmentStatus.APPROVED, AppointmentStatus.REJECTED):
        raise HTTPException(status_code=400, detail="审核结果只能为 approved 或 rejected")

    appointment.status = data.status
    appointment.review_status = (
        ReviewStatus.APPROVED if data.status == AppointmentStatus.APPROVED else ReviewStatus.REJECTED
    )
    appointment.review_opinion = data.review_opinion
    appointment.reviewer_name = data.reviewer_name
    appointment.reviewed_at = datetime.now()

    db.commit()
    db.refresh(appointment)

    notif_type = (
        NotificationType.APPOINTMENT_APPROVED
        if data.status == AppointmentStatus.APPROVED
        else NotificationType.APPOINTMENT_REJECTED
    )
    notif_content = (
        f"您的预约已通过审核。预约日期：{appointment.visit_date}。"
        if data.status == AppointmentStatus.APPROVED
        else f"您的预约已被拒绝。原因：{data.review_opinion or '无'}"
    )

    notification = Notification(
        appointment_id=appointment.id,
        recipient_name=appointment.visitor_name,
        recipient_phone=appointment.visitor_phone,
        notification_type=notif_type,
        content=notif_content,
    )
    db.add(notification)
    db.commit()

    return MessageResponse(
        success=True,
        message="审核完成",
        data={"appointment_id": appointment.id, "status": appointment.status.value},
    )


@router.get("/pending", response_model=AppointmentListResponse, summary="查询待审核预约列表")
def list_pending_appointments(
    employee_name: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Appointment).filter(Appointment.status == AppointmentStatus.PENDING)
    if employee_name:
        query = query.filter(Appointment.target_employee_name == employee_name)
    appointments = query.order_by(Appointment.created_at.desc()).all()
    return AppointmentListResponse(total=len(appointments), items=appointments)


@router.get("/{appointment_id}", response_model=AppointmentResponse, summary="查询预约详情")
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约记录不存在")
    return appointment

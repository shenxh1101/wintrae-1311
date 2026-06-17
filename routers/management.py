import uuid
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus, Employee, Notification, NotificationType, ReviewStatus
from schemas import (
    AppointmentResponse,
    AppointmentListResponse,
    TemporaryVisitCreate,
    CancelAppointmentRequest,
    EmployeeCreate,
    EmployeeResponse,
    MessageResponse,
)
from services import check_blacklist

router = APIRouter(prefix="/api/management", tags=["管理端"])


@router.get("/today-visitors", response_model=AppointmentListResponse, summary="查询今日访客")
def list_today_visitors(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    appointments = (
        db.query(Appointment)
        .filter(Appointment.visit_date == today)
        .order_by(Appointment.created_at.desc())
        .all()
    )
    return AppointmentListResponse(total=len(appointments), items=appointments)


@router.get("/filter", response_model=AppointmentListResponse, summary="按公司或楼栋筛选访客")
def filter_visitors(
    target_company: str = None,
    target_building: str = None,
    visit_date: str = None,
    status: AppointmentStatus = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Appointment)
    if target_company:
        query = query.filter(Appointment.target_company == target_company)
    if target_building:
        query = query.filter(Appointment.target_building == target_building)
    if visit_date:
        query = query.filter(Appointment.visit_date == visit_date)
    if status:
        query = query.filter(Appointment.status == status)

    total = query.count()
    appointments = query.order_by(Appointment.created_at.desc()).offset(skip).limit(limit).all()
    return AppointmentListResponse(total=total, items=appointments)


@router.post("/temporary", response_model=MessageResponse, summary="补录临时来访")
def create_temporary_visit(data: TemporaryVisitCreate, db: Session = Depends(get_db)):
    blacklist_hits = check_blacklist(db, data.visitor_name, data.id_last_four)

    if blacklist_hits:
        reasons = "；".join(b.reason for b in blacklist_hits)
        exception_msg = f"补录时黑名单校验未通过：{reasons}"

        qr_code = f"TMP-{uuid.uuid4().hex[:12].upper()}"
        today = date.today().isoformat()

        appointment = Appointment(
            visitor_name=data.visitor_name,
            visitor_phone=data.visitor_phone,
            id_last_four=data.id_last_four,
            license_plate=data.license_plate,
            companions_count=data.companions_count,
            target_employee_name=data.target_employee_name,
            target_company=data.target_company,
            target_building=data.target_building,
            purpose=data.purpose,
            visit_date=today,
            status=AppointmentStatus.REJECTED,
            qr_code=qr_code,
            is_temporary=True,
            review_status=ReviewStatus.REJECTED,
            exception_reason=exception_msg,
        )
        db.add(appointment)
        db.commit()
        db.refresh(appointment)

        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.BLACKLIST_ALERT,
            content=f"临时补录拦截：访客 {data.visitor_name}（证件后四位 {data.id_last_four}）在黑名单中，原因：{reasons}",
        )
        db.add(notification)
        db.commit()

        return MessageResponse(
            success=False,
            message="该访客在黑名单中，临时补录已拦截",
            data={"appointment_id": appointment.id, "exception_reason": exception_msg},
        )

    today = date.today().isoformat()
    qr_code = f"TMP-{uuid.uuid4().hex[:12].upper()}"

    appointment = Appointment(
        visitor_name=data.visitor_name,
        visitor_phone=data.visitor_phone,
        id_last_four=data.id_last_four,
        license_plate=data.license_plate,
        companions_count=data.companions_count,
        target_employee_name=data.target_employee_name,
        target_company=data.target_company,
        target_building=data.target_building,
        purpose=data.purpose,
        visit_date=today,
        status=AppointmentStatus.CHECKED_IN,
        qr_code=qr_code,
        is_temporary=True,
        review_status=ReviewStatus.APPROVED,
        checkin_time=datetime.now(),
        verification_result="补录通过",
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    return MessageResponse(
        success=True,
        message="临时来访补录成功",
        data={"appointment_id": appointment.id, "qr_code": qr_code},
    )


@router.put("/cancel", response_model=MessageResponse, summary="撤销预约")
def cancel_appointment(data: CancelAppointmentRequest, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == data.appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约记录不存在")

    if appointment.status in (AppointmentStatus.CHECKED_IN, AppointmentStatus.CHECKED_OUT):
        raise HTTPException(status_code=400, detail="已签到或已离园的预约无法撤销")

    appointment.status = AppointmentStatus.CANCELLED
    if data.reason:
        appointment.exception_reason = data.reason

    db.commit()

    return MessageResponse(
        success=True,
        message="预约已撤销",
        data={"appointment_id": appointment.id},
    )


@router.get("/not-checked-out", response_model=AppointmentListResponse, summary="查看未离园名单")
def list_not_checked_out(db: Session = Depends(get_db)):
    appointments = (
        db.query(Appointment)
        .filter(Appointment.status == AppointmentStatus.CHECKED_IN)
        .order_by(Appointment.checkin_time.asc())
        .all()
    )
    return AppointmentListResponse(total=len(appointments), items=appointments)


@router.post("/employees", response_model=MessageResponse, summary="添加员工信息")
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    employee = Employee(
        name=data.name,
        phone=data.phone,
        company=data.company,
        department=data.department,
        building=data.building,
        floor=data.floor,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return MessageResponse(
        success=True,
        message="员工添加成功",
        data={"employee_id": employee.id},
    )


@router.get("/employees", response_model=list[EmployeeResponse], summary="查询员工列表")
def list_employees(
    company: str = None,
    building: str = None,
    name: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Employee).filter(Employee.is_active == True)
    if company:
        query = query.filter(Employee.company == company)
    if building:
        query = query.filter(Employee.building == building)
    if name:
        query = query.filter(Employee.name.contains(name))

    employees = query.order_by(Employee.name).offset(skip).limit(limit).all()
    return employees

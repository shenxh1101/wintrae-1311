from datetime import datetime
from sqlalchemy.orm import Session
from models import Blacklist, ExceptionRecord, ExceptionType, ExceptionHandlingStatus, Appointment


def check_blacklist(db: Session, name: str, id_last_four: str | None = None) -> list[Blacklist]:
    query = db.query(Blacklist).filter(Blacklist.is_active == True, Blacklist.name == name)
    if id_last_four:
        query = query.filter(
            (Blacklist.id_last_four == id_last_four) | (Blacklist.id_last_four == None)
        )
    return query.all()


def create_exception_record(
    db: Session,
    exception_type: ExceptionType,
    exception_reason: str,
    appointment: Appointment | None = None,
    visitor_name: str | None = None,
    id_last_four: str | None = None,
    license_plate: str | None = None,
) -> ExceptionRecord:
    existing = (
        db.query(ExceptionRecord)
        .filter(
            ExceptionRecord.exception_type == exception_type,
            ExceptionRecord.appointment_id == appointment.id if appointment else None,
        )
        .first()
    )
    if existing:
        return existing

    if appointment:
        visitor_name = visitor_name or appointment.visitor_name
        id_last_four = id_last_four or appointment.id_last_four
        license_plate = license_plate or appointment.license_plate

    record = ExceptionRecord(
        appointment_id=appointment.id if appointment else None,
        visitor_name=visitor_name or "",
        id_last_four=id_last_four or "",
        license_plate=license_plate,
        exception_type=exception_type,
        exception_reason=exception_reason,
        visit_date=appointment.visit_date if appointment else None,
        target_employee_name=appointment.target_employee_name if appointment else None,
        target_company=appointment.target_company if appointment else None,
        target_building=appointment.target_building if appointment else None,
        appointment_status=appointment.status if appointment else None,
        handling_status=ExceptionHandlingStatus.PENDING,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def has_exception_record(
    db: Session,
    exception_type: ExceptionType,
    appointment_id: int,
) -> bool:
    existing = (
        db.query(ExceptionRecord)
        .filter(
            ExceptionRecord.exception_type == exception_type,
            ExceptionRecord.appointment_id == appointment_id,
        )
        .first()
    )
    return existing is not None

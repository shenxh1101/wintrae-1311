import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Boolean
from database import Base


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NotificationType(str, enum.Enum):
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_APPROVED = "appointment_approved"
    APPOINTMENT_REJECTED = "appointment_rejected"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    VISITOR_CHECKED_IN = "visitor_checked_in"
    VISITOR_CHECKED_OUT = "visitor_checked_out"
    BLACKLIST_ALERT = "blacklist_alert"


class ExceptionType(str, enum.Enum):
    BLACKLIST_INTERCEPT = "blacklist_intercept"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    NOT_CHECKED_OUT_TIMEOUT = "not_checked_out_timeout"
    DUPLICATE_CHECKIN = "duplicate_checkin"
    CHECKIN_REJECTED = "checkin_rejected"


class ExceptionHandlingStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    visitor_name = Column(String(50), nullable=False)
    visitor_phone = Column(String(20), nullable=True)
    id_last_four = Column(String(4), nullable=False)
    license_plate = Column(String(20), nullable=True, default="")
    companions_count = Column(Integer, nullable=False, default=0)
    target_employee_name = Column(String(50), nullable=False)
    target_employee_id = Column(Integer, nullable=True)
    target_company = Column(String(100), nullable=True)
    target_building = Column(String(100), nullable=True)
    purpose = Column(String(200), nullable=True, default="")
    visit_date = Column(String(10), nullable=False)
    visit_time_start = Column(String(5), nullable=True, default="09:00")
    visit_time_end = Column(String(5), nullable=True, default="18:00")
    status = Column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.PENDING)
    qr_code = Column(String(200), nullable=True, unique=True)
    is_temporary = Column(Boolean, nullable=False, default=False)
    review_status = Column(Enum(ReviewStatus), nullable=False, default=ReviewStatus.PENDING)
    review_opinion = Column(Text, nullable=True)
    reviewer_name = Column(String(50), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    checkin_time = Column(DateTime, nullable=True)
    checkout_time = Column(DateTime, nullable=True)
    verification_result = Column(String(50), nullable=True)
    exception_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=True)
    company = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    building = Column(String(100), nullable=True)
    floor = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class Blacklist(Base):
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    id_last_four = Column(String(4), nullable=False)
    phone = Column(String(20), nullable=True)
    reason = Column(Text, nullable=False)
    added_by = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class BlacklistOperationType(str, enum.Enum):
    ADD = "add"
    REMOVE = "remove"
    RE_ADD = "re_add"


class BlacklistOperationLog(Base):
    __tablename__ = "blacklist_operation_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    blacklist_id = Column(Integer, nullable=False)
    name = Column(String(50), nullable=False)
    id_last_four = Column(String(4), nullable=False)
    operation_type = Column(Enum(BlacklistOperationType), nullable=False)
    reason = Column(Text, nullable=False)
    operator_name = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id = Column(Integer, nullable=True)
    recipient_name = Column(String(50), nullable=True)
    recipient_phone = Column(String(20), nullable=True)
    notification_type = Column(Enum(NotificationType), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class ExceptionRecord(Base):
    __tablename__ = "exception_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id = Column(Integer, nullable=True)
    visitor_name = Column(String(50), nullable=False)
    id_last_four = Column(String(4), nullable=False)
    license_plate = Column(String(20), nullable=True)
    exception_type = Column(Enum(ExceptionType), nullable=False)
    exception_reason = Column(Text, nullable=False)
    visit_date = Column(String(10), nullable=True)
    target_employee_name = Column(String(50), nullable=True)
    target_company = Column(String(100), nullable=True)
    target_building = Column(String(100), nullable=True)
    appointment_status = Column(Enum(AppointmentStatus), nullable=True)
    handling_status = Column(Enum(ExceptionHandlingStatus), nullable=False, default=ExceptionHandlingStatus.PENDING)
    handling_note = Column(Text, nullable=True)
    handler_name = Column(String(50), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

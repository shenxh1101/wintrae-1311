from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from models import (
    AppointmentStatus,
    NotificationType,
    BlacklistOperationType,
    ReviewStatus,
    ExceptionType,
    ExceptionHandlingStatus,
)


class AppointmentCreate(BaseModel):
    visitor_name: str = Field(..., max_length=50, description="访客姓名")
    visitor_phone: Optional[str] = Field(None, max_length=20, description="访客手机号")
    id_last_four: str = Field(..., min_length=4, max_length=4, description="证件后四位")
    license_plate: Optional[str] = Field(None, max_length=20, description="车牌号")
    companions_count: int = Field(0, ge=0, description="随行人数")
    target_employee_name: str = Field(..., max_length=50, description="来访对象姓名")
    target_employee_id: Optional[int] = Field(None, description="来访对象员工ID")
    target_company: Optional[str] = Field(None, max_length=100, description="来访公司")
    target_building: Optional[str] = Field(None, max_length=100, description="来访楼栋")
    purpose: Optional[str] = Field(None, max_length=200, description="来访事由")
    visit_date: str = Field(..., max_length=10, description="来访日期(YYYY-MM-DD)")
    visit_time_start: Optional[str] = Field("09:00", max_length=5, description="开始时间")
    visit_time_end: Optional[str] = Field("18:00", max_length=5, description="结束时间")


class AppointmentReview(BaseModel):
    appointment_id: int = Field(..., description="预约ID")
    status: AppointmentStatus = Field(..., description="审核结果(approved/rejected)")
    review_opinion: Optional[str] = Field(None, description="审核意见")
    reviewer_name: str = Field(..., max_length=50, description="审核人姓名")


class AppointmentResponse(BaseModel):
    id: int
    visitor_name: str
    visitor_phone: Optional[str]
    id_last_four: str
    license_plate: Optional[str]
    companions_count: int
    target_employee_name: str
    target_employee_id: Optional[int]
    target_company: Optional[str]
    target_building: Optional[str]
    purpose: Optional[str]
    visit_date: str
    visit_time_start: Optional[str]
    visit_time_end: Optional[str]
    status: AppointmentStatus
    qr_code: Optional[str]
    is_temporary: bool
    review_opinion: Optional[str]
    reviewer_name: Optional[str]
    reviewed_at: Optional[datetime]
    checkin_time: Optional[datetime]
    checkout_time: Optional[datetime]
    verification_result: Optional[str]
    exception_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppointmentListResponse(BaseModel):
    total: int
    items: list[AppointmentResponse]


class CheckInRequest(BaseModel):
    qr_code: str = Field(..., description="二维码凭证")
    verification_result: Optional[str] = Field(None, max_length=50, description="核验结果")
    exception_reason: Optional[str] = Field(None, description="异常原因")


class CheckOutRequest(BaseModel):
    appointment_id: int = Field(..., description="预约ID")


class BlacklistCreate(BaseModel):
    name: str = Field(..., max_length=50, description="姓名")
    id_last_four: str = Field(..., min_length=4, max_length=4, description="证件后四位")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    reason: str = Field(..., description="加入黑名单原因")
    added_by: Optional[str] = Field(None, max_length=50, description="操作人")


class BlacklistResponse(BaseModel):
    id: int
    name: str
    id_last_four: str
    phone: Optional[str]
    reason: str
    added_by: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BlacklistCheckRequest(BaseModel):
    name: str = Field(..., max_length=50, description="姓名")
    id_last_four: str = Field(..., min_length=4, max_length=4, description="证件后四位")


class BlacklistCheckResponse(BaseModel):
    is_blacklisted: bool
    matches: list[BlacklistResponse] = []


class NotificationCreate(BaseModel):
    appointment_id: Optional[int] = Field(None, description="关联预约ID")
    recipient_name: Optional[str] = Field(None, max_length=50, description="接收人姓名")
    recipient_phone: Optional[str] = Field(None, max_length=20, description="接收人手机")
    notification_type: NotificationType = Field(..., description="通知类型")
    content: str = Field(..., description="通知内容")


class NotificationResponse(BaseModel):
    id: int
    appointment_id: Optional[int]
    recipient_name: Optional[str]
    recipient_phone: Optional[str]
    notification_type: NotificationType
    content: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemporaryVisitCreate(BaseModel):
    visitor_name: str = Field(..., max_length=50, description="访客姓名")
    visitor_phone: Optional[str] = Field(None, max_length=20, description="访客手机号")
    id_last_four: str = Field(..., min_length=4, max_length=4, description="证件后四位")
    license_plate: Optional[str] = Field(None, max_length=20, description="车牌号")
    companions_count: int = Field(0, ge=0, description="随行人数")
    target_employee_name: str = Field(..., max_length=50, description="来访对象")
    target_company: Optional[str] = Field(None, max_length=100, description="来访公司")
    target_building: Optional[str] = Field(None, max_length=100, description="来访楼栋")
    purpose: Optional[str] = Field(None, max_length=200, description="来访事由")


class CancelAppointmentRequest(BaseModel):
    appointment_id: int = Field(..., description="预约ID")
    reason: Optional[str] = Field(None, description="撤销原因")


class EmployeeCreate(BaseModel):
    name: str = Field(..., max_length=50, description="姓名")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    company: Optional[str] = Field(None, max_length=100, description="公司")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    building: Optional[str] = Field(None, max_length=100, description="楼栋")
    floor: Optional[str] = Field(None, max_length=20, description="楼层")


class EmployeeResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    company: Optional[str]
    department: Optional[str]
    building: Optional[str]
    floor: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportRequest(BaseModel):
    start_date: str = Field(..., max_length=10, description="开始日期(YYYY-MM-DD)")
    end_date: str = Field(..., max_length=10, description="结束日期(YYYY-MM-DD)")
    target_company: Optional[str] = Field(None, max_length=100, description="按公司筛选")
    target_building: Optional[str] = Field(None, max_length=100, description="按楼栋筛选")
    status: Optional[AppointmentStatus] = Field(None, description="按状态筛选")
    checkin_time_start: Optional[str] = Field(None, description="签到时间起(YYYY-MM-DD HH:MM:SS)")
    checkin_time_end: Optional[str] = Field(None, description="签到时间止(YYYY-MM-DD HH:MM:SS)")
    checkout_time_start: Optional[str] = Field(None, description="离园时间起(YYYY-MM-DD HH:MM:SS)")
    checkout_time_end: Optional[str] = Field(None, description="离园时间止(YYYY-MM-DD HH:MM:SS)")
    exception_reason: Optional[str] = Field(None, description="异常原因关键词筛选")


class VerificationDeskResponse(BaseModel):
    appointment_id: int
    visitor_name: str
    visitor_phone: Optional[str]
    id_last_four: str
    license_plate: Optional[str]
    companions_count: int
    target_employee_name: str
    target_company: Optional[str]
    target_building: Optional[str]
    purpose: Optional[str]
    visit_date: str
    visit_time_start: Optional[str]
    visit_time_end: Optional[str]
    status: AppointmentStatus
    is_temporary: bool
    review_status: ReviewStatus
    review_opinion: Optional[str]
    reviewer_name: Optional[str]
    reviewed_at: Optional[datetime]
    checkin_time: Optional[datetime]
    checkout_time: Optional[datetime]
    verification_result: Optional[str]
    exception_reason: Optional[str]
    is_blacklisted: bool
    blacklist_reasons: list[str] = []
    can_admit: bool
    review_conclusion: str
    checkin_status: str
    checkout_status: str
    admission_suggestion: str
    exception_reason_display: str
    handling_status: str
    handler: Optional[str]


class MessageResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict | list | None] = None


class ExceptionRecordResponse(BaseModel):
    id: int
    appointment_id: Optional[int]
    visitor_name: str
    id_last_four: str
    license_plate: Optional[str]
    exception_type: ExceptionType
    exception_reason: str
    visit_date: Optional[str]
    target_employee_name: Optional[str]
    target_company: Optional[str]
    target_building: Optional[str]
    appointment_status: Optional[AppointmentStatus]
    handling_status: ExceptionHandlingStatus
    handling_note: Optional[str]
    handler_name: Optional[str]
    handled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExceptionListResponse(BaseModel):
    total: int
    items: list[ExceptionRecordResponse]


class ExceptionHandleRequest(BaseModel):
    exception_id: int = Field(..., description="异常记录ID")
    handling_status: ExceptionHandlingStatus = Field(..., description="处理状态：pending/in_progress/resolved")
    handling_note: Optional[str] = Field(None, description="处理说明")
    handler_name: str = Field(..., max_length=50, description="处理人姓名")


class ExceptionScanResponse(BaseModel):
    scanned_count: int
    newly_created: int
    already_existed: int
    timeout_ids: list[int] = []


class BlacklistOperationLogResponse(BaseModel):
    id: int
    blacklist_id: int
    name: str
    id_last_four: str
    operation_type: BlacklistOperationType
    reason: str
    operator_name: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class BlacklistWithOperationLogsResponse(BlacklistResponse):
    operation_logs: list[BlacklistOperationLogResponse] = []


class BlacklistTimelineResponse(BaseModel):
    name: str
    id_last_four: str
    total_operations: int
    current_status: str
    operation_logs: list[BlacklistOperationLogResponse] = []

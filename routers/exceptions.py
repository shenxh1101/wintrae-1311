from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus, ReviewStatus
from schemas import ExceptionRecordResponse, ExceptionListResponse

router = APIRouter(prefix="/api/exceptions", tags=["异常记录"])

EXCEPTION_TYPE_BLACKLIST = "blacklist_intercept"
EXCEPTION_TYPE_CANCELLED = "appointment_cancelled"
EXCEPTION_TYPE_TIMEOUT = "not_checked_out_timeout"
EXCEPTION_TYPE_DUPLICATE = "duplicate_checkin"
EXCEPTION_TYPE_CHECKIN_REJECT = "checkin_rejected"

EXCEPTION_TYPE_LABELS = {
    EXCEPTION_TYPE_BLACKLIST: "黑名单拦截",
    EXCEPTION_TYPE_CANCELLED: "预约撤销",
    EXCEPTION_TYPE_TIMEOUT: "未离园超时",
    EXCEPTION_TYPE_DUPLICATE: "重复签到",
    EXCEPTION_TYPE_CHECKIN_REJECT: "签到被拒",
}


def _classify_exception(appointment: Appointment) -> str | None:
    if appointment.status == AppointmentStatus.CANCELLED:
        return EXCEPTION_TYPE_CANCELLED
    if appointment.exception_reason and "黑名单" in appointment.exception_reason:
        return EXCEPTION_TYPE_BLACKLIST
    if appointment.status == AppointmentStatus.REJECTED and appointment.review_status == ReviewStatus.APPROVED:
        return EXCEPTION_TYPE_CHECKIN_REJECT
    return None


def _get_exception_reason(appointment: Appointment) -> str:
    if appointment.exception_reason:
        return appointment.exception_reason
    if appointment.status == AppointmentStatus.CANCELLED:
        return "预约已撤销"
    return ""


def _get_handling_status(appointment: Appointment) -> str:
    if appointment.status == AppointmentStatus.CHECKED_OUT:
        return "已处理"
    if appointment.status == AppointmentStatus.CANCELLED:
        return "已处理"
    if appointment.status == AppointmentStatus.REJECTED:
        return "已处理"
    if appointment.status == AppointmentStatus.CHECKED_IN:
        return "待处理"
    return "待处理"


def _get_handler(appointment: Appointment) -> str | None:
    if appointment.reviewer_name:
        return appointment.reviewer_name
    return None


@router.get("/", response_model=ExceptionListResponse, summary="查询异常记录")
def list_exceptions(
    exception_type: str = Query(
        None,
        description="异常类型：blacklist_intercept(黑名单拦截)、appointment_cancelled(预约撤销)、not_checked_out_timeout(未离园超时)、checkin_rejected(签到被拒)",
    ),
    visit_date: str = Query(None, description="来访日期(YYYY-MM-DD)，默认今日"),
    target_company: str = Query(None, description="按公司筛选"),
    target_building: str = Query(None, description="按楼栋筛选"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if not visit_date:
        visit_date = date.today().isoformat()

    query = db.query(Appointment).filter(Appointment.visit_date == visit_date)

    if target_company:
        query = query.filter(Appointment.target_company == target_company)
    if target_building:
        query = query.filter(Appointment.target_building == target_building)

    appointments = query.order_by(Appointment.created_at.desc()).all()

    results = []
    for a in appointments:
        exc_type = _classify_exception(a)

        if exception_type == EXCEPTION_TYPE_TIMEOUT:
            if a.status == AppointmentStatus.CHECKED_IN and a.visit_time_end:
                try:
                    end_time = datetime.strptime(
                        f"{a.visit_date} {a.visit_time_end}", "%Y-%m-%d %H:%M"
                    )
                    if datetime.now() > end_time:
                        exc_type = EXCEPTION_TYPE_TIMEOUT
                except ValueError:
                    pass
            else:
                exc_type = None

        if not exc_type:
            continue

        if exception_type and exc_type != exception_type:
            continue

        results.append(
            ExceptionRecordResponse(
                appointment_id=a.id,
                visitor_name=a.visitor_name,
                id_last_four=a.id_last_four,
                exception_type=EXCEPTION_TYPE_LABELS.get(exc_type, exc_type),
                exception_reason=_get_exception_reason(a),
                visit_date=a.visit_date,
                target_employee_name=a.target_employee_name,
                target_company=a.target_company,
                target_building=a.target_building,
                status=a.status,
                handling_status=_get_handling_status(a),
                handler=_get_handler(a),
                created_at=a.created_at,
                handled_at=a.reviewed_at if a.reviewed_at else None,
            )
        )

    total = len(results)
    paginated = results[skip : skip + limit]

    return ExceptionListResponse(total=total, items=paginated)


@router.get("/types", summary="获取异常类型列表")
def get_exception_types():
    return {
        "types": [
            {"value": EXCEPTION_TYPE_BLACKLIST, "label": EXCEPTION_TYPE_LABELS[EXCEPTION_TYPE_BLACKLIST]},
            {"value": EXCEPTION_TYPE_CANCELLED, "label": EXCEPTION_TYPE_LABELS[EXCEPTION_TYPE_CANCELLED]},
            {"value": EXCEPTION_TYPE_TIMEOUT, "label": EXCEPTION_TYPE_LABELS[EXCEPTION_TYPE_TIMEOUT]},
            {"value": EXCEPTION_TYPE_CHECKIN_REJECT, "label": EXCEPTION_TYPE_LABELS[EXCEPTION_TYPE_CHECKIN_REJECT]},
        ]
    }


@router.get("/{appointment_id}", response_model=ExceptionRecordResponse, summary="查询单条异常记录详情")
def get_exception_detail(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="预约记录不存在")

    exc_type = _classify_exception(appointment)
    if not exc_type:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="该预约无异常记录")

    return ExceptionRecordResponse(
        appointment_id=appointment.id,
        visitor_name=appointment.visitor_name,
        id_last_four=appointment.id_last_four,
        exception_type=EXCEPTION_TYPE_LABELS.get(exc_type, exc_type),
        exception_reason=_get_exception_reason(appointment),
        visit_date=appointment.visit_date,
        target_employee_name=appointment.target_employee_name,
        target_company=appointment.target_company,
        target_building=appointment.target_building,
        status=appointment.status,
        handling_status=_get_handling_status(appointment),
        handler=_get_handler(appointment),
        created_at=appointment.created_at,
        handled_at=appointment.reviewed_at if appointment.reviewed_at else None,
    )

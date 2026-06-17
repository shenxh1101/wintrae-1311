import io
import base64
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Appointment, AppointmentStatus, Blacklist, Notification, NotificationType
from schemas import CheckInRequest, CheckOutRequest, AppointmentResponse, MessageResponse

router = APIRouter(prefix="/api/visit", tags=["入园核验"])


@router.get("/qr/{qr_code}", response_model=MessageResponse, summary="通过二维码查询预约信息")
def get_by_qr_code(qr_code: str, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.qr_code == qr_code).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="二维码对应的预约不存在")
    return MessageResponse(
        success=True,
        message="查询成功",
        data={
            "appointment_id": appointment.id,
            "visitor_name": appointment.visitor_name,
            "status": appointment.status.value,
            "visit_date": appointment.visit_date,
            "target_employee_name": appointment.target_employee_name,
            "target_company": appointment.target_company,
            "target_building": appointment.target_building,
        },
    )


@router.get("/qr-image/{appointment_id}", response_model=MessageResponse, summary="获取预约二维码图片(Base64)")
def get_qr_image(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约记录不存在")

    if not appointment.qr_code:
        raise HTTPException(status_code=400, detail="该预约未生成二维码")

    try:
        import qrcode as qrcode_lib

        qr = qrcode_lib.QRCode(version=1, box_size=10, border=2)
        qr.add_data(appointment.qr_code)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return MessageResponse(
            success=True,
            message="二维码生成成功",
            data={"qr_code": appointment.qr_code, "qr_image_base64": img_base64},
        )
    except ImportError:
        return MessageResponse(
            success=True,
            message="二维码库未安装，仅返回编码",
            data={"qr_code": appointment.qr_code},
        )


@router.post("/checkin", response_model=MessageResponse, summary="到访签到")
def check_in(data: CheckInRequest, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.qr_code == data.qr_code).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="二维码对应的预约不存在")

    if appointment.status == AppointmentStatus.CHECKED_IN:
        raise HTTPException(status_code=400, detail="该访客已签到，请勿重复操作")

    if appointment.status != AppointmentStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"当前预约状态为 {appointment.status.value}，无法签到",
        )

    blacklist_hits = (
        db.query(Blacklist)
        .filter(
            Blacklist.is_active == True,
            Blacklist.name == appointment.visitor_name,
        )
        .all()
    )
    if appointment.id_last_four:
        blacklist_hits = [
            b for b in blacklist_hits if b.id_last_four is None or b.id_last_four == appointment.id_last_four
        ]

    if blacklist_hits:
        appointment.status = AppointmentStatus.REJECTED
        appointment.exception_reason = "签到时发现访客在黑名单中"
        db.commit()

        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.BLACKLIST_ALERT,
            content=f"访客 {appointment.visitor_name} 签到时触发黑名单预警！",
        )
        db.add(notification)
        db.commit()

        raise HTTPException(status_code=403, detail="该访客在黑名单中，签到被拒绝")

    appointment.status = AppointmentStatus.CHECKED_IN
    appointment.checkin_time = datetime.now()
    appointment.verification_result = data.verification_result
    if data.exception_reason:
        appointment.exception_reason = data.exception_reason

    db.commit()
    db.refresh(appointment)

    notification = Notification(
        appointment_id=appointment.id,
        recipient_name=appointment.target_employee_name,
        notification_type=NotificationType.VISITOR_CHECKED_IN,
        content=f"访客 {appointment.visitor_name} 已于 {appointment.checkin_time.strftime('%H:%M')} 签到入园。",
    )
    db.add(notification)
    db.commit()

    return MessageResponse(
        success=True,
        message="签到成功",
        data={"appointment_id": appointment.id, "checkin_time": appointment.checkin_time.isoformat()},
    )


@router.post("/checkout", response_model=MessageResponse, summary="离园登记")
def check_out(data: CheckOutRequest, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == data.appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="预约记录不存在")

    if appointment.status == AppointmentStatus.CHECKED_OUT:
        raise HTTPException(status_code=400, detail="该访客已离园，请勿重复操作")

    if appointment.status != AppointmentStatus.CHECKED_IN:
        raise HTTPException(
            status_code=400,
            detail=f"当前预约状态为 {appointment.status.value}，无法办理离园",
        )

    appointment.status = AppointmentStatus.CHECKED_OUT
    appointment.checkout_time = datetime.now()

    db.commit()
    db.refresh(appointment)

    notification = Notification(
        appointment_id=appointment.id,
        recipient_name=appointment.target_employee_name,
        notification_type=NotificationType.VISITOR_CHECKED_OUT,
        content=f"访客 {appointment.visitor_name} 已于 {appointment.checkout_time.strftime('%H:%M')} 离园。",
    )
    db.add(notification)
    db.commit()

    return MessageResponse(
        success=True,
        message="离园登记成功",
        data={"appointment_id": appointment.id, "checkout_time": appointment.checkout_time.isoformat()},
    )

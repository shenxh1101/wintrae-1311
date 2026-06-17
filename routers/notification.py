from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Notification, NotificationType
from schemas import NotificationCreate, NotificationResponse, MessageResponse

router = APIRouter(prefix="/api/notifications", tags=["消息提醒"])


@router.post("/", response_model=MessageResponse, summary="发送通知")
def send_notification(data: NotificationCreate, db: Session = Depends(get_db)):
    notification = Notification(
        appointment_id=data.appointment_id,
        recipient_name=data.recipient_name,
        recipient_phone=data.recipient_phone,
        notification_type=data.notification_type,
        content=data.content,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return MessageResponse(success=True, message="通知已发送", data={"notification_id": notification.id})


@router.get("/", response_model=list[NotificationResponse], summary="查询通知列表")
def list_notifications(
    recipient_name: str = None,
    notification_type: NotificationType = None,
    is_read: bool = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Notification)
    if recipient_name:
        query = query.filter(Notification.recipient_name == recipient_name)
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)

    notifications = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()
    return notifications


@router.put("/{notification_id}/read", response_model=MessageResponse, summary="标记通知已读")
def mark_as_read(notification_id: int, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")

    notification.is_read = True
    db.commit()

    return MessageResponse(success=True, message="已标记为已读", data={"notification_id": notification_id})

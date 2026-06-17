from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Blacklist, BlacklistOperationLog, BlacklistOperationType
from schemas import (
    BlacklistCreate,
    BlacklistResponse,
    BlacklistCheckRequest,
    BlacklistCheckResponse,
    MessageResponse,
    BlacklistOperationLogResponse,
    BlacklistWithOperationLogsResponse,
    BlacklistTimelineResponse,
)
from services import check_blacklist

router = APIRouter(prefix="/api/blacklist", tags=["黑名单校验"])


def _add_operation_log(
    db: Session,
    blacklist_id: int,
    name: str,
    id_last_four: str,
    operation_type: BlacklistOperationType,
    reason: str,
    operator_name: str | None = None,
):
    log = BlacklistOperationLog(
        blacklist_id=blacklist_id,
        name=name,
        id_last_four=id_last_four,
        operation_type=operation_type,
        reason=reason,
        operator_name=operator_name,
    )
    db.add(log)
    db.commit()


@router.post("/check", response_model=BlacklistCheckResponse, summary="校验访客是否在黑名单中")
def check_blacklist_api(data: BlacklistCheckRequest, db: Session = Depends(get_db)):
    matches = check_blacklist(db, data.name, data.id_last_four)
    return BlacklistCheckResponse(is_blacklisted=len(matches) > 0, matches=matches)


@router.post("/", response_model=MessageResponse, summary="添加黑名单记录")
def add_to_blacklist(data: BlacklistCreate, db: Session = Depends(get_db)):
    if not data.id_last_four:
        raise HTTPException(status_code=400, detail="添加黑名单时证件后四位为必填项")

    existing_active = (
        db.query(Blacklist)
        .filter(
            Blacklist.name == data.name,
            Blacklist.id_last_four == data.id_last_four,
            Blacklist.is_active == True,
        )
        .first()
    )
    if existing_active:
        raise HTTPException(
            status_code=400,
            detail=f"人员 {data.name}（证件后四位 {data.id_last_four}）已在黑名单中",
        )

    has_history = (
        db.query(Blacklist)
        .filter(
            Blacklist.name == data.name,
            Blacklist.id_last_four == data.id_last_four,
        )
        .first()
    )

    operation_type = BlacklistOperationType.RE_ADD if has_history else BlacklistOperationType.ADD

    entry = Blacklist(
        name=data.name,
        id_last_four=data.id_last_four,
        phone=data.phone,
        reason=data.reason,
        added_by=data.added_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    _add_operation_log(
        db,
        blacklist_id=entry.id,
        name=data.name,
        id_last_four=data.id_last_four,
        operation_type=operation_type,
        reason=data.reason,
        operator_name=data.added_by,
    )

    action_label = "重新加入" if operation_type == BlacklistOperationType.RE_ADD else "添加"
    return MessageResponse(
        success=True,
        message=f"已{action_label}到黑名单",
        data={"id": entry.id, "operation_type": operation_type.value},
    )


@router.get("/", response_model=list[BlacklistResponse], summary="查询黑名单列表")
def list_blacklist(
    name: str = None,
    id_last_four: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Blacklist).filter(Blacklist.is_active == True)
    if name:
        query = query.filter(Blacklist.name == name)
    if id_last_four:
        query = query.filter(Blacklist.id_last_four == id_last_four)

    entries = query.order_by(Blacklist.created_at.desc()).offset(skip).limit(limit).all()
    return entries


@router.get("/{entry_id}", response_model=BlacklistWithOperationLogsResponse, summary="查询黑名单详情及操作日志")
def get_blacklist_detail(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(Blacklist).filter(Blacklist.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")

    logs = (
        db.query(BlacklistOperationLog)
        .filter(BlacklistOperationLog.blacklist_id == entry_id)
        .order_by(BlacklistOperationLog.created_at.desc())
        .all()
    )

    return BlacklistWithOperationLogsResponse(
        id=entry.id,
        name=entry.name,
        id_last_four=entry.id_last_four,
        phone=entry.phone,
        reason=entry.reason,
        added_by=entry.added_by,
        is_active=entry.is_active,
        created_at=entry.created_at,
        operation_logs=logs,
    )


@router.get("/{entry_id}/logs", response_model=list[BlacklistOperationLogResponse], summary="查询黑名单操作日志")
def get_operation_logs(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(Blacklist).filter(Blacklist.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")

    logs = (
        db.query(BlacklistOperationLog)
        .filter(BlacklistOperationLog.blacklist_id == entry_id)
        .order_by(BlacklistOperationLog.created_at.desc())
        .all()
    )
    return logs


@router.get("/logs/all", response_model=list[BlacklistOperationLogResponse], summary="查询全部黑名单操作日志")
def list_all_operation_logs(
    name: str = None,
    id_last_four: str = None,
    operation_type: BlacklistOperationType = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(BlacklistOperationLog)
    if name:
        query = query.filter(BlacklistOperationLog.name == name)
    if id_last_four:
        query = query.filter(BlacklistOperationLog.id_last_four == id_last_four)
    if operation_type:
        query = query.filter(BlacklistOperationLog.operation_type == operation_type)

    logs = query.order_by(BlacklistOperationLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs


@router.get("/timeline/{name}/{id_last_four}", response_model=BlacklistTimelineResponse, summary="按姓名+证件后四位查询完整操作时间线")
def get_blacklist_timeline(name: str, id_last_four: str, db: Session = Depends(get_db)):
    logs = (
        db.query(BlacklistOperationLog)
        .filter(
            BlacklistOperationLog.name == name,
            BlacklistOperationLog.id_last_four == id_last_four,
        )
        .order_by(BlacklistOperationLog.created_at.asc())
        .all()
    )

    if not logs:
        all_records = (
            db.query(Blacklist)
            .filter(
                Blacklist.name == name,
                Blacklist.id_last_four == id_last_four,
            )
            .all()
        )
        if not all_records:
            raise HTTPException(status_code=404, detail="未找到该人员的黑名单记录")

    active_record = (
        db.query(Blacklist)
        .filter(
            Blacklist.name == name,
            Blacklist.id_last_four == id_last_four,
            Blacklist.is_active == True,
        )
        .first()
    )

    if active_record:
        current_status = "在黑名单中"
    elif logs:
        current_status = "不在黑名单中（已移出）"
    else:
        current_status = "不在黑名单中（无历史记录）"

    return BlacklistTimelineResponse(
        name=name,
        id_last_four=id_last_four,
        total_operations=len(logs),
        current_status=current_status,
        operation_logs=logs,
    )


@router.delete("/{entry_id}", response_model=MessageResponse, summary="移出黑名单")
def remove_from_blacklist(
    entry_id: int,
    operator_name: str = None,
    remove_reason: str = "正常移出",
    db: Session = Depends(get_db),
):
    entry = db.query(Blacklist).filter(Blacklist.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")

    if not entry.is_active:
        raise HTTPException(status_code=400, detail="该人员已不在黑名单中")

    entry.is_active = False
    db.commit()

    _add_operation_log(
        db,
        blacklist_id=entry.id,
        name=entry.name,
        id_last_four=entry.id_last_four,
        operation_type=BlacklistOperationType.REMOVE,
        reason=remove_reason,
        operator_name=operator_name,
    )

    return MessageResponse(
        success=True,
        message=f"已将 {entry.name}（证件后四位 {entry.id_last_four}）从黑名单移除",
        data={"id": entry_id},
    )

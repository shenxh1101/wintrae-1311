from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Blacklist
from schemas import BlacklistCreate, BlacklistResponse, BlacklistCheckRequest, BlacklistCheckResponse, MessageResponse

router = APIRouter(prefix="/api/blacklist", tags=["黑名单校验"])


@router.post("/check", response_model=BlacklistCheckResponse, summary="校验访客是否在黑名单中")
def check_blacklist(data: BlacklistCheckRequest, db: Session = Depends(get_db)):
    query = db.query(Blacklist).filter(Blacklist.is_active == True, Blacklist.name == data.name)

    if data.id_last_four:
        query = query.filter(
            (Blacklist.id_last_four == data.id_last_four) | (Blacklist.id_last_four == None)
        )

    matches = query.all()
    return BlacklistCheckResponse(is_blacklisted=len(matches) > 0, matches=matches)


@router.post("/", response_model=MessageResponse, summary="添加黑名单记录")
def add_to_blacklist(data: BlacklistCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(Blacklist)
        .filter(Blacklist.name == data.name, Blacklist.is_active == True)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="该人员已在黑名单中")

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

    return MessageResponse(success=True, message="已添加到黑名单", data={"id": entry.id})


@router.get("/", response_model=list[BlacklistResponse], summary="查询黑名单列表")
def list_blacklist(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    entries = (
        db.query(Blacklist)
        .filter(Blacklist.is_active == True)
        .order_by(Blacklist.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return entries


@router.delete("/{entry_id}", response_model=MessageResponse, summary="移出黑名单")
def remove_from_blacklist(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(Blacklist).filter(Blacklist.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")

    entry.is_active = False
    db.commit()

    return MessageResponse(success=True, message="已从黑名单移除", data={"id": entry_id})

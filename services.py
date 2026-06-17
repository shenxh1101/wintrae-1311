from sqlalchemy.orm import Session
from models import Blacklist


def check_blacklist(db: Session, name: str, id_last_four: str | None = None) -> list[Blacklist]:
    query = db.query(Blacklist).filter(Blacklist.is_active == True, Blacklist.name == name)
    if id_last_four:
        query = query.filter(
            (Blacklist.id_last_four == id_last_four) | (Blacklist.id_last_four == None)
        )
    return query.all()

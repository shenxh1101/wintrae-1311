from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import appointment, visit, blacklist, notification, management, export, exceptions, timeout_reminder

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="园区访客管理系统 API",
    description="提供访客预约、员工审核、二维码凭证、到访签到、离园登记、黑名单校验和消息提醒等接口",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(appointment.router)
app.include_router(visit.router)
app.include_router(blacklist.router)
app.include_router(notification.router)
app.include_router(management.router)
app.include_router(export.router)
app.include_router(exceptions.router)
app.include_router(timeout_reminder.router)


@app.get("/", tags=["系统"])
def root():
    return {"service": "园区访客管理系统", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", tags=["系统"])
def health_check():
    return {"status": "ok"}

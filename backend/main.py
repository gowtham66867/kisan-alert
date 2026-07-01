import os
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from services.db import init_db
from routers import queries, alerts, admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kisan Alert — Smart Crop Advisory API",
    description="AI-powered crop advisory and alert system for Indian farmers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "?")
    logger.error(f"[{rid}] {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "request_id": rid})


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Kisan Alert API started")


app.include_router(queries.router)
app.include_router(alerts.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "Kisan Alert API", "version": "1.0.0"}


@app.get("/")
def root():
    return {
        "message": "Kisan Alert — Smart Water, Crop & Advisory System",
        "docs": "/docs",
        "endpoints": ["/query/text", "/query/photo", "/alerts/generate", "/alerts/recent"],
    }

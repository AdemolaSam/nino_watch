from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers import (
    advisories,
    climate,
    health,
    incidents,
    outlet,
    outlooks,
    regions,
    reports,
)
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="NiñoWatch API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(f"http_{exc.status_code}", str(exc.detail)),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return JSONResponse(
        status_code=422, content=error_body("validation_error", detail)
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    return JSONResponse(
        status_code=500, content=error_body("internal_error", "internal error")
    )


app.include_router(health.router, prefix="/api")
app.include_router(regions.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(climate.router, prefix="/api")
app.include_router(advisories.router, prefix="/api")
app.include_router(outlet.router, prefix="/api")
app.include_router(outlooks.router, prefix="/api")
app.include_router(reports.router, prefix="/api")

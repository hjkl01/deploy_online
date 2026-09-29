import logging
import time
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("deploy_online.http")


def install_http_handlers(app):
    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s 500 %.1fms request_id=%s",
                request.method,
                request.url.path,
                elapsed,
                request_id,
            )
            raise

        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if response.status_code >= 500:
            logger.error(
                "%s %s %s %.1fms request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
                request_id,
            )
        elif response.status_code >= 400:
            logger.warning(
                "%s %s %s %.1fms request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
                request_id,
            )
        else:
            logger.info(
                "%s %s %s %.1fms request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
                request_id,
            )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "request_id": request_id},
        )

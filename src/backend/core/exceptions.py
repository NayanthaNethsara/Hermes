import asyncio
import errno
import socket
from typing import Any, Iterator

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.backend.core.logging import get_logger

logger = get_logger("exceptions")

DATABASE_UNAVAILABLE_MESSAGE = (
    "The archive database is unavailable. Bring the Postgres service back up "
    "(docker compose up -d) and retry."
)
CACHE_UNAVAILABLE_MESSAGE = (
    "The cache service is unavailable. Bring the Redis service back up "
    "(docker compose up -d) and retry."
)
DEPENDENCY_UNAVAILABLE_MESSAGE = (
    "A required backend service is unreachable. Bring the supporting containers "
    "back up (docker compose up -d) and retry."
)
UPSTREAM_TIMEOUT_MESSAGE = "A backend service did not respond in time. Please retry."
UNEXPECTED_ERROR_MESSAGE = "The request failed because of an unexpected server error."

CONNECTIVITY_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    errno.ENETDOWN,
    errno.EPIPE,
    errno.ETIMEDOUT,
    errno.ENOTCONN,
}

CONNECTIVITY_MESSAGE_MARKERS = (
    "connect call failed",
    "connection refused",
    "connection reset",
    "connection closed",
    "cannot connect now",
    "server closed the connection",
    "is starting up",
    "is shutting down",
    "no route to host",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "too many connections",
    "couldn't get a connection",
    "pool is closed",
)

MAX_CAUSE_DEPTH = 10


class HermesException(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RetrievalThresholdError(HermesException):
    def __init__(self, message: str = "Retrieval confidence below required threshold") -> None:
        super().__init__(message=message, status_code=404)


class DocumentParsingError(HermesException):
    def __init__(self, message: str = "Document parsing and layout extraction failed") -> None:
        super().__init__(message=message, status_code=422)


class ModelInferenceError(HermesException):
    def __init__(self, message: str = "Language or vision model inference failure") -> None:
        super().__init__(message=message, status_code=502)


class ServiceUnavailableError(HermesException):
    def __init__(self, message: str = DEPENDENCY_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message=message, status_code=503)


class DatabaseUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = DATABASE_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message=message)


class CacheUnavailableError(ServiceUnavailableError):
    def __init__(self, message: str = CACHE_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(message=message)


def iter_exception_chain(error: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = error
    depth = 0
    while current is not None and depth < MAX_CAUSE_DEPTH and id(current) not in seen:
        seen.add(id(current))
        yield current
        depth += 1
        current = current.__cause__ or current.__context__


def is_connectivity_error(error: BaseException) -> bool:
    for link in iter_exception_chain(error):
        if isinstance(link, (ConnectionError, socket.gaierror, TimeoutError)):
            return True
        if isinstance(link, OSError) and link.errno in CONNECTIVITY_ERRNOS:
            return True
        text = str(link).lower()
        if any(marker in text for marker in CONNECTIVITY_MESSAGE_MARKERS):
            return True
    return False


def summarize_error(error: BaseException) -> str:
    """A single-line description, no traceback, safe for structured logs."""
    first_line = str(error).strip().splitlines()
    detail = first_line[0] if first_line else ""
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def error_response(
    request: Request,
    status_code: int,
    message: str,
    error_type: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    if status_code in {204, 304}:
        return Response(status_code=status_code, headers=headers)

    # `error` and `detail` are duplicated so both the web client (which reads
    # `error`) and any HTTP tooling (which reads `detail`) see the message.
    payload: dict[str, Any] = {
        "error": message,
        "detail": message,
        "message": message,
        "error_type": error_type,
        "path": str(request.url.path),
    }
    if extra:
        payload.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HermesException)
    async def handle_hermes_exception(
        request: Request, exc: HermesException
    ) -> Response:
        if exc.status_code >= 500:
            logger.warning(
                "hermes_exception",
                path=request.url.path,
                status_code=exc.status_code,
                error=summarize_error(exc),
            )
        return error_response(
            request,
            status_code=exc.status_code,
            message=exc.message,
            error_type=exc.__class__.__name__,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        request: Request, exc: SQLAlchemyError
    ) -> Response:
        if is_connectivity_error(exc):
            logger.warning(
                "database_unavailable",
                path=request.url.path,
                error=summarize_error(exc),
            )
            return error_response(
                request,
                status_code=503,
                message=DATABASE_UNAVAILABLE_MESSAGE,
                error_type="DatabaseUnavailableError",
            )

        logger.error(
            "database_query_failed",
            path=request.url.path,
            error=summarize_error(exc),
        )
        return error_response(
            request,
            status_code=500,
            message="The archive database rejected the request.",
            error_type="DatabaseError",
        )

    @app.exception_handler(RedisError)
    async def handle_cache_error(request: Request, exc: RedisError) -> Response:
        logger.warning(
            "cache_unavailable",
            path=request.url.path,
            error=summarize_error(exc),
        )
        return error_response(
            request,
            status_code=503,
            message=CACHE_UNAVAILABLE_MESSAGE,
            error_type="CacheUnavailableError",
        )

    @app.exception_handler(asyncio.TimeoutError)
    @app.exception_handler(TimeoutError)
    async def handle_timeout_error(request: Request, exc: BaseException) -> Response:
        logger.warning(
            "dependency_timed_out",
            path=request.url.path,
            error=summarize_error(exc),
        )
        return error_response(
            request,
            status_code=504,
            message=UPSTREAM_TIMEOUT_MESSAGE,
            error_type="UpstreamTimeoutError",
        )

    @app.exception_handler(OSError)
    async def handle_os_error(request: Request, exc: OSError) -> Response:
        # Raw socket failures reach here when a driver does not wrap them, which
        # is what asyncpg does for a refused Postgres connection. Other OSErrors
        # (a missing asset file, a full disk) are server faults, not outages.
        if is_connectivity_error(exc):
            logger.warning(
                "dependency_unreachable",
                path=request.url.path,
                error=summarize_error(exc),
            )
            return error_response(
                request,
                status_code=503,
                message=DEPENDENCY_UNAVAILABLE_MESSAGE,
                error_type="ServiceUnavailableError",
            )

        logger.error(
            "os_error_during_request",
            path=request.url.path,
            error=summarize_error(exc),
        )
        return error_response(
            request,
            status_code=500,
            message=UNEXPECTED_ERROR_MESSAGE,
            error_type=exc.__class__.__name__,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(
            request,
            status_code=exc.status_code,
            message=message,
            error_type="HTTPException",
            extra=None if isinstance(exc.detail, str) else {"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        return error_response(
            request,
            status_code=422,
            message="The request payload is invalid.",
            error_type="RequestValidationError",
            extra={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
        if is_connectivity_error(exc):
            logger.warning(
                "dependency_unreachable",
                path=request.url.path,
                error=summarize_error(exc),
            )
            return error_response(
                request,
                status_code=503,
                message=DEPENDENCY_UNAVAILABLE_MESSAGE,
                error_type="ServiceUnavailableError",
            )

        # Uvicorn re-raises past this handler and logs the traceback itself, so
        # only the one-line summary is emitted here.
        logger.error(
            "unhandled_request_error",
            path=request.url.path,
            error=summarize_error(exc),
        )
        return error_response(
            request,
            status_code=500,
            message=UNEXPECTED_ERROR_MESSAGE,
            error_type=exc.__class__.__name__,
        )

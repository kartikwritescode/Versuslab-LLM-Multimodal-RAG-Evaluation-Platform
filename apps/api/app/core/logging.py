import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable tracking current HTTP request ID for correlated log output
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include request ID if present in context or record
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        if req_id:
            log_entry["request_id"] = req_id

        # Include race ID if present
        race_id = getattr(record, "race_id", None)
        if race_id:
            log_entry["race_id"] = race_id

        # Include model ID if present
        model_id = getattr(record, "model_id", None)
        if model_id:
            log_entry["model_id"] = model_id

        # Include extra arbitrary attributes passed in extra={}
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id", "race_id", "model_id",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs and not k.startswith("_")}
        if extras:
            log_entry.update(extras)

        # Include traceback details if exception info is attached
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extracts or generates X-Request-ID and attaches it to request context and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(req_id)

        try:
            response = await call_next(request)
            response.headers["x-request-id"] = req_id
            return response
        finally:
            # Reset context variable after request completion
            request_id_ctx.reset(token)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configures the root and application loggers to emit JSON logs."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())

    root_logger = logging.getLogger()
    # Avoid duplicate handlers if called multiple times in test suites
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Suppress overly verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

"""API Error Handlers."""

# Standard Library
import typing as t

# Third Party
from litestar import Request, Response
from litestar.exceptions import ValidationException

# Project
from hyperglass.log import log
from hyperglass.state import use_state

# Local
from .metrics import record_query_error

__all__ = (
    "default_handler",
    "http_handler",
    "app_handler",
    "validation_handler",
)


def get_validation_exception_detail(exc: ValidationException) -> Response:
    data: dict[str, t.Any] = {
        "level": "error",
        "status_code": exc.status_code,
        "keywords": [],
        "output": repr(exc),
    }
    if isinstance(exc.extra, dict):
        data["output"] = "\n".join(f"{k}: {v!r}" for k, v in exc.extra.items())
        data["keywords"] = list(exc.extra)

    if isinstance(exc.extra, list):
        # Litestar reports each failed field as {"message": ..., "key": ...}.
        outputs = []
        kw = []
        for v in exc.extra:
            if isinstance(v, dict) and "key" in v:
                outputs = [*outputs, f"{v['key']}: {v.get('message', '')}"]
                kw = [*kw, v["key"]]
            else:
                outputs = [*outputs, str(v)]
        data["output"] = "\n".join(outputs)
        data["keywords"] = kw

    return Response(data, status_code=exc.status_code)


def default_handler(request: Request, exc: BaseException) -> Response:
    """Handle uncaught errors."""
    state = use_state()
    log.bind(method=request.method, path=request.url.path, detail=str(exc)).critical("Error")
    record_query_error(request, exc)
    return Response(
        {"output": state.params.messages.general, "level": "danger", "keywords": []},
        status_code=500,
    )


def http_handler(request: Request, exc: BaseException) -> Response:
    """Handle web server errors."""
    log.bind(method=request.method, path=request.url.path, detail=exc.detail).critical("HTTP Error")
    record_query_error(request, exc)
    return Response(
        {"output": exc.detail, "level": "danger", "keywords": []},
        status_code=exc.status_code,
    )


def app_handler(request: Request, exc: BaseException) -> Response:
    """Handle application errors."""
    log.bind(method=request.method, path=request.url.path, detail=exc.message).critical(
        "hyperglass Error"
    )
    record_query_error(request, exc)
    return Response(
        {"output": exc.message, "level": exc.level, "keywords": exc.keywords},
        status_code=exc.status_code,
    )


def validation_handler(request: Request, exc: ValidationException) -> Response:
    """Handle request validation errors raised by Litestar."""
    log.bind(method=request.method, path=request.url.path, detail=exc).critical("Validation Error")
    record_query_error(request, exc)
    return get_validation_exception_detail(exc)

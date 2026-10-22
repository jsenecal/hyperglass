"""Prometheus metrics.

Label values are restricted to validated identifiers (device and directive
IDs) and exception class names, never raw request input, so a client cannot
inflate label cardinality by submitting arbitrary locations or query types.
"""

# Standard Library
import re
import typing as t

# Third Party
from litestar import Request
from prometheus_client import Gauge, Counter, Histogram
from litestar.exceptions import HTTPException
from litestar.plugins.prometheus import PrometheusConfig, PrometheusController

# Project
from hyperglass.constants import __version__
from hyperglass.exceptions import HyperglassError

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.api import Query
    from hyperglass.models.config.metrics import Metrics

__all__ = (
    "QUERY_METRICS_OPT",
    "create_metrics",
    "error_reason",
    "record_query_cache",
    "record_query_duration",
    "record_query_error",
    "record_query_success",
    "set_query_labels",
)

# Route handler `opt` key marking a handler whose failures count as query errors.
QUERY_METRICS_OPT = "query_metrics"

# Key under `request.state` holding the labels of the query being handled.
_QUERY_LABELS_KEY = "hyperglass_query_labels"

# Label value for failures raised before the query is validated, when the
# device and query type are not yet known (or not trusted).
UNKNOWN = "unknown"

# Device queries routinely take several seconds, so the default
# prometheus_client buckets (which top out at 10s) are too coarse.
_QUERY_DURATION_BUCKETS = (0.25, 0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 45, 60, 90)

QUERIES = Counter(
    "hyperglass_queries",
    "Queries handled, by outcome.",
    ("device", "query_type", "status"),
)
QUERY_ERRORS = Counter(
    "hyperglass_query_errors",
    "Failed queries, by failure reason.",
    ("device", "query_type", "reason"),
)
QUERY_CACHE = Counter(
    "hyperglass_query_cache",
    "Query cache lookups, by result (hit, miss, or bypass when the query forces a refresh).",
    ("result",),
)
QUERY_DURATION = Histogram(
    "hyperglass_query_duration_seconds",
    "Time spent executing successful queries against devices (cache misses only).",
    ("device", "query_type"),
    buckets=_QUERY_DURATION_BUCKETS,
)
BUILD_INFO = Gauge(
    "hyperglass_build_info",
    "hyperglass build information.",
    ("version",),
    multiprocess_mode="max",
)
BUILD_INFO.labels(__version__).set(1)


def error_reason(exc: BaseException) -> str:
    """Get a bounded, snake_case failure reason from an exception."""
    if isinstance(exc, HyperglassError):
        return re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()
    if isinstance(exc, HTTPException) and exc.status_code < 500:
        return "invalid_request"
    return "internal_error"


def set_query_labels(request: Request, query: "Query") -> None:
    """Attach the validated query's labels to the request for error reporting."""
    request.state[_QUERY_LABELS_KEY] = (query.device.id, query.query_type)


def _query_labels(request: Request) -> t.Tuple[str, str]:
    return request.state.get(_QUERY_LABELS_KEY, (UNKNOWN, UNKNOWN))


def record_query_cache(result: t.Literal["hit", "miss", "bypass"]) -> None:
    """Record a query cache lookup."""
    QUERY_CACHE.labels(result).inc()


def record_query_duration(request: Request, seconds: float) -> None:
    """Record the device execution time of a successful query."""
    QUERY_DURATION.labels(*_query_labels(request)).observe(seconds)


def record_query_success(request: Request) -> None:
    """Record a successful query."""
    QUERIES.labels(*_query_labels(request), "success").inc()


def record_query_error(request: Request, exc: BaseException) -> None:
    """Record a failed query, if the failing route handles queries."""
    # Errors raised before routing (e.g. 404s) have no route handler.
    route_handler = request.scope.get("route_handler")
    if route_handler is None or not route_handler.opt.get(QUERY_METRICS_OPT, False):
        return
    device, query_type = _query_labels(request)
    QUERIES.labels(device, query_type, "error").inc()
    QUERY_ERRORS.labels(device, query_type, error_reason(exc)).inc()


def create_metrics(
    config: "Metrics", *, exclude: t.Sequence[str] = ()
) -> t.Tuple[PrometheusConfig, t.Type[PrometheusController]]:
    """Create the HTTP metrics middleware config and the metrics endpoint controller."""
    prometheus_config = PrometheusConfig(
        app_name="hyperglass",
        prefix="hyperglass_http",
        # Label by route template, not raw path, so per-ID routes like
        # /api/devices/{id} and /result/{share_id} don't explode cardinality.
        group_path=True,
        exclude=[f"^{re.escape(path)}$" for path in (config.path, *exclude)],
    )
    controller = type(
        "MetricsController",
        (PrometheusController,),
        {"path": config.path, "include_in_schema": False},
    )
    return prometheus_config, controller

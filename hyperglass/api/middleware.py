"""hyperglass API middleware."""

# Standard Library
import typing as t

# Third Party
from litestar import Request
from litestar.config.cors import CORSConfig
from litestar.config.compression import CompressionConfig

# Project
from hyperglass.state import use_state

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState

__all__ = ("create_cors_config", "recover_state", "COMPRESSION_CONFIG")

COMPRESSION_CONFIG = CompressionConfig(backend="brotli", brotli_gzip_fallback=True)

REQUEST_LOG_MESSAGE = "REQ"
RESPONSE_LOG_MESSAGE = "RES"
REQUEST_LOG_FIELDS = ("method", "path", "path_params", "query")
RESPONSE_LOG_FIELDS = ("status_code",)


async def recover_state(request: Request) -> None:
    """Wait for complete state recovery without blocking other requests."""
    await use_state().ensure_ready()


def create_cors_config(state: "HyperglassState") -> CORSConfig:
    """Create CORS configuration from parameters."""
    origins = state.params.cors_origins.copy()
    if state.settings.dev_mode:
        origins = [*origins, state.settings.dev_url, "http://localhost:3000"]

    return CORSConfig(
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

"""Validation model for cache config."""

# Local
from ..main import HyperglassModel


class Cache(HyperglassModel):
    """Public cache parameters."""

    timeout: int = 600
    show_text: bool = True
    share_enabled: bool = True
    share_timeout: int = 604800
    share_sliding: bool = False
    refresh_min_interval: int = 120
    history_enabled: bool = True
    history_limit: int = 10

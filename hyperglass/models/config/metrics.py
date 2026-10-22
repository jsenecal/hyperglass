"""Validation model for Prometheus metrics config."""

# Third Party
from pydantic import Field

# Local
from ..main import HyperglassModel
from ..fields import AnyUri


class Metrics(HyperglassModel):
    """Validation model for params.metrics."""

    enable: bool = Field(
        False,
        title="Enable",
        description="Expose Prometheus metrics. Restrict access to the metrics path at your reverse proxy or firewall, as it is unauthenticated.",
    )
    path: AnyUri = Field(
        "/metrics",
        title="Path",
        description="Path at which Prometheus metrics are exposed.",
    )

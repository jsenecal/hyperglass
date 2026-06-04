"""UI Configuration models."""

# Standard Library
import typing as t

# Local
from .main import HyperglassModel
from .config.web import WebPublic
from .config.params import ParamsPublic
from .config.messages import Messages

Alignment = t.Union[t.Literal["left"], t.Literal["center"], t.Literal["right"], None]
StructuredDataField = t.Tuple[str, str, Alignment]


class UICache(HyperglassModel):
    """UI projection of cache parameters (server-private fields omitted)."""

    timeout: int
    show_text: bool
    share_enabled: bool
    share_timeout: int
    refresh_min_interval: int
    history_enabled: bool
    history_limit: int


class UIDirective(HyperglassModel):
    """UI: Directive."""

    id: str
    name: str
    field_type: t.Union[str, None]
    groups: t.List[str]
    description: str
    info: t.Optional[str] = None
    options: t.Optional[t.List[t.Dict[str, t.Any]]] = None


class UILocation(HyperglassModel):
    """UI: Location (Device)."""

    id: str
    name: str
    group: t.Optional[str] = None
    avatar: t.Optional[str] = None
    description: t.Optional[str] = None
    directives: t.List[UIDirective] = []


class UIDevices(HyperglassModel):
    """UI: Devices."""

    group: t.Optional[str] = None
    locations: t.List[UILocation] = []


class UIContent(HyperglassModel):
    """UI: Content."""

    credit: str
    greeting: str


class UIParameters(ParamsPublic, HyperglassModel):
    """UI Configuration Parameters."""

    cache: UICache
    web: WebPublic
    messages: Messages
    version: str
    devices: t.List[UIDevices] = []
    parsed_data_fields: t.Tuple[StructuredDataField, ...]
    content: UIContent
    developer_mode: bool

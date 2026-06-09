"""hyperglass API."""

# Standard Library
import re
import logging

# Third Party
from litestar import Litestar, get
from litestar.params import FromPath
from litestar.openapi import OpenAPIConfig
from litestar.response import File
from litestar.openapi.plugins import StoplightRenderPlugin
from litestar.exceptions import HTTPException, NotFoundException, ValidationException
from litestar.static_files import create_static_files_router

# Project
from hyperglass.state import use_state
from hyperglass.constants import __version__
from hyperglass.exceptions import HyperglassError

# Local
from .events import check_redis
from .routes import info, query, device, devices, queries, share_get, share_create
from .middleware import COMPRESSION_CONFIG, create_cors_config
from .error_handlers import app_handler, http_handler, default_handler, validation_handler

__all__ = ("app",)

_SHARE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{11}$")

STATE = use_state()

UI_DIR = STATE.settings.static_path / "ui"
IMAGES_DIR = STATE.settings.static_path / "images"


OPEN_API = OpenAPIConfig(
    title=STATE.params.docs.title.format(site_title=STATE.params.site_title),
    version=__version__,
    description=STATE.params.docs.description,
    path=STATE.params.docs.path,
    # Stoplight Elements served at the OpenAPI root path (the first/only
    # render plugin), replacing the deprecated root_schema_site="elements".
    render_plugins=[StoplightRenderPlugin()],
)


@get("/result/{share_id:str}", include_in_schema=False)
async def share_view_html(share_id: FromPath[str]) -> File:
    """Serve the SPA shell (index.html) for share result URLs.

    Litestar's static-files html_mode serves 404.html (the Next.js error
    page) for unknown paths rather than index.html, which breaks client-side
    routing to /result/<id>. This explicit handler ensures the SPA shell is
    returned so the Next.js client router can hydrate the correct page.
    """
    if not _SHARE_ID_RE.match(share_id):
        raise NotFoundException(detail="Invalid share ID format.")
    index = UI_DIR / "index.html"
    if not index.exists():
        raise NotFoundException(detail="UI not built.")
    # content_disposition_type defaults to "attachment", which makes browsers
    # download the SPA shell instead of rendering it; force inline so /result/<id>
    # loads in-page and the client router can hydrate.
    return File(path=index, media_type="text/html", content_disposition_type="inline")


HANDLERS = [
    device,
    devices,
    queries,
    info,
    query,
    share_create,
    share_get,
    share_view_html,
]

if not STATE.settings.disable_ui:
    HANDLERS = [
        *HANDLERS,
        create_static_files_router(
            path="/images", directories=[IMAGES_DIR], name="images", include_in_schema=False
        ),
        create_static_files_router(
            path="/", directories=[UI_DIR], name="ui", html_mode=True, include_in_schema=False
        ),
    ]


app = Litestar(
    route_handlers=HANDLERS,
    exception_handlers={
        HTTPException: http_handler,
        HyperglassError: app_handler,
        ValidationException: validation_handler,
        Exception: default_handler,
    },
    on_startup=[check_redis],
    debug=STATE.settings.debug,
    cors_config=create_cors_config(state=STATE),
    compression_config=COMPRESSION_CONFIG,
    openapi_config=OPEN_API if STATE.params.docs.enable else None,
)

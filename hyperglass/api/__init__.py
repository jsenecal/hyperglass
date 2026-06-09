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
    """Serve the exported result page for share URLs.

    Share IDs are minted at runtime, so `next export` can't pre-render a file
    per ID. The UI emits a single placeholder export at `result/shared.html`
    whose bundle is the `/result/[id]` page; we serve it for every valid
    /result/<id> request and the client parses the real ID from the URL.

    We must NOT fall back to index.html here: index.html is the home page's
    export (its __NEXT_DATA__ pins the route to "/"), so the browser would
    render the landing page instead of the result page.
    """
    if not _SHARE_ID_RE.match(share_id):
        raise NotFoundException(detail="Invalid share ID format.")
    result_page = UI_DIR / "result" / "shared.html"
    if not result_page.exists():
        raise NotFoundException(detail="UI not built.")
    # content_disposition_type defaults to "attachment", which makes browsers
    # download the page instead of rendering it; force inline so /result/<id>
    # loads in-page and the client router can hydrate.
    return File(path=result_page, media_type="text/html", content_disposition_type="inline")


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

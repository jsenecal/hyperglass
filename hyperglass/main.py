"""Start hyperglass."""

# Standard Library
import os
import sys
import atexit
import shutil
import typing as t
import asyncio
import logging
import tempfile
from pathlib import Path

# Third Party
import uvicorn

# Local
from .log import LibInterceptHandler, init_logger, enable_file_logging, enable_syslog_logging
from .util import get_node_version
from .constants import MIN_NODE_VERSION, MIN_PYTHON_VERSION, __version__

# Ensure the Python version meets the minimum requirements.
pretty_version = ".".join(tuple(str(v) for v in MIN_PYTHON_VERSION))
if sys.version_info < MIN_PYTHON_VERSION:
    raise RuntimeError(f"Python {pretty_version}+ is required.")

# Ensure the NodeJS version meets the minimum requirements.
node_major, node_minor, node_patch = get_node_version()

if node_major < MIN_NODE_VERSION:
    installed = ".".join(str(v) for v in (node_major, node_minor, node_patch))
    raise RuntimeError(f"NodeJS {MIN_NODE_VERSION!s}+ is required (version {installed} installed)")


# Local
from .state import use_state
from .settings import Settings

LOG_LEVEL = logging.INFO if Settings.debug is False else logging.DEBUG
logging.basicConfig(handlers=[LibInterceptHandler()], level=0, force=True)
log = init_logger(LOG_LEVEL)


async def build_ui() -> bool:
    """Perform a UI build prior to starting the application."""
    # Local
    from .frontend import build_frontend

    state = use_state()
    await build_frontend(
        dev_mode=Settings.dev_mode,
        dev_url=Settings.dev_url,
        prod_url=Settings.prod_url,
        params=state.ui_params,
        app_path=Settings.app_path,
    )
    return True


def register_all_plugins() -> None:
    """Validate and register configured plugins."""

    # Local
    from .plugins import register_plugin, init_builtin_plugins

    state = use_state()

    # Register built-in plugins.
    init_builtin_plugins()

    failures = ()

    # Register external directive-based plugins (defined in directives).
    for plugin_file, directives in state.devices.directive_plugins().items():
        failures += register_plugin(plugin_file, directives=directives)

    # Register external global/common plugins (defined in config).
    for plugin_file in state.params.common_plugins():
        failures += register_plugin(plugin_file, common=True)

    for failure in failures:
        log.bind(plugin=failure).warning("Invalid hyperglass plugin")


def unregister_all_plugins() -> None:
    """Unregister all plugins."""
    # Local
    from .plugins import InputPluginManager, OutputPluginManager

    for manager in (InputPluginManager, OutputPluginManager):
        manager().reset()


def prepare_metrics_dir() -> Path:
    """Prepare prometheus_client's multiprocess directory.

    Each uvicorn worker is a separate process with its own metric values, so
    worker processes write them to a shared directory that the metrics
    endpoint aggregates. prometheus_client selects this mode when it is first
    imported, so this must run before any worker imports it (i.e. before the
    app is imported), and the directory must be emptied between runs.
    """
    configured = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

    if configured is None:
        path = Path(tempfile.mkdtemp(prefix="hyperglass-metrics-"))
        atexit.register(shutil.rmtree, path, ignore_errors=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(path)
        return path

    path = Path(configured)
    path.mkdir(parents=True, exist_ok=True)
    for stale in path.glob("*.db"):
        stale.unlink()
    return path


def start(*, log_level: t.Union[str, int], workers: int) -> None:
    """Start hyperglass via ASGI server."""

    register_all_plugins()

    if use_state("params").metrics.enable:
        metrics_dir = prepare_metrics_dir()
        log.bind(directory=str(metrics_dir)).debug("Prepared metrics directory")

    if not Settings.disable_ui:
        asyncio.run(build_ui())

    uvicorn.run(
        app="hyperglass.api:app",
        host=str(Settings.host),
        port=Settings.port,
        workers=workers,
        log_level=log_level,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "format": "%(message)s",
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "format": "%(message)s",
                },
            },
            "handlers": {
                "default": {"formatter": "default", "class": "hyperglass.log.LibInterceptHandler"},
                "access": {"formatter": "access", "class": "hyperglass.log.LibInterceptHandler"},
            },
            "loggers": {
                "uvicorn.error": {"level": "ERROR", "handlers": ["default"], "propagate": False},
                "uvicorn.access": {"level": "INFO", "handlers": ["access"], "propagate": False},
            },
        },
    )


def run(workers: int = None):
    """Run hyperglass."""
    # Local
    from .configuration import init_user_config

    try:
        log.debug(repr(Settings))

        state = use_state()
        state.clear()

        init_user_config()

        enable_file_logging(
            directory=state.params.logging.directory,
            max_size=state.params.logging.max_size,
            log_format=state.params.logging.format,
            level=LOG_LEVEL,
        )

        if state.params.logging.syslog is not None:
            enable_syslog_logging(
                host=state.params.logging.syslog.host,
                port=state.params.logging.syslog.port,
            )
        _workers = workers if workers is not None else Settings.workers

        log.bind(
            version=__version__,
            listening=f"http://{Settings.bind()}",
            app_path=f"{Settings.app_path.absolute()!s}",
            container=Settings.container,
            original_app_path=f"{Settings.original_app_path.absolute()!s}",
            workers=_workers,
        ).info(
            "Starting hyperglass",
        )

        start(log_level=LOG_LEVEL, workers=_workers)
        log.bind(version=__version__).critical("Stopping hyperglass")
    except Exception as error:
        log.critical(error)
        # Handle app exceptions.
        if not Settings.dev_mode:
            state = use_state()
            state.clear()
            log.debug("Cleared hyperglass state")
        unregister_all_plugins()
        raise error
    except (SystemExit, BaseException):
        unregister_all_plugins()
        sys.exit(4)


if __name__ == "__main__":
    run()

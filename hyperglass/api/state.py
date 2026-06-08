"""hyperglass state dependencies."""

# Project
from hyperglass.state import use_state


async def get_state():
    """Get hyperglass state as a dependency."""
    # No parameters: a parameter here would be inferred as a request query
    # parameter by Litestar (the deprecated inferred style), exposing an
    # unintended `?attr=` surface that could coerce a state subset.
    return use_state()


async def get_params():
    """Get hyperglass params as FastAPI dependency."""
    return use_state("params")


async def get_devices():
    """Get hyperglass devices as FastAPI dependency."""
    return use_state("devices")


async def get_ui_params():
    """Get hyperglass ui_params as FastAPI dependency."""
    return use_state("ui_params")

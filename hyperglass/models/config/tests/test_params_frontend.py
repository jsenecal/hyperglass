"""Tests for Params.frontend() projection."""

# Project
from hyperglass.models.config.params import Params


def test_frontend_includes_share_fields():
    p = Params()
    out = p.frontend()
    assert "cache" in out
    cache = out["cache"]
    assert "share_enabled" in cache
    assert "share_timeout" in cache
    assert "refresh_min_interval" in cache


def test_frontend_excludes_private_share_sliding():
    p = Params()
    cache = p.frontend()["cache"]
    assert "share_sliding" not in cache


def test_ui_params_cache_projection_excludes_private_fields():
    """UIParameters.export_dict must not expose server-private cache fields."""
    # Project
    from hyperglass.models.config.devices import Devices
    from hyperglass.configuration.validate import init_ui_params

    ui = init_ui_params(params=Params(), devices=Devices())
    cache = ui.export_dict(by_alias=True)["cache"]
    assert set(cache) == {
        "timeout",
        "showText",
        "shareEnabled",
        "shareTimeout",
        "refreshMinInterval",
        "historyEnabled",
        "historyLimit",
    }


def test_ui_params_export_excludes_public_url():
    """public_url must not be present in the UI bundle."""
    # Project
    from hyperglass.models.config.devices import Devices
    from hyperglass.configuration.validate import init_ui_params

    ui = init_ui_params(params=Params(), devices=Devices())
    assert "publicUrl" not in ui.export_dict(by_alias=True)


def test_frontend_includes_cache_history_fields():
    """Cache history fields must be projected to frontend()."""
    p = Params()
    fe = p.frontend()
    assert fe["cache"]["history_enabled"] is True
    assert fe["cache"]["history_limit"] == 10

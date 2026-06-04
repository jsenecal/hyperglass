"""Tests for the per-directive history opt-out field."""

from hyperglass.models.directive import Directive


def _directive(**kwargs):
    base = {"id": "test", "name": "Test", "field": None}
    base.update(kwargs)
    return Directive(**base)


def test_directive_history_defaults_true():
    assert _directive().history is True


def test_directive_history_can_be_disabled():
    assert _directive(history=False).history is False


def test_directive_frontend_includes_history():
    fe = _directive(history=False).frontend()
    assert fe["history"] is False

    fe_default = _directive().frontend()
    assert fe_default["history"] is True

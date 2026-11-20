"""Tests for API error handlers."""

# Third Party
import pytest
from litestar.exceptions import ValidationException

# Local
from ..error_handlers import get_validation_exception_detail


@pytest.mark.parametrize(
    "body",
    (
        pytest.param({"queryTarget": "192.0.2.0/24"}, id="missing-fields"),
        pytest.param({"queryLocation": 1, "queryType": [], "queryTarget": {}}, id="wrong-types"),
    ),
)
def test_validation_error_returns_400(client, body):
    response = client.post("/api/query", json=body)

    assert response.status_code == 400
    data = response.json()
    assert data["level"] == "error"
    assert data["status_code"] == 400


def test_validation_error_names_failed_fields(client):
    response = client.post("/api/query", json={"queryTarget": "192.0.2.0/24"})

    data = response.json()
    assert data["keywords"] == ["queryLocation", "queryType"]
    assert data["output"] == "queryLocation: Field required\nqueryType: Field required"


def test_validation_detail_accepts_dict_extra():
    exc = ValidationException(extra={"queryLocation": "Field required"})

    response = get_validation_exception_detail(exc)

    assert response.status_code == 400
    assert response.content["keywords"] == ["queryLocation"]
    assert response.content["output"] == "queryLocation: 'Field required'"


def test_validation_detail_keeps_unrecognised_list_items():
    exc = ValidationException(extra=["something went wrong"])

    response = get_validation_exception_detail(exc)

    assert response.content["output"] == "something went wrong"
    assert response.content["keywords"] == []

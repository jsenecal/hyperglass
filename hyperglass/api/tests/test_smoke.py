"""Smoke test that the API test scaffolding works."""


def test_devices_endpoint_returns_seeded_device(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    payload = response.json()
    assert any(d.get("name") == "test1" for d in payload)

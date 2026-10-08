"""The guard against cross-site requests and DNS rebinding."""

from starlette.testclient import TestClient

from folio import server


def client():
    server.STATE["token"] = "secret-token"
    app = server.build_app(7381)
    return TestClient(app, base_url="http://127.0.0.1:7381")


def test_rejects_foreign_host():
    c = client()
    assert c.get("/api/ping", headers={"Host": "evil.example:7381"}).status_code == 403


def test_rejects_foreign_origin():
    c = client()
    r = c.post("/api/open", json={"id": 1}, headers={"Origin": "http://evil.example", "X-Folio-Token": "secret-token"})
    assert r.status_code == 403


def test_requires_token():
    c = client()
    assert c.post("/api/open", json={"id": 1}).status_code == 403
    assert c.post("/api/open", json={"id": 1}, headers={"X-Folio-Token": "wrong"}).status_code == 403


def test_actions_refuse_get():
    c = client()
    assert c.get("/api/open", headers={"X-Folio-Token": "secret-token"}).status_code == 405


def test_ping_from_same_origin():
    c = client()
    assert c.get("/api/ping", headers={"Origin": "http://127.0.0.1:7381"}).status_code == 200

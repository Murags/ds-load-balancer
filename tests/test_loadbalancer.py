"""Endpoint/validation tests for the Task 3 load balancer.

The docker layer and health probing are mocked, so these run without a real
docker daemon. Run from the loadbalancer project:
    cd loadbalancer && uv run pytest
"""
import pytest
from fastapi.testclient import TestClient

import loadbalancer as lb


class _FakeResp:
    def __init__(self, status_code, content=b"", content_type="application/json"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


class _FakeClient:
    """Stand-in for the httpx client used when proxying requests."""

    def __init__(self, status_code=200, content=b'{"ok": true}'):
        self._status = status_code
        self._content = content

    async def get(self, url, timeout=None):
        return _FakeResp(self._status, self._content)

    async def aclose(self):
        pass


@pytest.fixture
def client(monkeypatch):
    spawned: set[str] = set()

    async def fake_spawn(hostname, image, network):
        spawned.add(hostname)
        return "cid-" + hostname

    async def fake_remove(hostname):
        spawned.discard(hostname)

    async def fake_list():
        return []

    async def fake_wait(hostname):
        return True

    async def fake_loop():
        return

    monkeypatch.setattr(lb.dm, "spawn_server", fake_spawn)
    monkeypatch.setattr(lb.dm, "remove_server", fake_remove)
    monkeypatch.setattr(lb.dm, "list_servers", fake_list)
    monkeypatch.setattr(lb, "_wait_healthy", fake_wait)
    monkeypatch.setattr(lb, "_health_loop", fake_loop)
    monkeypatch.setattr(lb, "ring", lb.ConsistentHashMap())  # fresh ring per test
    with TestClient(lb.app) as c:  # triggers lifespan -> bootstraps N=3
        yield c


# --------------------------------------------------------------------------- #
# /rep
# --------------------------------------------------------------------------- #
def test_rep_initial(client):
    body = client.get("/rep").json()
    assert body["status"] == "successful"
    assert body["message"]["N"] == 3
    assert set(body["message"]["replicas"]) == {"server1", "server2", "server3"}


# --------------------------------------------------------------------------- #
# /add
# --------------------------------------------------------------------------- #
def test_add_preferred_and_random(client):
    r = client.post("/add", json={"n": 2, "hostnames": ["S5"]})
    assert r.status_code == 200
    reps = r.json()["message"]["replicas"]
    assert "S5" in reps and len(reps) == 5


def test_add_too_many_hostnames(client):
    r = client.post("/add", json={"n": 1, "hostnames": ["a", "b"]})
    assert r.status_code == 400
    assert "more than newly added instances" in r.json()["message"]


def test_add_duplicate_hostnames(client):
    r = client.post("/add", json={"n": 2, "hostnames": ["x", "x"]})
    assert r.status_code == 400
    assert "Duplicate" in r.json()["message"]


def test_add_existing_hostname(client):
    r = client.post("/add", json={"n": 1, "hostnames": ["server1"]})
    assert r.status_code == 400
    assert "already exists" in r.json()["message"]


def test_add_invalid_n(client):
    assert client.post("/add", json={"n": 0}).status_code == 400
    assert client.post("/add", json={"hostnames": ["a"]}).status_code == 400


# --------------------------------------------------------------------------- #
# /rm
# --------------------------------------------------------------------------- #
def test_rm_preferred(client):
    r = client.request("DELETE", "/rm", json={"n": 1, "hostnames": ["server2"]})
    assert r.status_code == 200
    reps = r.json()["message"]["replicas"]
    assert "server2" not in reps and len(reps) == 2


def test_rm_too_many_hostnames(client):
    r = client.request("DELETE", "/rm", json={"n": 1, "hostnames": ["a", "b"]})
    assert r.status_code == 400
    assert "more than removable instances" in r.json()["message"]


def test_rm_duplicate_hostnames(client):
    r = client.request("DELETE", "/rm", json={"n": 2, "hostnames": ["server1", "server1"]})
    assert r.status_code == 400
    assert "Duplicate" in r.json()["message"]


def test_rm_more_than_present(client):
    r = client.request("DELETE", "/rm", json={"n": 99})
    assert r.status_code == 400
    assert "more instances than are present" in r.json()["message"]


def test_rm_unknown_hostname(client):
    r = client.request("DELETE", "/rm", json={"n": 1, "hostnames": ["ghost"]})
    assert r.status_code == 400
    assert "not a managed replica" in r.json()["message"]


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def test_route_unknown_path_returns_400(client, monkeypatch):
    monkeypatch.setattr(lb, "_client", _FakeClient(status_code=404))
    r = client.get("/nope")
    assert r.status_code == 400
    assert "does not exist in server replicas" in r.json()["message"]


def test_route_proxies_success(client, monkeypatch):
    monkeypatch.setattr(
        lb, "_client",
        _FakeClient(status_code=200, content=b'{"message": "hi", "status": "successful"}'),
    )
    r = client.get("/home")
    assert r.status_code == 200
    assert r.json()["status"] == "successful"

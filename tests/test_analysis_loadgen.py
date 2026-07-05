import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

import loadgen


def test_replicas_from_response_accepts_expected_shape():
    response = httpx.Response(
        200,
        json={"message": {"replicas": ["server1", "server2"]}},
        request=httpx.Request("GET", "http://lb/rep"),
    )

    assert loadgen._replicas_from_response(response) == ["server1", "server2"]


def test_replicas_from_response_rejects_non_200():
    response = httpx.Response(
        503,
        json={"message": "starting"},
        request=httpx.Request("GET", "http://lb/rep"),
    )

    with pytest.raises(httpx.HTTPStatusError):
        loadgen._replicas_from_response(response)


def test_replicas_from_response_rejects_bad_shape():
    response = httpx.Response(
        200,
        json={"message": {"replicas": "server1"}},
        request=httpx.Request("GET", "http://lb/rep"),
    )

    with pytest.raises(ValueError, match="replica list"):
        loadgen._replicas_from_response(response)

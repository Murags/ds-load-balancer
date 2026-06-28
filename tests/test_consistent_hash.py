"""Unit tests for the Task 2 consistent hash ring.

Run from the loadbalancer project so `hashing` is importable:
    cd loadbalancer && uv run pytest
"""
import random

import pytest

from hashing import (
    ConsistentHashMap,
    default_request_hash,
    default_virtual_hash,
)


# --------------------------------------------------------------------------- #
# Defaults / parameters
# --------------------------------------------------------------------------- #
def test_assignment_defaults():
    ch = ConsistentHashMap()
    assert ch.M == 512
    assert ch.K == 9  # log2(512)


def test_hash_functions_match_spec():
    # H(i) = i^2 + 2i + 17
    assert default_request_hash(0) == 17
    assert default_request_hash(3) == 9 + 6 + 17
    # Phi(i, j) = i^2 + j^2 + 2j + 25
    assert default_virtual_hash(0, 0) == 25
    assert default_virtual_hash(2, 3) == 4 + 9 + 6 + 25


# --------------------------------------------------------------------------- #
# Placement / virtual nodes
# --------------------------------------------------------------------------- #
def test_add_places_k_virtual_nodes():
    ch = ConsistentHashMap()
    ch.add_server("Server 1")
    assert len(ch._occupied) == ch.K
    assert ch._occupied == sorted(ch._occupied)  # kept sorted


def test_three_servers_have_3k_distinct_slots():
    ch = ConsistentHashMap()
    for name in ("Server 1", "Server 2", "Server 3"):
        ch.add_server(name)
    # No two virtual nodes share a slot (probing resolved any collisions).
    assert len(ch._occupied) == 3 * ch.K
    assert len(set(ch._occupied)) == len(ch._occupied)


def test_ids_are_sequential():
    ch = ConsistentHashMap()
    assert ch.add_server("a") == 1
    assert ch.add_server("b") == 2
    assert ch.server_id("a") == 1


def test_duplicate_add_rejected():
    ch = ConsistentHashMap()
    ch.add_server("dup")
    with pytest.raises(ValueError):
        ch.add_server("dup")


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #
def test_empty_ring_returns_none():
    assert ConsistentHashMap().get_server(123456) is None


def test_lookup_is_deterministic():
    ch = ConsistentHashMap()
    for name in ("S1", "S2", "S3"):
        ch.add_server(name)
    rid = 132574
    assert ch.get_server(rid) == ch.get_server(rid)


def test_every_request_maps_to_a_real_server():
    ch = ConsistentHashMap()
    names = {"S1", "S2", "S3"}
    for n in names:
        ch.add_server(n)
    rng = random.Random(42)
    for _ in range(2000):
        rid = rng.randint(100000, 999999)
        assert ch.get_server(rid) in names


def test_clockwise_wraparound():
    # A request whose slot is past the last occupied slot wraps to the first.
    ch = ConsistentHashMap()
    ch.add_server("only")
    max_slot = max(ch._occupied)
    # Find a request id whose slot is strictly greater than the largest node.
    rid = next(
        r for r in range(1000000)
        if default_request_hash(r) % ch.M > max_slot
    )
    assert ch.get_server(rid) == "only"  # wrapped around to the single server


# --------------------------------------------------------------------------- #
# Removal / failure
# --------------------------------------------------------------------------- #
def test_remove_frees_slots_and_reroutes():
    ch = ConsistentHashMap()
    for n in ("S1", "S2", "S3"):
        ch.add_server(n)
    before = len(ch._occupied)
    ch.remove_server("S2")
    assert "S2" not in ch
    assert len(ch._occupied) == before - ch.K
    # Requests that previously hit S2 must now resolve to a surviving server.
    rng = random.Random(7)
    survivors = {"S1", "S3"}
    for _ in range(2000):
        assert ch.get_server(rng.randint(100000, 999999)) in survivors


def test_remove_unknown_raises():
    with pytest.raises(KeyError):
        ConsistentHashMap().remove_server("ghost")


# --------------------------------------------------------------------------- #
# Distribution sanity (loose — not asserting perfect balance)
# --------------------------------------------------------------------------- #
def test_load_is_shared_across_servers():
    ch = ConsistentHashMap()
    names = ["S1", "S2", "S3"]
    for n in names:
        ch.add_server(n)
    counts = {n: 0 for n in names}
    rng = random.Random(2024)
    total = 10000
    for _ in range(total):
        counts[ch.get_server(rng.randint(100000, 999999))] += 1
    # Every server should carry a non-trivial share; none should hoard it all.
    for n in names:
        assert counts[n] > 0
        assert counts[n] < total * 0.9


# --------------------------------------------------------------------------- #
# A-4: custom hash functions are honoured
# --------------------------------------------------------------------------- #
def test_custom_hash_functions_are_used():
    # Force every server's virtual nodes and every request onto fixed slots so
    # the outcome is fully determined by the injected functions.
    ch = ConsistentHashMap(
        request_hash=lambda i: 100,
        virtual_hash=lambda i, j: 50,  # all nodes cluster from slot 50 (probed)
    )
    ch.add_server("only")
    assert ch.get_server(999999) == "only"
    assert min(ch._occupied) == 50  # first node landed exactly on the forced slot


def test_quadratic_probing_no_collisions():
    ch = ConsistentHashMap(probing="quadratic")
    for n in ("S1", "S2", "S3", "S4"):
        ch.add_server(n)
    assert len(set(ch._occupied)) == 4 * ch.K

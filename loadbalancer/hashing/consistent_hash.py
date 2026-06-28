"""Task 2: consistent hashing.

A fixed-size consistent hash ring that maps client requests to server replicas.
Each physical server is represented by K *virtual* nodes spread around the ring
so that load stays balanced — including after a server is added or fails (the
requests of a downed server scatter across the survivors instead of all landing
on a single neighbour).

Assignment defaults:
    M (slots)              = 512
    K (virtuals / server)  = 9      (= log2 512)
    H(i)      = i^2 + 2i + 17        request id  -> ring position (pre-mod)
    Phi(i, j) = i^2 + j^2 + 2j + 25  virtual node (i, j) -> ring position

  where i is the server's integer id and j in [0, K) is the virtual replica
  index. Final slot = position % M. Both hash functions are injectable so the
  analysis task (A-4) can swap them and re-measure the distribution.

Collisions (two virtual nodes mapping to the same slot) are resolved with
linear or quadratic probing.
"""
from __future__ import annotations

import bisect
from typing import Callable, Optional


def default_request_hash(i: int) -> int:
    """H(i) = i^2 + 2i + 17 — maps a request id to a ring position (pre-mod)."""
    return i * i + 2 * i + 17


def default_virtual_hash(i: int, j: int) -> int:
    """Phi(i, j) = i^2 + j^2 + 2j + 25 — maps virtual node (i, j) to a position."""
    return i * i + j * j + 2 * j + 25


class ConsistentHashMap:
    """A consistent hash ring with virtual nodes and collision probing."""

    def __init__(
        self,
        num_slots: int = 512,
        virtuals_per_server: int = 9,
        request_hash: Callable[[int], int] = default_request_hash,
        virtual_hash: Callable[[int, int], int] = default_virtual_hash,
        probing: str = "linear",
    ) -> None:
        if probing not in ("linear", "quadratic"):
            raise ValueError("probing must be 'linear' or 'quadratic'")
        self.M = num_slots
        self.K = virtuals_per_server
        self._request_hash = request_hash
        self._virtual_hash = virtual_hash
        self._probing = probing

        # slot index -> server name occupying it (None if free)
        self._slots: list[Optional[str]] = [None] * num_slots
        # sorted list of occupied slot indices (for clockwise lookup via bisect)
        self._occupied: list[int] = []
        # server name -> the slot indices it occupies
        self._server_slots: dict[str, list[int]] = {}
        # server name -> integer id i used by the virtual hash
        self._server_ids: dict[str, int] = {}
        # monotonically increasing id allocator (ids are never reused)
        self._next_id = 1

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def servers(self) -> list[str]:
        """Names of the servers currently on the ring (insertion order)."""
        return list(self._server_ids.keys())

    def server_id(self, name: str) -> int:
        """Integer id assigned to a server (the `i` fed to the virtual hash)."""
        return self._server_ids[name]

    def __len__(self) -> int:
        return len(self._server_ids)

    def __contains__(self, name: str) -> bool:
        return name in self._server_ids

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def add_server(self, name: str) -> int:
        """Place a server's K virtual nodes on the ring. Returns its integer id."""
        if name in self._server_ids:
            raise ValueError(f"server {name!r} already present")

        i = self._next_id
        self._next_id += 1
        self._server_ids[name] = i

        slots: list[int] = []
        for j in range(self.K):
            base = self._virtual_hash(i, j) % self.M
            slot = self._probe_slot(base)
            self._slots[slot] = name
            bisect.insort(self._occupied, slot)
            slots.append(slot)
        self._server_slots[name] = slots
        return i

    def remove_server(self, name: str) -> None:
        """Remove a server and free all of its virtual node slots."""
        if name not in self._server_ids:
            raise KeyError(name)
        for slot in self._server_slots.pop(name):
            self._slots[slot] = None
            idx = bisect.bisect_left(self._occupied, slot)
            self._occupied.pop(idx)
        del self._server_ids[name]

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #
    def get_server(self, request_id: int) -> Optional[str]:
        """Return the server handling `request_id` (clockwise-nearest node)."""
        if not self._occupied:
            return None
        slot = self._request_hash(request_id) % self.M
        # First occupied slot at or clockwise-after `slot`; wrap around if none.
        idx = bisect.bisect_left(self._occupied, slot)
        if idx == len(self._occupied):
            idx = 0
        return self._slots[self._occupied[idx]]

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _probe_slot(self, base: int) -> int:
        """Find the next free slot at/after `base` using the configured probing.

        Linear probing visits every slot and is guaranteed to find a free one if
        the ring isn't full. Quadratic probing reduces clustering but may not
        visit every slot, so we cap the search at M steps and raise if full.
        """
        for step in range(self.M):
            if self._probing == "linear":
                slot = (base + step) % self.M
            else:  # quadratic
                slot = (base + step * step) % self.M
            if self._slots[slot] is None:
                return slot
        raise RuntimeError("consistent hash ring is full — cannot place virtual node")

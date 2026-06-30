"""Consistent hashing package (Task 2)."""
from .consistent_hash import (
    ConsistentHashMap,
    default_request_hash,
    default_virtual_hash,
)

__all__ = [
    "ConsistentHashMap",
    "default_request_hash",
    "default_virtual_hash",
]

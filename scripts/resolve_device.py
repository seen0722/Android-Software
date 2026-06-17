#!/usr/bin/env python3
"""resolve_device.py — compose layered device profiles + resolve the active SKU."""
from __future__ import annotations


def deep_merge(base: dict, override: dict) -> dict:
    """Maps deep-merge; scalars overridden by `override`; a None value deletes the key."""
    result = dict(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

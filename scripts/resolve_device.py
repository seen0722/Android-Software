#!/usr/bin/env python3
"""resolve_device.py — compose layered device profiles + resolve the active SKU."""
from __future__ import annotations

import json
from pathlib import Path
import yaml


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


_RESERVED = {"layer"}


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents as a dict."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_index(devices_dir: Path) -> dict:
    """Load the devices index from index.json."""
    return json.loads((devices_dir / "index.json").read_text(encoding="utf-8"))


def _strip_meta(fragment: dict) -> dict:
    """Strip reserved metadata keys from a fragment."""
    return {k: v for k, v in fragment.items() if k not in _RESERVED}


def _fragment_path(devices_dir: Path, product: str, layer: str) -> Path:
    """Return the path to a layer fragment file."""
    rel = "base.yaml" if layer == "base" else f"{layer}.yaml"
    return devices_dir / product / rel


def resolve_sku(devices_dir: Path, product: str, sku_id: str) -> dict:
    """Compose the effective profile for a SKU by merging layers in order.

    Args:
        devices_dir: Path to the devices directory
        product: Product name (e.g., "tab-atlas")
        sku_id: SKU identifier (e.g., "atlas-lte-ofilm-cn-dl")

    Returns:
        A dict with keys: sku, resolves_from, and merged profile data.
        The 'layer' metadata key is stripped from all fragments.
    """
    # Load the SKU recipe
    sku = load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")

    # Start with empty profile and merge layers in order
    profile: dict = {}
    for layer in sku["layers"]:
        fragment = load_yaml(_fragment_path(devices_dir, product, layer))
        profile = deep_merge(profile, _strip_meta(fragment))

    # Merge any extra keys from the SKU file (excluding reserved keys)
    extras = {k: v for k, v in sku.items() if k not in {"layers", "sku", "resolves_from"}}
    profile = deep_merge(profile, extras)

    # Add sku and resolves_from to the profile
    profile["sku"] = sku["sku"]
    profile["resolves_from"] = sku.get("resolves_from", {})

    return profile

# Device Profile Grounding (L4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add device/SKU/customer grounding to the Android-Software skill set so the agent answers from the active board's real facts and a verified source-control state, not generic AOSP assumptions.

**Architecture:** Facts live as layered YAML data under `devices/` (base + os + hw + dist + customer fragments composed by thin SKU recipes). Three repo-level Python scripts resolve, validate, and source-verify a profile. One generic `L4-device-grounding-expert` skill and an L1 router augmentation wire it into routing. Spec: `docs/superpowers/specs/2026-06-17-device-profile-grounding-design.md`.

**Tech Stack:** Python 3 (stdlib + `pyyaml`), pytest, Markdown SKILL.md, existing `scripts/skill_lint.py` and `tests/routing_accuracy`.

## Global Constraints

- All commands run from inside `Android-Software/` (its own git repo; the workspace root is not a repo).
- Python 3, `pyyaml` required; `pytest` required for new unit tests (`python3 -m pip install pyyaml pytest`).
- New top-level dirs need `.gitignore` whitelist entries: `!devices/`, `!docs/`.
- Layer merge: maps deep-merge; scalars overridden by later layers; `null` deletes a key.
- SKU resolution priority (never guess): explicit sku → branch/build_option match → product `default_sku` (state assumption) → ambiguous = raise/ask.
- `Source State as Truth`: a correct path is necessary but NOT sufficient; never analyze/propose against an unverified or mismatched source state.
- No secrets: profiles carry locations and commands only — never credentials/tokens.
- Cross-customer NDA isolation is the highest-severity rule; a leak is a hard failure.
- File size: keep each Python file focused (< 400 lines); split helpers if larger.
- TDD throughout; commit after every green task.

---

## File Structure

**Data (Phase 1):**
- Create `devices/index.json` — product/SKU registry + `default_sku`
- Create `devices/schema.md` — field definitions
- Create `devices/tab-atlas/base.yaml`, `os/a16.yaml`, `hw/panel-ofilm.yaml`, `hw/panel-boe.yaml`, `hw/modem-x75.yaml`, `dist/cn.yaml`, `dist/gms.yaml`, `customer/datalogic.yaml`, `customer/trimble.yaml`, `skus/atlas-lte-ofilm-cn-dl.yaml`, `skus/atlas-wifi-boe-gms-tr.yaml`

**Scripts:**
- Create `scripts/resolve_device.py` — merge layers + resolve active SKU + source coords
- Create `scripts/validate_device_profile.py` — schema + convention + source-coord + no-secret validation
- Create `scripts/verify_source_state.py` — synced tree vs resolved coords; emits fetch hint

**Tests:**
- Create `tests/device_profile/test_dataset.py`, `test_resolve_device.py`, `test_validate_device_profile.py`, `test_verify_source_state.py`
- Modify `tests/routing_accuracy/` — add device-context resolution cases

**Skill + routing (Phases 3-4):**
- Create `skills/L4-device-grounding-expert/SKILL.md` + `references/device_grounding_model.md`
- Modify `skills/L1-aosp-root-router/SKILL.md` — Device Context Detection + augmented decision block

---

## Task 1: Project setup, sample dataset, and `.gitignore`

**Files:**
- Modify: `.gitignore` (add `!devices/`, `!docs/`)
- Create: `devices/index.json`, `devices/schema.md`, and the 11 fragment/SKU YAML files listed above
- Test: `tests/device_profile/test_dataset.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the on-disk `devices/` dataset every later task reads. SKU ids: `atlas-lte-ofilm-cn-dl`, `atlas-wifi-boe-gms-tr`. Product id: `tab-atlas`. `default_sku`: `atlas-lte-ofilm-cn-dl`.

- [ ] **Step 1: Ensure dependencies + whitelist `devices/`/`docs/`**

Run:
```bash
python3 -m pip install pyyaml pytest
```
Add these two lines to the end of `.gitignore`:
```gitignore
!devices/
!docs/
```

- [ ] **Step 2: Create the registry `devices/index.json`**

```json
{
  "products": [
    {
      "id": "tab-atlas",
      "name": "Atlas 11-inch Tablet",
      "default_sku": "atlas-lte-ofilm-cn-dl",
      "skus": ["atlas-lte-ofilm-cn-dl", "atlas-wifi-boe-gms-tr"]
    }
  ]
}
```

- [ ] **Step 3: Create `devices/tab-atlas/base.yaml`**

```yaml
product: tab-atlas
soc: { vendor: qualcomm, codename: kalama, model: SM8650 }
kernel: { gki_branch: android14-6.1, page_size: 4k }
android_version: "16"
board_paths: { device_config: device/qcom/kalama/, vendor_root: vendor/qcom/ }
partitions: { scheme: ab, layout: gpt }
components: { wifi: wcn7850, modem: none }
source:
  manifest_repo: "git@gitlab.example.com:atlas/manifest.git"
  manifest_file: "atlas.xml"
  build_script: "build/atlas.sh"
freshness: { last_verified: "2026-06-17", status: fresh }
```

- [ ] **Step 4: Create the axis fragments**

`devices/tab-atlas/os/a16.yaml`:
```yaml
layer: os/a16
android_version: "16"
kernel: { gki_branch: android14-6.1 }
source: { manifest_file: "atlas_a16.xml" }
```
`devices/tab-atlas/hw/panel-ofilm.yaml`:
```yaml
layer: hw/panel-ofilm
components: { panel: ofilm-tv101wum, touch: goodix-gt9897 }
```
`devices/tab-atlas/hw/panel-boe.yaml`:
```yaml
layer: hw/panel-boe
components: { panel: boe-tv101wum }
```
`devices/tab-atlas/hw/modem-x75.yaml`:
```yaml
layer: hw/modem-x75
components: { modem: snapdragon-x75 }
```
`devices/tab-atlas/dist/cn.yaml`:
```yaml
layer: dist/cn
distribution: cn
gms: { integrated: false, replacement: vendor-appstore }
certification: { programs: [cts, vts], status: "n/a" }
```
`devices/tab-atlas/dist/gms.yaml`:
```yaml
layer: dist/gms
distribution: gms
gms: { integrated: true, level: full, package_config: vendor/partner_gms/products/, preinstall_partition: product }
certification: { programs: [cts, gts, vts], status: in_progress }
```

- [ ] **Step 5: Create the customer fragments**

`devices/tab-atlas/customer/datalogic.yaml`:
```yaml
layer: customer/datalogic
customer: datalogic
isolation_group: datalogic
conventions:
  branch_pattern: "DL_{product}_{androidver}_{sku}"
  sku_encoding: "DL-{hw}-{dist}"
  version_scheme: "{cust_major}.{cust_minor}.{odm_build}"
source:
  manifest_repo: "git@gitlab.example.com:datalogic/atlas-manifest.git"
  gitlab_location: "gitlab.example.com/datalogic/atlas/*"
  fetch:
    method: repo
    init: "repo init -u {manifest_repo} -b {branch} -m {manifest_file}"
    sync: "repo sync -j8"
    workspace_hint: "~/work/atlas-dl"
  build_script: "build/dl/atlas_dl.sh"
properties:
  ro.product.manufacturer: Datalogic
  ro.product.model: "{model}"
  ro.datalogic.sku: "{variant_code}"
governance:
  delivery_branch: "DL_atlas_A16_*"
  cert_owner: customer
  approval_gate: customer-signoff
```
`devices/tab-atlas/customer/trimble.yaml`:
```yaml
layer: customer/trimble
customer: trimble
isolation_group: trimble
conventions:
  branch_pattern: "trimble/{product}/rel-{androidver}-{sku}"
  sku_encoding: "TR-{hw}-{dist}"
  version_scheme: "{cust_year}.{cust_rev}"
source:
  manifest_repo: "git@gitlab.example.com:trimble/atlas-manifest.git"
  gitlab_location: "gitlab.example.com/trimble/atlas/*"
  fetch:
    method: repo
    init: "repo init -u {manifest_repo} -b {branch} -m {manifest_file}"
    sync: "repo sync -j8"
    workspace_hint: "~/work/atlas-tr"
  build_script: "build/tr/atlas_tr.sh"
properties:
  ro.product.manufacturer: Trimble
  ro.product.model: "{model}"
  ro.trimble.sku: "{variant_code}"
governance:
  delivery_branch: "trimble/atlas/rel-*"
  cert_owner: customer
  approval_gate: customer-signoff
```

- [ ] **Step 6: Create the SKU recipes**

`devices/tab-atlas/skus/atlas-lte-ofilm-cn-dl.yaml`:
```yaml
sku: atlas-lte-ofilm-cn-dl
layers: [base, os/a16, hw/panel-ofilm, hw/modem-x75, dist/cn, customer/datalogic]
resolves_from:
  branch: "DL_atlas_A16_lte-ofilm-cn"
  build_option: "TARGET_PRODUCT=atlas_lte_cn_dl"
freshness: { last_verified: "2026-06-12", status: fresh }
```
`devices/tab-atlas/skus/atlas-wifi-boe-gms-tr.yaml`:
```yaml
sku: atlas-wifi-boe-gms-tr
layers: [base, os/a16, hw/panel-boe, dist/gms, customer/trimble]
resolves_from:
  branch: "trimble/atlas/rel-a16-wifi-boe"
  build_option: "TARGET_PRODUCT=atlas_wifi_gms_tr"
freshness: { last_verified: "2026-06-12", status: fresh }
```

- [ ] **Step 7: Create `devices/schema.md`**

```markdown
# Device Profile Schema

A profile is composed from layers via a SKU recipe:
`effective = deep_merge(base, os, hw…, dist, customer)`.

## Fragment keys
- `layer` (fragments only): identity string, e.g. `customer/datalogic`. Stripped on merge.
- `soc`: `{ vendor, codename, model }`. `codename` maps to the L3-qualcomm SoC table.
- `kernel`: `{ gki_branch, page_size }`.
- `components`: `{ panel, touch, modem, wifi, ... }`.
- `board_paths`, `partitions`, `android_version`, `distribution`, `gms`, `certification`, `properties`.
- `source`: `{ manifest_repo, manifest_file, gitlab_location, build_script, fetch }`.
  - `fetch`: `{ method, init, sync, workspace_hint }`. Commands only — NEVER credentials.
- `conventions` (customer): `{ branch_pattern, sku_encoding, version_scheme, resolver_hook? }`.
- `governance` (customer): `{ delivery_branch, cert_owner, approval_gate }`.
- `isolation_group` (customer): NDA isolation boundary.
- `freshness`: `{ last_verified, status: fresh|dirty, reason? }`.

## SKU recipe keys
- `sku`, `layers` (ordered), `resolves_from: { branch, build_option }`, `freshness`.
```

- [ ] **Step 8: Write the dataset test**

`tests/device_profile/test_dataset.py`:
```python
import json
from pathlib import Path
import yaml

DEVICES = Path(__file__).resolve().parents[2] / "devices"

def _load_yaml(p):
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

def test_index_and_skus_parse_and_layers_exist():
    index = json.loads((DEVICES / "index.json").read_text(encoding="utf-8"))
    for product in index["products"]:
        pid = product["id"]
        assert product["default_sku"] in product["skus"]
        for sku_id in product["skus"]:
            sku = _load_yaml(DEVICES / pid / "skus" / f"{sku_id}.yaml")
            assert sku["sku"] == sku_id
            for layer in sku["layers"]:
                rel = "base.yaml" if layer == "base" else f"{layer}.yaml"
                assert (DEVICES / pid / rel).exists(), f"{sku_id} references missing layer {layer}"
```

- [ ] **Step 9: Run the dataset test**

Run: `python3 -m pytest tests/device_profile/test_dataset.py -v`
Expected: PASS (2 SKUs, all layers exist).

- [ ] **Step 10: Commit**

```bash
git add .gitignore devices/ tests/device_profile/test_dataset.py
git commit -m "feat(devices): add layered device profile dataset + schema"
```

---

## Task 2: `deep_merge` layer composition

**Files:**
- Create: `scripts/resolve_device.py`
- Test: `tests/device_profile/test_resolve_device.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `deep_merge(base: dict, override: dict) -> dict` — maps deep-merged, scalars replaced, a `None` value deletes the key. Used by `resolve_sku` (Task 3).

- [ ] **Step 1: Write the failing test**

`tests/device_profile/test_resolve_device.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import resolve_device as rd

def test_deep_merge_overrides_scalar_and_merges_maps():
    base = {"components": {"modem": "none", "wifi": "wcn7850"}, "k": 1}
    override = {"components": {"modem": "snapdragon-x75"}, "k": 2}
    out = rd.deep_merge(base, override)
    assert out == {"components": {"modem": "snapdragon-x75", "wifi": "wcn7850"}, "k": 2}

def test_deep_merge_null_deletes_key():
    out = rd.deep_merge({"components": {"modem": "none"}}, {"components": {"modem": None}})
    assert out == {"components": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py -v`
Expected: FAIL (`No module named 'resolve_device'`).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/resolve_device.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/resolve_device.py tests/device_profile/test_resolve_device.py
git commit -m "feat(resolve): add deep_merge layer composition"
```

---

## Task 3: `resolve_sku` — compose a profile from a recipe

**Files:**
- Modify: `scripts/resolve_device.py`
- Test: `tests/device_profile/test_resolve_device.py`

**Interfaces:**
- Consumes: `deep_merge` (Task 2); the `devices/` dataset (Task 1).
- Produces: `resolve_sku(devices_dir: Path, product: str, sku_id: str) -> dict` returning the effective profile with `sku` and `resolves_from` keys, `layer` meta stripped. `load_yaml(path) -> dict`, `load_index(devices_dir) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `tests/device_profile/test_resolve_device.py`:
```python
DEVICES = Path(__file__).resolve().parents[2] / "devices"

def test_resolve_sku_merges_layers_in_order():
    p = rd.resolve_sku(DEVICES, "tab-atlas", "atlas-lte-ofilm-cn-dl")
    assert p["sku"] == "atlas-lte-ofilm-cn-dl"
    assert p["components"]["modem"] == "snapdragon-x75"   # hw/modem-x75 overrode base 'none'
    assert p["components"]["panel"] == "ofilm-tv101wum"   # hw/panel-ofilm
    assert p["components"]["wifi"] == "wcn7850"            # inherited from base
    assert p["distribution"] == "cn"                       # dist/cn
    assert p["customer"] == "datalogic"                    # customer layer
    assert p["source"]["manifest_file"] == "atlas_a16.xml" # os/a16 overrode base
    assert p["source"]["manifest_repo"].endswith("datalogic/atlas-manifest.git")
    assert "layer" not in p                                 # meta stripped
    assert p["resolves_from"]["branch"] == "DL_atlas_A16_lte-ofilm-cn"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py::test_resolve_sku_merges_layers_in_order -v`
Expected: FAIL (`module 'resolve_device' has no attribute 'resolve_sku'`).

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/resolve_device.py`:
```python
import json
from pathlib import Path
import yaml

_RESERVED = {"layer"}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_index(devices_dir: Path) -> dict:
    return json.loads((devices_dir / "index.json").read_text(encoding="utf-8"))


def _strip_meta(fragment: dict) -> dict:
    return {k: v for k, v in fragment.items() if k not in _RESERVED}


def _fragment_path(devices_dir: Path, product: str, layer: str) -> Path:
    rel = "base.yaml" if layer == "base" else f"{layer}.yaml"
    return devices_dir / product / rel


def resolve_sku(devices_dir: Path, product: str, sku_id: str) -> dict:
    sku = load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")
    profile: dict = {}
    for layer in sku["layers"]:
        fragment = load_yaml(_fragment_path(devices_dir, product, layer))
        profile = deep_merge(profile, _strip_meta(fragment))
    extras = {k: v for k, v in sku.items() if k not in {"layers", "sku", "resolves_from"}}
    profile = deep_merge(profile, extras)
    profile["sku"] = sku["sku"]
    profile["resolves_from"] = sku.get("resolves_from", {})
    return profile
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/resolve_device.py tests/device_profile/test_resolve_device.py
git commit -m "feat(resolve): compose effective profile from SKU recipe layers"
```

---

## Task 4: `resolve_active` — SKU selection priority

**Files:**
- Modify: `scripts/resolve_device.py`
- Test: `tests/device_profile/test_resolve_device.py`

**Interfaces:**
- Consumes: `resolve_sku`, `load_index` (Task 3).
- Produces: `resolve_active(devices_dir, *, sku=None, branch=None, build_option=None, product=None) -> dict` (effective profile + `_resolution` metadata). Exceptions `AmbiguousDeviceError`, `DeviceNotFoundError`. Used by the L4 skill and tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/device_profile/test_resolve_device.py`:
```python
import pytest

def test_resolve_active_by_branch():
    p = rd.resolve_active(DEVICES, branch="DL_atlas_A16_lte-ofilm-cn")
    assert p["sku"] == "atlas-lte-ofilm-cn-dl"
    assert p["_resolution"]["matched_by"] == "branch"

def test_resolve_active_by_explicit_sku():
    p = rd.resolve_active(DEVICES, sku="atlas-wifi-boe-gms-tr")
    assert p["customer"] == "trimble"

def test_resolve_active_product_only_uses_default_and_flags_assumption():
    p = rd.resolve_active(DEVICES, product="tab-atlas")
    assert p["sku"] == "atlas-lte-ofilm-cn-dl"
    assert p["_resolution"]["assumed_default"] is True

def test_resolve_active_unknown_branch_raises():
    with pytest.raises(rd.DeviceNotFoundError):
        rd.resolve_active(DEVICES, branch="nope/does-not-exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py -k resolve_active -v`
Expected: FAIL (`has no attribute 'resolve_active'`).

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/resolve_device.py`:
```python
import fnmatch


class DeviceNotFoundError(Exception):
    pass


class AmbiguousDeviceError(Exception):
    pass


def _iter_skus(index: dict):
    for product in index["products"]:
        for sku_id in product["skus"]:
            yield product["id"], sku_id


def _product_of_sku(index: dict, sku_id: str) -> str:
    for product in index["products"]:
        if sku_id in product["skus"]:
            return product["id"]
    raise DeviceNotFoundError(f"unknown sku: {sku_id}")


def _match_recipes(devices_dir: Path, index: dict, field: str, value: str):
    hits = []
    for product, sku_id in _iter_skus(index):
        recipe = load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")
        declared = recipe.get("resolves_from", {}).get(field, "")
        if declared and (value == declared or fnmatch.fnmatch(value, declared)):
            hits.append((product, sku_id))
    return hits


def resolve_active(devices_dir: Path, *, sku=None, branch=None,
                   build_option=None, product=None) -> dict:
    index = load_index(devices_dir)
    if sku:
        prof = resolve_sku(devices_dir, _product_of_sku(index, sku), sku)
        prof["_resolution"] = {"matched_by": "sku", "assumed_default": False}
        return prof
    for field, value in (("branch", branch), ("build_option", build_option)):
        if not value:
            continue
        hits = _match_recipes(devices_dir, index, field, value)
        if len(hits) == 1:
            prof = resolve_sku(devices_dir, hits[0][0], hits[0][1])
            prof["_resolution"] = {"matched_by": field, "assumed_default": False}
            return prof
        if len(hits) > 1:
            raise AmbiguousDeviceError(f"{field}={value} matches {hits}")
        raise DeviceNotFoundError(f"no SKU for {field}={value}")
    if product:
        prod = next((p for p in index["products"] if p["id"] == product), None)
        if not prod:
            raise DeviceNotFoundError(f"unknown product: {product}")
        prof = resolve_sku(devices_dir, product, prod["default_sku"])
        prof["_resolution"] = {"matched_by": "default", "assumed_default": True}
        return prof
    raise AmbiguousDeviceError("no sku/branch/build_option/product cue given")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_resolve_device.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Add CLI entry point**

Append to `scripts/resolve_device.py`:
```python
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Resolve an effective device profile")
    ap.add_argument("--devices-dir", default="devices")
    ap.add_argument("--sku")
    ap.add_argument("--branch")
    ap.add_argument("--build-option")
    ap.add_argument("--product")
    args = ap.parse_args(argv)
    prof = resolve_active(Path(args.devices_dir), sku=args.sku, branch=args.branch,
                          build_option=args.build_option, product=args.product)
    print(json.dumps(prof, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the CLI**

Run: `python3 scripts/resolve_device.py --branch DL_atlas_A16_lte-ofilm-cn`
Expected: JSON profile with `"sku": "atlas-lte-ofilm-cn-dl"` and `"customer": "datalogic"`.

- [ ] **Step 7: Commit**

```bash
git add scripts/resolve_device.py tests/device_profile/test_resolve_device.py
git commit -m "feat(resolve): add resolve_active SKU selection + CLI"
```

---

## Task 5: `validate_device_profile.py` — schema, conventions, no-secrets

**Files:**
- Create: `scripts/validate_device_profile.py`
- Test: `tests/device_profile/test_validate_device_profile.py`

**Interfaces:**
- Consumes: `resolve_device.load_index`, `resolve_sku`, `load_yaml` (Tasks 3-4); the dataset.
- Produces: `validate(devices_dir: Path) -> list[str]` (error strings; empty = valid). CLI exits non-zero on errors. `SOC_GKI_TABLE: dict`. Helpers `pattern_literals_present`, `find_secrets`.

- [ ] **Step 1: Write the failing test**

`tests/device_profile/test_validate_device_profile.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import validate_device_profile as v

DEVICES = Path(__file__).resolve().parents[2] / "devices"

def test_sample_dataset_is_valid():
    assert v.validate(DEVICES) == []

def test_pattern_literals_present():
    assert v.pattern_literals_present("DL_{product}_{androidver}_{sku}", "DL_atlas_A16_lte-ofilm-cn")
    assert not v.pattern_literals_present("trimble/{product}/rel-{x}", "DL_atlas_A16_lte")

def test_find_secrets_flags_token_like_values():
    assert v.find_secrets({"source": {"token": "ghp_abcdef0123456789abcdef0123456789abcd"}})
    assert v.find_secrets({"source": {"fetch": {"init": "repo init -u {manifest_repo}"}}}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/device_profile/test_validate_device_profile.py -v`
Expected: FAIL (`No module named 'validate_device_profile'`).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/validate_device_profile.py`:
```python
#!/usr/bin/env python3
"""validate_device_profile.py — schema + convention + source-coord + no-secret checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve_device as rd

# codename → expected gki_branch (from L3-qualcomm-kernel-expert SoC table)
SOC_GKI_TABLE = {
    "lahaina": "android13-5.10", "taro": "android14-5.15",
    "kalama": "android14-6.1", "sun": "android15-6.6", "crow": "android15-6.6",
}
_REQUIRED_SOURCE = ("manifest_repo", "manifest_file", "build_script")
_SECRET_KEYS = re.compile(r"(token|password|secret|api[_-]?key|private[_-]?key)", re.I)
_SECRET_VAL = re.compile(r"(ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")


def pattern_literals_present(pattern: str, branch: str) -> bool:
    """Lenient check: every non-placeholder literal of `pattern` appears in order in `branch`."""
    literals = [s for s in re.split(r"\{[^}]+\}", pattern) if s]
    pos = 0
    for lit in literals:
        idx = branch.find(lit, pos)
        if idx < 0:
            return False
        pos = idx + len(lit)
    return True


def find_secrets(node, path="") -> list[str]:
    hits = []
    if isinstance(node, dict):
        for k, val in node.items():
            if isinstance(val, str) and _SECRET_KEYS.search(str(k)):
                hits.append(f"{path}.{k}: secret-like key")
            hits += find_secrets(val, f"{path}.{k}")
    elif isinstance(node, str) and _SECRET_VAL.search(node):
        hits.append(f"{path}: secret-like value")
    return hits


def validate(devices_dir: Path) -> list[str]:
    errors: list[str] = []
    index = rd.load_index(devices_dir)
    for product, sku_id in rd._iter_skus(index):
        recipe = rd.load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")
        for layer in recipe.get("layers", []):
            if not rd._fragment_path(devices_dir, product, layer).exists():
                errors.append(f"{sku_id}: missing layer file {layer}")
        try:
            prof = rd.resolve_sku(devices_dir, product, sku_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sku_id}: resolve failed: {exc}")
            continue
        src = prof.get("source", {})
        for key in _REQUIRED_SOURCE:
            if not src.get(key):
                errors.append(f"{sku_id}: source.{key} missing")
        branch = recipe.get("resolves_from", {}).get("branch", "")
        pattern = prof.get("conventions", {}).get("branch_pattern", "")
        if branch and pattern and not pattern_literals_present(pattern, branch):
            errors.append(f"{sku_id}: branch '{branch}' does not match pattern '{pattern}'")
        codename = prof.get("soc", {}).get("codename")
        gki = prof.get("kernel", {}).get("gki_branch")
        if codename in SOC_GKI_TABLE and gki != SOC_GKI_TABLE[codename]:
            errors.append(f"{sku_id}: codename {codename} expects {SOC_GKI_TABLE[codename]}, got {gki}")
        errors += [f"{sku_id}: {h}" for h in find_secrets(prof)]
    return errors


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices-dir", default="devices")
    args = ap.parse_args(argv)
    errs = validate(Path(args.devices_dir))
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    print("OK: all device profiles valid")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_validate_device_profile.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the validator CLI on the dataset**

Run: `python3 scripts/validate_device_profile.py`
Expected: `OK: all device profiles valid`

- [ ] **Step 6: Commit**

```bash
git add scripts/validate_device_profile.py tests/device_profile/test_validate_device_profile.py
git commit -m "feat(validate): schema + convention + no-secret device profile validation"
```

---

## Task 6: `verify_source_state.py` — synced tree vs resolved coords (Phase 2)

**Files:**
- Create: `scripts/verify_source_state.py`
- Test: `tests/device_profile/test_verify_source_state.py`

**Interfaces:**
- Consumes: an effective profile dict (from `resolve_device`).
- Produces: `verify(profile: dict, tree_path: Path, runner=...) -> dict` → `{state: "VERIFIED"|"MISMATCH"|"UNVERIFIED", expected_branch, actual_branch, fetch_hint}`. `render_fetch_hint(profile) -> str`. `runner(cmd: list[str]) -> str|None` (injectable; returns None when the command/tree is unavailable).

- [ ] **Step 1: Write the failing test**

`tests/device_profile/test_verify_source_state.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import verify_source_state as vs

PROFILE = {
    "resolves_from": {"branch": "DL_atlas_A16_lte-ofilm-cn"},
    "source": {
        "manifest_repo": "git@gitlab.example.com:datalogic/atlas-manifest.git",
        "manifest_file": "atlas_a16.xml",
        "gitlab_location": "gitlab.example.com/datalogic/atlas/*",
        "fetch": {"method": "repo",
                  "init": "repo init -u {manifest_repo} -b {branch} -m {manifest_file}",
                  "sync": "repo sync -j8"},
    },
}

def test_verified_when_branch_matches():
    out = vs.verify(PROFILE, Path("/x"), runner=lambda cmd: "DL_atlas_A16_lte-ofilm-cn")
    assert out["state"] == "VERIFIED"

def test_mismatch_when_branch_differs():
    out = vs.verify(PROFILE, Path("/x"), runner=lambda cmd: "some-other-branch")
    assert out["state"] == "MISMATCH"
    assert "repo init" in out["fetch_hint"]

def test_unverified_when_tree_unavailable():
    out = vs.verify(PROFILE, Path("/x"), runner=lambda cmd: None)
    assert out["state"] == "UNVERIFIED"
    assert "DL_atlas_A16_lte-ofilm-cn" in out["fetch_hint"]

def test_render_fetch_hint_substitutes_placeholders():
    hint = vs.render_fetch_hint(PROFILE)
    assert "datalogic/atlas-manifest.git" in hint
    assert "atlas_a16.xml" in hint
    assert "{manifest_repo}" not in hint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/device_profile/test_verify_source_state.py -v`
Expected: FAIL (`No module named 'verify_source_state'`).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/verify_source_state.py`:
```python
#!/usr/bin/env python3
"""verify_source_state.py — compare a synced tree against the resolved source coords."""
from __future__ import annotations

import subprocess
from pathlib import Path


def render_fetch_hint(profile: dict) -> str:
    src = profile.get("source", {})
    fetch = src.get("fetch", {})
    branch = profile.get("resolves_from", {}).get("branch", "")
    subs = {
        "manifest_repo": src.get("manifest_repo", ""),
        "manifest_file": src.get("manifest_file", ""),
        "branch": branch,
    }

    def fill(template: str) -> str:
        for key, val in subs.items():
            template = template.replace("{" + key + "}", val)
        return template

    lines = [f"# GitLab location: {src.get('gitlab_location', 'n/a')}"]
    if fetch.get("init"):
        lines.append(fill(fetch["init"]))
    if fetch.get("sync"):
        lines.append(fill(fetch["sync"]))
    return "\n".join(lines)


def _default_runner(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def verify(profile: dict, tree_path: Path, runner=_default_runner) -> dict:
    expected = profile.get("resolves_from", {}).get("branch", "")
    actual = runner(["git", "-C", str(tree_path), "rev-parse", "--abbrev-ref", "HEAD"])
    hint = render_fetch_hint(profile)
    if actual is None or actual == "":
        state = "UNVERIFIED"
    elif actual == expected:
        state = "VERIFIED"
    else:
        state = "MISMATCH"
    return {"state": state, "expected_branch": expected, "actual_branch": actual,
            "fetch_hint": hint}


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("tree_path")
    ap.add_argument("--profile", required=True, help="path to a resolved profile JSON")
    args = ap.parse_args(argv)
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    out = verify(profile, Path(args.tree_path))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["state"] == "VERIFIED" else 2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_verify_source_state.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_source_state.py tests/device_profile/test_verify_source_state.py
git commit -m "feat(verify): source-state verification + actionable fetch hint"
```

---

## Task 7: `L4-device-grounding-expert` skill (Phase 3)

**Files:**
- Create: `skills/L4-device-grounding-expert/SKILL.md`
- Create: `skills/L4-device-grounding-expert/references/device_grounding_model.md`

**Interfaces:**
- Consumes: `scripts/resolve_device.py`, `scripts/verify_source_state.py`, `scripts/validate_device_profile.py`.
- Produces: a `skill_lint`-compliant SKILL.md with frontmatter + required sections + ≥5 Forbidden Actions, emitting the `[Profile]/[Source]/[State]` grounding header.

- [ ] **Step 1: Inspect the lint schema and an existing L3 for required sections**

Run: `python3 scripts/skill_lint.py --skills-dir skills`
Read the failure/structure rules and skim `skills/L3-qualcomm-kernel-expert/SKILL.md` to mirror section order.

- [ ] **Step 2: Write `SKILL.md`**

Create `skills/L4-device-grounding-expert/SKILL.md` with this content:
```markdown
---
name: device-grounding-expert
layer: L4
path_scope: devices/
version: 1.0.0
android_version_tested: Android 16
parent_skill: aosp-root-router
---

## Path Scope

| Path | Responsibility |
|------|---------------|
| `devices/` | Layered device/SKU/customer fact store (data) |
| `scripts/resolve_device.py` | Compose effective profile + resolve active SKU |
| `scripts/verify_source_state.py` | Confirm synced tree == resolved source coords |
| `scripts/validate_device_profile.py` | Schema/convention/no-secret validation |

## Trigger Conditions

Load (paged by L1) when a task carries a device cue: product/SKU/`variant_code`,
a branch or build option, a named HW component, or a brand customer (e.g. Datalogic,
Trimble). Runs after L1, before the subsystem L2/L3.

## Architecture Intelligence

Resolve the effective profile, then VERIFY source state, then ground:

1. `python3 scripts/resolve_device.py --branch <b>` (or `--sku/--build-option/--product`).
2. `python3 scripts/verify_source_state.py <tree> --profile <json>` → VERIFIED / MISMATCH / UNVERIFIED.
3. Emit the grounding header and hand to the subsystem expert (do not answer subsystem
   questions here). Layer merge = base + os + hw + dist + customer (later overrides earlier).

Grounding header:
```
[Profile] SoC=<codename>(<model>) GKI=<gki_branch> panel=<panel> dist=<distribution> customer=<customer>
[Source]  manifest=<manifest_file>@<branch>  build=<build_script>
[State]   VERIFIED | UNVERIFIED | MISMATCH
```
When State != VERIFIED, do not analyze or propose — emit the fetch hint and stop.

## Forbidden Actions

1. Analyze or propose a fix against an unverified or mismatched source state — forbidden;
   confirm repo/manifest/branch/HEAD first, or stop and report.
2. Cross-customer NDA isolation: never reference or leak one `isolation_group`'s
   facts/branding/properties/source into another customer's answer.
3. Customer delivery/release branch (`governance.delivery_branch`) = hard stop; ask first.
4. When `cert_owner: customer`, treat CTS/GTS/GMS settings as read-only; confirm first.
5. Never apply one SKU's or OS version's facts/manifest/branch/build script to another.
6. Parse branch/SKU only with the active customer's conventions (never cross-customer).
7. Never invent an undocumented HW component / property / source coordinate — report "not defined".
8. Never store, echo, or hard-code GitLab credentials/tokens, and never fetch with another
   customer's coordinates.

## Tool Calls

```bash
python3 scripts/resolve_device.py --branch <branch>
python3 scripts/resolve_device.py --sku <sku-id>
python3 scripts/verify_source_state.py <tree_path> --profile <profile.json>
python3 scripts/validate_device_profile.py
```

## Handoff Rules

| Condition | Emit | Target |
|-----------|------|--------|
| State VERIFIED, subsystem question | `[L4 DEVICE → GROUNDING]` | the relevant L2/L3 |
| State != VERIFIED | (emit fetch hint) | stop / ask user |
| Pure device-fact lookup | (answer from profile) | terminal |

## References

- `skills/L4-device-grounding-expert/references/device_grounding_model.md`
- `devices/schema.md`
- `docs/superpowers/specs/2026-06-17-device-profile-grounding-design.md`
```

- [ ] **Step 3: Write the reference doc**

Create `skills/L4-device-grounding-expert/references/device_grounding_model.md`:
```markdown
# Device Grounding Model

`Path as Truth` → `Source State as Truth`: a correct path is necessary but not
sufficient; it is only meaningful inside a confirmed (repo, manifest, branch, sync state).

- **Layered composition:** `effective = deep_merge(base, os, hw…, dist, customer)`.
  Divergence (HW, GMS/CN, customer conventions, source location) lives in DATA; this skill
  is the generic method.
- **Resolution priority:** explicit sku → branch/build_option → product default (state it)
  → ambiguous = ask.
- **Verification gate:** never reason on an unconfirmed tree; when wrong/missing, emit the
  per-SKU fetch hint so the user can sync the correct code.
- **Isolation:** `isolation_group` is the NDA boundary; never cross customers.
```

- [ ] **Step 4: Run the linter**

Run: `python3 scripts/skill_lint.py --skills-dir skills`
Expected: PASS for `L4-device-grounding-expert` (frontmatter, required sections, ≥5 Forbidden Actions). Fix any reported section gaps inline and re-run.

- [ ] **Step 5: Commit**

```bash
git add skills/L4-device-grounding-expert/
git commit -m "feat(L4): add device-grounding-expert skill + reference"
```

---

## Task 8: L1 router — Device Context Detection (Phase 4)

**Files:**
- Modify: `skills/L1-aosp-root-router/SKILL.md`
- Test: `tests/routing_accuracy/test_router.py` (regression)

**Interfaces:**
- Consumes: the L4 skill (Task 7).
- Produces: an L1 "Device Context Detection" section + augmented `[L1 ROUTING DECISION]` block including `Device` / `Profile` / `Source` / `State` lines.

- [ ] **Step 1: Baseline the routing suite (no regression target)**

Run: `python3 tests/routing_accuracy/test_router.py`
Expected: `Routing Accuracy: 100.0%` (record this; Task 8 must not lower it).

- [ ] **Step 2: Add the Device Context Detection section to L1 `SKILL.md`**

In `skills/L1-aosp-root-router/SKILL.md`, immediately after the `## Routing Algorithm`
section, insert:
```markdown
## Device Context Detection (pre-routing)

Before subsystem routing, detect a device cue: product id, SKU id / `variant_code`,
a branch name, a build option (`TARGET_PRODUCT=...`), a named HW component, or a brand
customer (e.g. Datalogic, Trimble). If present, page `L4-device-grounding-expert` first;
it resolves the effective profile and verifies source state, then hands back for subsystem
routing. If absent, route directly (`L1 → L2/L3`). Never guess the SKU — if ambiguous, ask.

Execution order is `L1 → L4 → L2 → L3` even though L4 is the most specific (highest) layer.
```

- [ ] **Step 3: Augment the routing decision block in L1 `SKILL.md`**

In the `## Handoff Rules` section, replace the existing `[L1 ROUTING DECISION]` block with:
```markdown
[L1 ROUTING DECISION]
Device:  <product>/<sku>  (resolved via <sku|branch|build_option|default>)   # omit if no device cue
Profile: SoC=<codename> GKI=<gki_branch> panel=<panel> dist=<dist> customer=<customer>  # if device
Source:  manifest=<manifest_file>@<branch>  build=<build_script>             # if device
State:   VERIFIED | UNVERIFIED | MISMATCH   (subsystem expert must refuse unless VERIFIED)
Intent: <one-line summary of the task>
Path(s): <matched AOSP path(s)>
L2 Skill: <skill name>
Reason: <why this skill was chosen>
[END ROUTING → loading L2 skill now]
```

- [ ] **Step 4: Re-run the routing suite (verify no regression)**

Run: `python3 tests/routing_accuracy/test_router.py`
Expected: `Routing Accuracy: 100.0%` (unchanged — the edit is additive prose).

- [ ] **Step 5: Lint the modified L1 skill**

Run: `python3 scripts/skill_lint.py --skills-dir skills`
Expected: PASS for `L1-aosp-root-router` (still has ≥5 Forbidden Actions and required sections).

- [ ] **Step 6: Commit**

```bash
git add skills/L1-aosp-root-router/SKILL.md
git commit -m "feat(L1): add Device Context Detection + grounding header"
```

---

## Task 9: Device-context resolution eval (Phase 5)

**Files:**
- Create: `tests/device_profile/test_device_routing_eval.py`

**Interfaces:**
- Consumes: `resolve_device.resolve_active`, `verify_source_state.verify` (Tasks 4, 6).
- Produces: a deterministic eval asserting that representative device-context prompts resolve to the correct SKU and gate on source state. (LLM Layer-B grounding/isolation eval is future work, noted below.)

- [ ] **Step 1: Write the failing eval**

`tests/device_profile/test_device_routing_eval.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import resolve_device as rd
import verify_source_state as vs

DEVICES = Path(__file__).resolve().parents[2] / "devices"

# (cue_kwargs, expected_sku, expected_customer)
CASES = [
    ({"branch": "DL_atlas_A16_lte-ofilm-cn"}, "atlas-lte-ofilm-cn-dl", "datalogic"),
    ({"build_option": "TARGET_PRODUCT=atlas_wifi_gms_tr"}, "atlas-wifi-boe-gms-tr", "trimble"),
    ({"sku": "atlas-lte-ofilm-cn-dl"}, "atlas-lte-ofilm-cn-dl", "datalogic"),
]

def test_device_context_cases_resolve_correctly():
    for kwargs, sku, customer in CASES:
        p = rd.resolve_active(DEVICES, **kwargs)
        assert p["sku"] == sku, kwargs
        assert p["customer"] == customer, kwargs

def test_unverified_tree_gates_and_offers_fetch():
    p = rd.resolve_active(DEVICES, sku="atlas-lte-ofilm-cn-dl")
    out = vs.verify(p, Path("/no/such/tree"), runner=lambda cmd: None)
    assert out["state"] == "UNVERIFIED"
    assert p["resolves_from"]["branch"] in out["fetch_hint"]

def test_cross_customer_isolation_groups_differ():
    dl = rd.resolve_active(DEVICES, sku="atlas-lte-ofilm-cn-dl")
    tr = rd.resolve_active(DEVICES, sku="atlas-wifi-boe-gms-tr")
    assert dl["isolation_group"] != tr["isolation_group"]
```

- [ ] **Step 2: Run the eval to verify it passes**

Run: `python3 -m pytest tests/device_profile/test_device_routing_eval.py -v`
Expected: PASS (3 tests — they exercise already-built code).

- [ ] **Step 3: Run the full device-profile suite**

Run: `python3 -m pytest tests/device_profile/ -v`
Expected: PASS (all files).

- [ ] **Step 4: Commit**

```bash
git add tests/device_profile/test_device_routing_eval.py
git commit -m "test(eval): device-context resolution + source-gating + isolation eval"
```

> **Future (Layer-B, out of scope here):** add LLM-in-the-loop cases to the
> `tests/routing_accuracy/llm_runner.py` harness that score grounding-fact correctness and
> cross-customer isolation (a leak = hard fail), per spec §11.

---

## Self-Review

**1. Spec coverage:**
- §4 directory / §5 data model → Task 1 (dataset, schema, `os/` axis, `source`+`fetch`).
- §5 merge / §6 resolution → Tasks 2-4 (`deep_merge`, `resolve_sku`, `resolve_active`, priority).
- §7 source verification → Task 6 (`verify_source_state` + fetch hint).
- §9 L4 skill + Forbidden Actions → Task 7 (all 8 forbidden actions copied verbatim).
- §8 routing integration → Task 8 (Device Context Detection + augmented decision block).
- §10 freshness → represented in data (`freshness` keys) + FA on `dirty`; validator can extend later.
- §11 validation/testing → Task 5 (validator), Tasks 2-6/9 (tests), Task 9 (device eval); Layer-B noted as future.
- §12 composition → encoded in L4 handoff rules (Task 7) + L1 routing (Task 8).
- §13 phasing → Tasks map 1:1 (P1: T1-5, P2: T6, P3: T7, P4: T8, P5: T9).
- §14 risks → no-GitLab degrades to UNVERIFIED+fetch hint (Task 6); `resolver_hook` documented in schema (not built — YAGNI until needed).

**2. Placeholder scan:** No TBD/TODO; every code/test step shows complete code; the one
`# fetch_ref` line is an intentionally commented optional field, not a gap.

**3. Type consistency:** `deep_merge`, `resolve_sku`, `resolve_active`, `load_index`,
`_iter_skus`, `_fragment_path`, `load_yaml` are defined in Task 2-4 and reused by Tasks 5-6,9
with matching signatures. `verify(profile, tree_path, runner)` and `render_fetch_hint(profile)`
match between Task 6 and Task 9. Profile keys (`sku`, `customer`, `isolation_group`,
`resolves_from.branch`, `source.*`, `_resolution`) are consistent across tasks.

No gaps found.

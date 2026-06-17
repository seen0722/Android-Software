import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import resolve_device as rd
import pytest

def test_deep_merge_overrides_scalar_and_merges_maps():
    base = {"components": {"modem": "none", "wifi": "wcn7850"}, "k": 1}
    override = {"components": {"modem": "snapdragon-x75"}, "k": 2}
    out = rd.deep_merge(base, override)
    assert out == {"components": {"modem": "snapdragon-x75", "wifi": "wcn7850"}, "k": 2}

def test_deep_merge_null_deletes_key():
    out = rd.deep_merge({"components": {"modem": "none"}}, {"components": {"modem": None}})
    assert out == {"components": {}}

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

def test_resolve_active_by_branch():
    p = rd.resolve_active(DEVICES, branch="DL_atlas_A16_lte-ofilm-cn")
    assert p["sku"] == "atlas-lte-ofilm-cn-dl"
    assert p["_resolution"]["matched_by"] == "branch"

def test_resolve_active_by_explicit_sku():
    p = rd.resolve_active(DEVICES, sku="atlas-wifi-boe-gms-tr")
    assert p["customer"] == "trimble"
    assert p["_resolution"]["matched_by"] == "sku"
    assert p["_resolution"]["assumed_default"] is False

def test_resolve_active_product_only_uses_default_and_flags_assumption():
    p = rd.resolve_active(DEVICES, product="tab-atlas")
    assert p["sku"] == "atlas-lte-ofilm-cn-dl"
    assert p["_resolution"]["assumed_default"] is True

def test_resolve_active_unknown_branch_raises():
    with pytest.raises(rd.DeviceNotFoundError):
        rd.resolve_active(DEVICES, branch="nope/does-not-exist")

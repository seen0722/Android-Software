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

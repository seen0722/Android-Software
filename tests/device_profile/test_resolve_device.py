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

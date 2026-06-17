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

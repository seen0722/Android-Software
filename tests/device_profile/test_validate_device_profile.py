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
    assert v.find_secrets({"certification": {"programs": ["cts", "ghp_abcdef0123456789abcdef0123456789abcd"]}})
    assert v.find_secrets({"token": {"nested": "x"}})

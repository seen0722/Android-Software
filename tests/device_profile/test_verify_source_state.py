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

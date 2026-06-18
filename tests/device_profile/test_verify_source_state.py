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


# --- manifest-aware mode (repo-tool trees, e.g. Thorpe T70) ---

GMS_PROFILE = {
    "resolves_from": {"branch": "release/T70-A15-*-GMS"},
    "source": {
        "manifest_repo": "ssh://git@10.192.188.16/qcs6490/manifest.git",
        "manifest_file": "default.xml",                       # daily-dev sync (the common case)
        "release_manifest": "T70-GMS-A15-{mr}.{yymmdd}.xml",  # pinned release snapshot
        "gitlab_location": "http://10.192.188.16/qcs6490",
        "fetch": {"init": "repo init -u {manifest_repo} -b default -m {manifest_file}",
                  "sync": "repo sync -j8"},
    },
}

def test_manifest_matches_globs_version_placeholders():
    assert vs.manifest_matches("T70-GMS-A15-{mr}.{yymmdd}.xml", "T70-GMS-A15-02.03.00.260523.xml")
    assert not vs.manifest_matches("T70-GMS-A15-{mr}.{yymmdd}.xml", "T70-CN-A15-02.03.00.260523.xml")
    assert not vs.manifest_matches("T70-GMS-A15-{mr}.{yymmdd}.xml", "default.xml")

def test_manifest_mode_dev_default_is_verified_as_dev():
    # Daily development: tree synced with default.xml — this is a VALID dev state.
    out = vs.verify(GMS_PROFILE, Path("/x"), manifest_reader=lambda t: "default.xml")
    assert out["mode"] == "manifest"
    assert out["state"] == "VERIFIED"
    assert out["manifest_kind"] == "dev"

def test_manifest_mode_pinned_release_is_verified_as_release():
    out = vs.verify(GMS_PROFILE, Path("/x"),
                    manifest_reader=lambda t: "T70-GMS-A15-02.03.00.260523.xml")
    assert out["state"] == "VERIFIED"
    assert out["manifest_kind"] == "release"
    assert out["actual_manifest"] == "T70-GMS-A15-02.03.00.260523.xml"

def test_manifest_mode_mismatch_when_wrong_sku_manifest():
    # CN pinned manifest is neither this SKU's dev default nor its GMS release.
    out = vs.verify(GMS_PROFILE, Path("/x"),
                    manifest_reader=lambda t: "T70-CN-A15-02.03.00.260523.xml")
    assert out["state"] == "MISMATCH"
    assert out["manifest_kind"] is None

def test_falls_back_to_branch_mode_when_not_a_repo_tree():
    # manifest_reader returns None (no .repo) -> branch mode uses the runner
    out = vs.verify(PROFILE, Path("/x"),
                    runner=lambda cmd: "DL_atlas_A16_lte-ofilm-cn",
                    manifest_reader=lambda t: None)
    assert out["mode"] == "branch"
    assert out["state"] == "VERIFIED"

def test_default_manifest_reader_reads_include(tmp_path):
    repo = tmp_path / ".repo"
    repo.mkdir()
    (repo / "manifest.xml").write_text(
        '<?xml version="1.0"?>\n<manifest>\n'
        '  <include name="T70-GMS-A15-02.03.00.260523.xml"/>\n</manifest>\n',
        encoding="utf-8")
    assert vs._default_manifest_reader(tmp_path) == "T70-GMS-A15-02.03.00.260523.xml"

def test_default_manifest_reader_none_when_no_dot_repo(tmp_path):
    assert vs._default_manifest_reader(tmp_path) is None

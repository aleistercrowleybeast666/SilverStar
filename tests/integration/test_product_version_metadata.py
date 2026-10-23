"""Product SemVer is retained; unsupported package projections fail together."""
from pathlib import Path
import runpy
import sys

import pytest
from packaging.version import Version

OVERLAY = Path(__file__).resolve().parents[2]

API = runpy.run_path(str(OVERLAY / "tools/silverstar_version.py"))


def product_root(path, text):
    (path / "VERSION").write_text(text + "\n", encoding="ascii")
    (path / "versions.json").write_bytes((OVERLAY / "versions.json").read_bytes())
    return path


@pytest.mark.parametrize("text,package", [
    ("0.1.3+ci", "0.1.3+ci"),
    ("0.1.3+Build.7", "0.1.3+build.7"),
    ("0.1.3+ci.007", "0.1.3+ci.7"),
    ("0.1.3+9.000", "0.1.3+9.0"),
    ("0.1.3+AbC123.1AbC", "0.1.3+abc123.1abc"),
    ("0.1.3-alpha.0+CI.09", "0.1.3a0+ci.9"),
    ("0.1.3-beta.2+CI.09", "0.1.3b2+ci.9"),
    ("0.1.3-rc.0+CI.09", "0.1.3rc0+ci.9"),
    ("0.1.3-dev.0+CI.09", "0.1.3.dev0+ci.9"),
])
def test_supported_metadata_is_legal_normalized_and_full_identity_is_retained(tmp_path, text, package):
    parsed = API["ProductVersion_Parse"](text)
    assert parsed.full == text
    assert parsed.package == package
    assert str(Version(package)) == package
    assert parsed.windows == (0, 1, 3, 0)
    loaded = API["ReleaseIdentity_Load"](product_root(tmp_path, text))
    assert loaded.full == text and loaded.package == package
    firmware = API["FirmwareIdentity_Resolve"](text, root=tmp_path)
    assert firmware["product_version"] == firmware["firmware_version"] == text
    assert "product_version=" + text in firmware["runtime_identity_fields"]


@pytest.mark.parametrize("metadata", [
    "ci-", "-ci", "-", "ci--build", "ci-build", "ci.-", "-.ci",
    "ci-.7", "ci.-7", "0-1", "---", "a.-.b",
])
def test_legal_semver_with_unrepresentable_metadata_is_rejected_at_shared_boundary(tmp_path, metadata):
    text = "0.1.3+" + metadata
    parsed = API["ProductVersion_Parse"](text)
    assert parsed.full == text  # Valid source SemVer, not silently rewritten.
    with pytest.raises(ValueError, match="metadata"):
        _ = parsed.package
    product_root(tmp_path, text)
    with pytest.raises(ValueError, match="metadata"):
        API["ReleaseIdentity_Load"](tmp_path)
    with pytest.raises(ValueError, match="metadata"):
        API["FirmwareIdentity_Resolve"](text, root=tmp_path)


@pytest.mark.parametrize("text,package", [("0.1.3+Build.007", "0.1.3+build.7"), ("0.1.3+ci-", None)])
def test_application_and_packaging_boundaries_agree(tmp_path, monkeypatch, text, package):
    product_root(tmp_path, text)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/silverstar_version.py").write_bytes((OVERLAY / "tools/silverstar_version.py").read_bytes())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    applications = [
        ("apps/SCG/src/silverstar_fccg/app/version.py", "__version__"),
        ("apps/FLP/src/silverstar_flp/app/version.py", "__version__"),
        ("apps/GSHC/config.py", "APP_VERSION"),
    ]
    for path, display in applications:
        if package is None:
            with pytest.raises(ValueError, match="metadata"):
                runpy.run_path(str(OVERLAY / path))
        else:
            values = runpy.run_path(str(OVERLAY / path))
            assert values[display] == text
            if "__package_version__" in values:
                assert values["__package_version__"] == package
    if package is not None:
        resource = runpy.run_path(str(OVERLAY / "apps/GSHC/packaging/product_version.py"))
        assert resource["ProductVersionResource_Create"]().ffi.fileVersionLS >> 16 == 3

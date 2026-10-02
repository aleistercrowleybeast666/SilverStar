from __future__ import annotations

import re
import json
from pathlib import Path
from pathlib import PureWindowsPath
from urllib.parse import unquote, urlsplit

import pytest

from silverstar_fccg.app.version import SILVERSTAR_PLATFORM_VERSION
from silverstar_fccg.core.workspace import WorkspacePolicy
from tools.import_reference_components import _PackageDocumentation_Annotate


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/FCCG"


def _Markdown_Destinations(content: str) -> list[str]:
    # Ignore examples in fenced code, but keep image and reference destinations.
    content = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", content)
    inline = re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)", content)
    references = re.findall(r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*(<[^>]+>|\S+)", content)
    return [value.strip("<>") for value in inline + references]


def test_docs_relative_links_exist():
    missing = []
    for path in sorted(DOCS.rglob("*.md")):
        if path.name in {"VALIDATION.md", "CHANGELOG.md"} or "history" in path.parts:
            continue
        for destination in _Markdown_Destinations(path.read_text(encoding="utf-8")):
            url = urlsplit(destination)
            if url.scheme or url.netloc or not url.path:
                continue
            # Raw snapshots retain the original link context recorded in their
            # inventory. Check their links without rewriting historical evidence.
            context = path.parent
            if path.name.endswith("_SNAPSHOT.md") and (path.parent / "INDEX.json").exists():
                inventory = json.loads((path.parent / "INDEX.json").read_text(encoding="utf-8"))
                entry = next((item for item in inventory.get("entries", [])
                              if item.get("file") == path.name), None)
                if entry:
                    parts = PureWindowsPath(entry["source"]).parts
                    repository = parts.index("SilverStar")
                    context = ROOT.parents[1].joinpath(*parts[repository + 1:-1])
            target = context / unquote(url.path)
            if not target.exists():
                missing.append(f"{path.relative_to(DOCS)} -> {destination}")
    assert not missing, "\n".join(missing)


def test_current_docs_release_and_calibration_claims():
    suite_root = ROOT.parents[1]
    assert SILVERSTAR_PLATFORM_VERSION == (suite_root / "VERSION").read_text(encoding="ascii").strip()
    stale_declaration = re.compile(
        r"(?m)^(?:#.*SilverStar\s+0\.0\.9|>.*(?:文档版本|适用范围).*0\.0\.9)"
        r"|(?:当前|firmware build tag)[^\n。]{0,70}(?:SilverStar\s+0\.0\.9|SILV0009)"
    )
    fixed_mask = re.compile(r"(?:当前为|固定(?:为)?|始终为)\s*`?0x07\b", re.I)
    for path in DOCS.rglob("*.md"):
        if path.name in {"APP_README.md", "VALIDATION.md", "CHANGELOG.md"} or "history" in path.relative_to(DOCS).parts:
            continue
        content = path.read_text(encoding="utf-8")
        assert not stale_declaration.search(content), path
        # "Existing" is valid hardware-route prose. Reject the retired
        # calibration operation, not unrelated English words in audit reports.
        assert not re.search(r"使用现有校准|\bExisting\s+Calibration\b", content, re.I), path
        assert not fixed_mask.search(content), path


def test_shared_contract_and_platform_index():
    content = (DOCS / "AIR_CALIBRATION_CONTRACT.md").read_text(encoding="utf-8")
    for mask in ("0x01", "0x03", "0x05", "0x07"):
        assert f"`{mask}`" in content
    for status in ("BAD_PARAM", "REJECTED", "BAD_STATE", "BUSY", "OK"):
        assert status in content
    details = DOCS / "platform/details"
    index = (details / "DOCUMENT_LIST.md").read_text(encoding="utf-8")
    destinations = _Markdown_Destinations(index)
    listed = {(details / unquote(urlsplit(value).path)).resolve() for value in destinations}
    assert set(details.glob("*.md")) - {details / "DOCUMENT_LIST.md"} <= listed
    contract_entry = (details / "AIR_CALIBRATION_CONTRACT.md").read_text(encoding="utf-8")
    assert "../../AIR_CALIBRATION_CONTRACT.md" in contract_entry


def test_formula_sources_and_pdfs_are_present():
    formula = DOCS / "platform/formula"
    sources = {path.stem for path in formula.glob("*.tex")}
    pdfs = {path.stem for path in formula.glob("*.pdf")}
    assert sources == pdfs == {
        "flight_controller_6d_kf_equations", "ins_coning_sculling_mechanization"
    }
    for name in sources:
        assert (formula / f"{name}.tex").stat().st_size > 0
        assert (formula / f"{name}.pdf").read_bytes().startswith(b"%PDF-")


def test_package_notes_do_not_replace_platform_authority(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    authority = tmp_path / "docs/platform/README.md"
    policy.Text_AtomicWrite(authority, "Current platform authority\n")
    builtin = tmp_path / "staging/builtin"
    note = builtin / "component/docs/detail.md"
    policy.Text_AtomicWrite(note, "# Reference implementation\n")
    _PackageDocumentation_Annotate(builtin, policy)
    assert "Package-local implementation note" in note.read_text(encoding="utf-8")
    assert "docs/platform/README.md" in note.read_text(encoding="utf-8")
    before = (note.read_bytes(), note.stat().st_mtime_ns)
    _PackageDocumentation_Annotate(builtin, policy)
    assert (note.read_bytes(), note.stat().st_mtime_ns) == before
    assert authority.read_text(encoding="utf-8") == "Current platform authority\n"
    with pytest.raises(ValueError, match="builtin package root"):
        _PackageDocumentation_Annotate(tmp_path / "docs", policy)
    with pytest.raises(ValueError, match="builtin package root"):
        _PackageDocumentation_Annotate(tmp_path / "docs/platform/builtin", policy)


def test_installed_builtin_notes_defer_to_current_docs():
    notes = list((ROOT / "plugins/builtin").glob("*/docs/**/*.md"))
    assert notes
    for note in notes:
        assert note.read_text(encoding="utf-8").startswith(
            "<!-- FCCG package-local documentation -->"
        ), note

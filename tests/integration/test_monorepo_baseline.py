from __future__ import annotations

import json
import hashlib
import pytest
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()


def _Python_Run(code: str, *paths: Path) -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in paths)
    return subprocess.check_output(
        [sys.executable, "-c", code], cwd=ROOT, env=env, text=True
    ).strip()


def test_one_release_version_and_independent_freertos_version() -> None:
    assert VERSION == "0.1.1"
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert package["project"]["dynamic"] == ["version"]
    assert package["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "tools.silverstar_version.__version__"
    assert subprocess.check_output([sys.executable, "SCG.py", "--version"], cwd=ROOT, text=True).strip() == VERSION
    assert subprocess.check_output([sys.executable, "FLP.py", "--version"], cwd=ROOT, text=True).strip() == VERSION
    assert _Python_Run("from config import APP_VERSION; print(APP_VERSION)", ROOT / "apps/GSHC") == VERSION
    manifests = sorted((ROOT / "apps/FCCG/plugins/builtin").glob("*/plugin.json"))
    assert manifests
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        # Plugin identities remain independent of the product patch release.
        expected = "11.3.0" if manifest["id"] == "silverstar.os.freertos_11_3_0" else "0.1.0"
        assert manifest["version"] == expected, path
    core = ROOT / "apps/FCCG/plugins/builtin/silverstar_core_0_1_0/plugin.json"
    assert json.loads(core.read_text(encoding="utf-8"))["id"] == "silverstar.core.0_1_0"
    gshc_version_info = _Python_Run(
        "import runpy; f=runpy.run_path('apps/GSHC/packaging/product_version.py')['ProductVersionResource_Create']; print(f())")
    gshc_installer = (ROOT / "apps/GSHC/installer/SilverStar_GSHC.iss").read_text(encoding="utf-8")
    assert f"StringStruct('ProductVersion', '{VERSION}')" in gshc_version_info
    assert '#define MyAppVersion Trim(FileRead(ProductVersionFile))' in gshc_installer
    assert 'VERSION' in gshc_installer


def test_one_navigation_contract_for_all_consumers() -> None:
    canonical = ROOT / "contracts/navigation_v1.json"
    assert canonical.is_file()
    assert list(ROOT.glob("apps/**/navigation_v1.json")) == []
    assert list(ROOT.glob("docs/**/navigation_v1.json")) == []
    contract = json.loads(canonical.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/plugin.json").read_text(encoding="utf-8"))
    parameters = {item["id"]: {key: item[key] for key in ("type", "default", "unit", "representation", "min", "max")} for item in manifest["algorithm_parameters"]["parameters"]}
    assert parameters == contract["eskf15"]["parameters"]
    flp_value = _Python_Run(
        "from silverstar_flp.plugins.algorithms.eskf15.plugin import CONTRACT; print(CONTRACT['eskf15']['component_id'])",
        ROOT / "apps/FLP/src",
    )
    assert flp_value == contract["eskf15"]["component_id"]
    gshc_doc = (ROOT / "docs/GSHC/JOINT_GSHC_STATUS.md").read_text(encoding="utf-8")
    assert "../../contracts/navigation_v1.json" in gshc_doc


def test_root_launchers_create_offscreen_gui_without_old_source() -> None:
    for name in ("SCG", "GSHC", "FLP"):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["SILVERSTAR_GSHC_DATA_ROOT"] = str(ROOT / ".work/gshc-test-data")
        process = subprocess.Popen(
            [sys.executable, str(ROOT / f"{name}.py")], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            time.sleep(2)
            assert process.poll() is None, f"{name} exited during startup"
        finally:
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
        assert "Traceback" not in stdout + stderr
    for app in ("FCCG", "GSHC", "FLP"):
        for current, dirs, files in os.walk(ROOT / "apps" / app):
            dirs[:] = [
                name for name in dirs
                if name not in {".work", ".venv", "build", "dist", "joint_rework_20260927"}
            ]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = Path(current) / name
                assert not re.search(
                    r"[A-Za-z]:[/\\]python_software[/\\]SilverStar_(?:FCCG|GSHC|FLP)",
                    path.read_text(encoding="utf-8"),
                ), path


def _DocumentLinkDirectory_Get(source: Path, repository_root: Path) -> Path:
    if source.name not in {"AGENTS_SNAPSHOT.md", "REPORT_SNAPSHOT.md"}:
        return source.parent
    index = json.loads((source.parent / "INDEX.json").read_text(encoding="utf-8"))
    entries = {entry["file"]: entry for entry in index["entries"]}
    entry = entries[source.name]
    # Archived source is byte-for-byte evidence. Resolve its original relative
    # links at the indexed source location, rather than rewriting the archive.
    assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"], source
    origin_root = PureWindowsPath(entries["AGENTS_SNAPSHOT.md"]["source"]).parent
    relative_source = PureWindowsPath(entry["source"]).relative_to(origin_root)
    current_source = repository_root.joinpath(*relative_source.parts)
    assert current_source.is_file(), current_source
    return current_source.parent


def _DocumentLinks_Validate(source: Path, repository_root: Path) -> None:
    directory = _DocumentLinkDirectory_Get(source, repository_root)
    body = source.read_text(encoding="utf-8")
    body = re.sub(r"(?ms)^ *(`{3,}|~{3,})[^\n]*\n.*?^ *\1 *$", "", body)
    for target in re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)", body):
        url = urlsplit(target.strip("<>"))
        if url.scheme or url.netloc or not url.path:
            continue
        assert (directory / unquote(url.path)).resolve().exists(), (source, target)


def test_current_document_links_resolve() -> None:
    sources = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for source in sources:
        if source.name in {"VALIDATION.md", "CHANGELOG.md"} or "history" in source.parts:
            continue
        _DocumentLinks_Validate(source, ROOT)


def test_indexed_snapshot_links_still_reject_missing_targets_and_changed_bytes(tmp_path) -> None:
    repository = tmp_path / "repository"
    archive = repository / "docs" / "evidence"
    archive.mkdir(parents=True)
    (repository / "AGENTS.md").write_text("Original source location", encoding="utf-8")
    source = archive / "AGENTS_SNAPSHOT.md"
    source.write_text("[target](docs/target.md)", encoding="utf-8")
    (archive / "INDEX.json").write_text(json.dumps({"entries": [{
        "file": source.name, "source": r"D:\original\SilverStar\AGENTS.md",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }]}), encoding="utf-8")
    with pytest.raises(AssertionError):
        _DocumentLinks_Validate(source, repository)
    (repository / "docs" / "target.md").write_text("Target", encoding="utf-8")
    _DocumentLinks_Validate(source, repository)
    source.write_text("Changed archive", encoding="utf-8")
    with pytest.raises(AssertionError):
        _DocumentLinks_Validate(source, repository)


def test_disposable_work_is_ignored_and_no_nested_repositories() -> None:
    for relative in (".work/probe.txt", ".venv/probe.txt"):
        assert subprocess.run(["git", "check-ignore", "-q", relative], cwd=ROOT, check=False).returncode == 0
    for app in ("FCCG", "GSHC", "FLP"):
        subtree = ROOT / "apps" / app
        for current, dirs, _files in os.walk(subtree):
            assert ".git" not in dirs, current
            assert ".venv" not in dirs, current
            dirs[:] = [name for name in dirs if name not in {".work", "build", "dist"}]


def test_root_has_only_public_launchers_and_legacy_scg_still_starts():
    assert {p.name for p in ROOT.glob("*.py")} == {"SCG.py", "GSHC.py", "FLP.py"}
    assert subprocess.check_output([sys.executable, "apps/FCCG/FCCG.py", "--version"], cwd=ROOT, text=True).strip() == VERSION

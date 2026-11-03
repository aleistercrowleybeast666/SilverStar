"""Stage a Windows candidate after the shared spec finishes its three analyses."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from importlib import metadata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_owners(entries):
    required = {
        Path(source).resolve()
        for _, _, source in entries
        if "site-packages" in Path(source).parts and Path(source).is_file()
    }
    found = defaultdict(set)
    owners = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "")
        for record in dist.files or ():
            path = Path(dist.locate_file(record)).resolve()
            if path not in required or not record.hash or record.hash.mode != "sha256":
                continue
            actual = (
                base64.urlsafe_b64encode(bytes.fromhex(digest(path)))
                .rstrip(b"=")
                .decode()
            )
            if actual == record.hash.value:
                found[path].add(name)
                owners[name] = dist
    return found, owners, sorted(str(path) for path in required - found.keys())


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )


def stage(bundle: Path, evidence: Path, witness: Path, output: Path):
    if not all(
        (bundle / name).is_file() for name in ("SCG.exe", "GSHC.exe", "FLP.exe")
    ):
        raise ValueError("Missing one or more candidate executables")
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists() or (bundle / "licenses").exists():
        raise FileExistsError("Use a fresh candidate bundle and archive destination")
    entries = json.loads(
        (evidence / "resolved-runtime-inputs.json").read_text(encoding="utf8")
    )
    for kind, destination, _source in entries:
        if (
            kind in ("binary", "data")
            and not (bundle / "_internal" / destination).is_file()
        ):
            raise FileNotFoundError(f"Collected {kind} missing: {destination}")
    owners, distributions, unresolved = wheel_owners(entries)
    licenses = bundle / "licenses"
    licenses.mkdir()
    package_rows = []
    counts = Counter(name for values in owners.values() for name in values)
    build_tools = {
        name: metadata.distribution(name)
        for name in ("pyinstaller", "pyinstaller-hooks-contrib")
    }
    for name, dist in sorted((distributions | build_tools).items()):
        texts = []
        for record in dist.files or ():
            part = Path(record)
            if part.is_absolute() or ".." in part.parts:
                continue
            if not (
                re.match(
                    r"(?i)^(licen[cs]e|copying|copyright|notice|authors)(?:[._-]|$)",
                    part.name,
                )
                or (
                    "licenses" in [s.lower() for s in part.parts]
                    and part.suffix.lower() in (".md", ".txt")
                )
            ):
                continue
            source = Path(dist.locate_file(record))
            if not source.is_file():
                continue
            category = (
                "build-runtime-notices" if name in build_tools else "python-packages"
            )
            target = licenses / category / name / part
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            texts.append(target.relative_to(licenses).as_posix())
        package_rows.append(
            {
                "name": name,
                "version": dist.version,
                "matched_inputs": counts[name],
                "license_metadata": dist.metadata.get("License-Expression")
                or dist.metadata.get("License"),
                "files": texts,
            }
        )
    versions = {normalized(name): dist.version for name, dist in distributions.items()}
    witness_texts = []
    # Older binary output is never copied. Recover only original notices for the same
    # runtime versions (including notices absent from the Python wheels).
    with zipfile.ZipFile(witness) as old:
        catalog = json.loads(old.read("SilverStar/licenses/DEPENDENCIES.json"))
        expected = catalog["source_versions"]
        if not (
            versions.get("pyside6-essentials") == expected["Qt"]
            and versions.get("shiboken6") == expected["Shiboken6"]
            and sys.version.split()[0] == expected["Python"]
        ):
            raise ValueError("Original Qt/Python notice witness version differs")
        for entry in old.infolist():
            if not entry.filename.startswith("SilverStar/licenses/") or entry.is_dir():
                continue
            relative = PurePosixPath(entry.filename).relative_to("SilverStar/licenses")
            if relative.parts[0] in (
                "python-packages",
                "build-runtime-notices",
                "DEPENDENCIES.json",
                "README.md",
            ):
                continue
            if any(
                p in (".", "..") or ":" in p for p in relative.parts
            ) or relative.suffix.lower() not in (
                ".txt",
                ".md",
                ".rst",
                ".src",
                ".json",
                "",
            ):
                continue
            if relative.name == "Matplotlib-FreeType-2.6.1-FTL.txt":
                from matplotlib.ft2font import __freetype_version__

                if "matplotlib" not in versions or __freetype_version__ != "2.6.1":
                    continue
            if (
                relative.parts[0].lower().startswith("pyopengl")
                and versions.get("pyopengl") != "3.1.10"
            ):
                continue
            if (
                "pyserial" in relative.name.lower()
                and versions.get("pyserial") != "3.5"
            ):
                continue
            target = licenses / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old.read(entry))
            witness_texts.append(str(relative))
    write_json(
        licenses / "DEPENDENCIES.json",
        {
            "packages": package_rows,
            "original_notice_witness": witness.name,
            "witness_sha256": digest(witness),
            "witnessed_texts": witness_texts,
            "unmatched_site_inputs": [Path(p).name for p in unresolved],
            "runtime": sys.version.split()[0],
        },
    )
    write_json(
        evidence / "wheel-attribution.json",
        {
            "unmatched_paths": unresolved,
            "multiply_owned": {
                str(p): sorted(v) for p, v in owners.items() if len(v) > 1
            },
            "packages": {p["name"]: p["matched_inputs"] for p in package_rows},
        },
    )
    shutil.copyfile(ROOT / "LICENSE", bundle / "LICENSE")
    for name in (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--", "docs/public"], cwd=ROOT
        )
        .decode()
        .split("\0")
    ):
        if name and (ROOT / name).is_file():
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (bundle / "README.md").write_text(
        """# SilverStar Windows 发布候选

解压整个目录后分别运行 SCG.exe、GSHC.exe、FLP.exe。三个程序共用 _internal。
操作见 [桌面工作流](docs/public/USER_WORKFLOW.md)。地面站到电脑使用 UART 或外部 USB-UART 桥。
本包用于软件验收，实机验证与正式发布状态见交付记录。许可证与依赖清单在 licenses 目录。
Qt/PySide 与应用动态链接，对应源码与构建信息见 [Qt](https://code.qt.io/cgit/qt/qtbase.git/)
及 [Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/) 的 v6.10.1 版本。
可更换兼容的动态库并调试这些修改。
""",
        encoding="utf8",
    )
    inventory = {
        p.relative_to(bundle).as_posix(): digest(p)
        for p in sorted(bundle.rglob("*"))
        if p.is_file()
    }
    write_json(
        bundle / "CANDIDATE_MANIFEST.json", {"code_commit": head, "files": inventory}
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=5
    ) as archive:
        for p in sorted(bundle.rglob("*")):
            if p.is_file():
                archive.write(p, "SilverStar/" + p.relative_to(bundle).as_posix())
    with zipfile.ZipFile(partial) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC verification failed")
    partial.rename(output)
    write_json(
        evidence / "candidate.json",
        {
            "code_commit": head,
            "archive": str(output),
            "sha256": digest(output),
            "bytes": output.stat().st_size,
            "bundle": str(bundle),
            "runtime_input_count": len(entries),
            "executable_sha256": {
                n: inventory[n] for n in ("SCG.exe", "GSHC.exe", "FLP.exe")
            },
            "unmatched_site_inputs": len(unresolved),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle", "evidence", "witness", "output"):
        parser.add_argument(key, type=Path)
    opts = parser.parse_args()
    stage(
        opts.bundle.resolve(),
        opts.evidence.resolve(),
        opts.witness.resolve(),
        opts.output.resolve(),
    )

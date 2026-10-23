"""Single product parser; versions.json references independent authorities.

VERSION is the only manually maintained product number. This module does not
infer hardware acceptance, source provenance or numerical fidelity.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


def _Pairs_Read(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate version-manifest key: " + key)
        result[key] = value
    return result


def _Json_Read(path):
    data = path.read_bytes()
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Version source is too large: " + str(path))
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_Pairs_Read)


def _SourcePath_Resolve(root, relative):
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
        raise ValueError("Unsafe version source path")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved.is_symlink():
        raise ValueError("Version source leaves its root")
    return resolved


@dataclass(frozen=True, slots=True)
class ProductVersion:
    full: str
    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build_metadata: str = ""

    @property
    def numeric(self):
        return self.major, self.minor, self.patch

    @property
    def package(self):
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            match = re.fullmatch(r"(alpha|beta|rc|dev)\.(0|[1-9][0-9]*)", self.prerelease)
            if match is None:
                raise ValueError("Packaging supports alpha.N, beta.N, rc.N or dev.N")
            label = {"alpha": "a", "beta": "b", "rc": "rc", "dev": ".dev"}[match[1]]
            base += label + match[2]
        if self.build_metadata:
            if re.fullmatch(r"[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*", self.build_metadata) is None:
                raise ValueError("Python package metadata requires dot-separated alphanumeric identifiers; "
                                 "hyphens cannot be projected without changing identifier boundaries")
            # PEP 440 canonicalizes case and numeric local segments. Keep full
            # SemVer unchanged for display, firmware and provenance.
            base += "+" + ".".join(str(int(part)) if part.isdigit() else part.lower()
                                   for part in self.build_metadata.split("."))
        return base

    @property
    def windows(self):
        if any(part > 65535 for part in self.numeric):
            raise ValueError("Windows version components exceed 16-bit fields")
        return (*self.numeric, 0)

    @property
    def artifact_suffix(self):
        return re.sub(r"[^0-9A-Za-z]+", "_", self.full)

    @property
    def firmware_tag(self):
        if not self.prerelease and not self.build_metadata and self.major < 10 and self.minor < 10 and self.patch < 100:
            return f"SILV{self.major}{self.minor}{self.patch:02d}"
        return "V" + hashlib.sha256(self.full.encode("ascii")).hexdigest()[:7].upper()


def ProductVersion_Parse(value):
    if not isinstance(value, str) or len(value) > 96:
        raise ValueError("Product version requires a bounded SemVer string")
    match = _SEMVER.fullmatch(value)
    if match is None:
        raise ValueError("Product version must be SemVer major.minor.patch")
    prerelease, metadata = match[4] or "", match[5] or ""
    if any(p.isdigit() and len(p) > 1 and p[0] == "0" for p in prerelease.split(".")):
        raise ValueError("Numeric prerelease identifiers cannot have leading zeros")
    return ProductVersion(value, *(int(match[i]) for i in (1, 2, 3)), prerelease, metadata)


def VersionManifest_Load(root=ROOT):
    manifest = _Json_Read(Path(root) / "versions.json")
    if manifest.get("schema") != "silverstar.version-registry/1":
        raise ValueError("Unsupported version registry")
    product = manifest.get("product", {})
    if set(product) != {"source_file", "maturity"} or product["source_file"] != "VERSION":
        raise ValueError("Product version has exactly one authority: VERSION")
    if product["maturity"] not in ("development", "release"):
        raise ValueError("Unknown product maturity")
    return manifest


def ReleaseIdentity_Load(root=ROOT):
    root = Path(root)
    manifest = VersionManifest_Load(root)
    value = _SourcePath_Resolve(root, manifest["product"]["source_file"]).read_text(encoding="ascii").strip()
    version = ProductVersion_Parse(value)
    version.package
    return version


def FirmwareIdentity_Resolve(requested_version, *, root=ROOT, test_identity=None):
    root = Path(root)
    product = ReleaseIdentity_Load(root)
    legacy_spelling = isinstance(requested_version, str) and re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", requested_version) is not None
    requested = ProductVersion_Parse(requested_version + ".0" if legacy_spelling else requested_version)
    if any(part > 255 for part in requested.numeric):
        raise ValueError("Firmware version components exceed existing u8 fields")
    maturity = VersionManifest_Load(root)["product"]["maturity"]
    if maturity == "release" and (requested_version != product.full or test_identity is not None):
        raise ValueError("Release firmware must match the product and cannot use a test identity")
    number, tag = 0, requested.firmware_tag
    fields = f" product_version={requested_version} maturity={maturity}"
    if requested_version != product.full:
        fields += f" generator_version={product.full} legacy_requested=1"
    if test_identity is not None:
        if legacy_spelling:
            raise ValueError("Explicit test firmware requires three version fields")
        number, tag = test_identity["build_number"], test_identity["build_tag"]
        if (type(number) is not int or not 1 <= number <= 255 or not isinstance(tag, str)
                or re.fullmatch(r"[A-Z0-9]{8}", tag) is None
                or re.fullmatch(r"[A-Z][A-Z0-9_]{0,47}", test_identity["id"]) is None
                or re.fullmatch(r"[0-9a-f]{40}", test_identity["source_commit"]) is None):
            raise ValueError("Invalid bounded test build identity")
        fields = (f" build={number} kind=test build_tag={tag} "
                  f"source_commit={test_identity['source_commit']} test_id={test_identity['id']} "
                  f"product_version={requested_version}")
    if len(fields) > 240:
        raise ValueError("Firmware identity exceeds its bounded text policy")
    result = {
        "schema": "silverstar.version-identity/1",
        "product_version": product.full, "firmware_version": requested_version,
        "product_version_matches": requested_version == product.full,
        "maturity": "test" if test_identity else maturity,
        "numeric_version": list(requested.numeric), "build_number": number,
        "log_build_tag": tag, "runtime_identity_fields": fields,
        "registry_sha256": hashlib.sha256((root / "versions.json").read_bytes()).hexdigest(),
        "version_source_sha256": hashlib.sha256((root / "VERSION").read_bytes()).hexdigest(),
        "evidence_scope": "version declaration; source/artifact evidence remains in owning build audit",
    }
    if legacy_spelling:
        result["legacy_numeric_projection"] = "two-part request retained; patch=0 in numeric compatibility fields"
    return result


def VersionSource_Read(root, source):
    path = _SourcePath_Resolve(Path(root), source["path"])
    kind = source["kind"]
    if kind == "json":
        value = _Json_Read(path)
        for key in source["selector"]:
            value = value[key]
        return value
    if kind == "python_constant":
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == source["name"] for t in node.targets):
                return ast.literal_eval(node.value)
        raise ValueError("Missing version constant: " + source["name"])
    if kind == "text_pattern":
        matches = re.findall(source["pattern"], path.read_text(encoding="utf-8-sig"), re.MULTILINE)
        if len(matches) != 1:
            raise ValueError("Version source is missing or ambiguous")
        return matches[0]
    raise ValueError("Unknown version source reader")


def VersionInventory_Resolve(root=ROOT, *, source_root=None):
    root = Path(root)
    manifest, version = VersionManifest_Load(root), ReleaseIdentity_Load(root)
    source_root = Path(source_root) if source_root is not None else root
    identities = {}
    for name, entry in manifest["identities"].items():
        if entry.get("version") == "product":
            value = version.full
        else:
            source = entry["source"]
            owner = root if (root / source["path"]).is_file() else source_root
            source_path = _SourcePath_Resolve(owner, source["path"])
            if not source_path.exists() and entry.get("source_required") is False:
                identities[name] = {"value": None, "scope": entry["scope"],
                    "status": "source_unavailable", "source_path": source["path"]}
                continue
            value = VersionSource_Read(owner, source)
        identities[name] = {"value": value, "scope": entry["scope"], "status": "resolved"}
    plugins = {}
    for path in sorted((source_root / "apps/SCG/plugins/builtin").glob("*/plugin.json")):
        data = _Json_Read(path)
        plugins[data["id"]] = {"version": data["version"], "path": path.relative_to(source_root).as_posix()}
    contracts = {}
    identity_fields = {"$id", "schema_id", "contract", "version", "contract_version",
                       "schema_version", "protocol_version", "revision", "versions",
                       "component_version", "quality_policy_revision", "format", "contract_id", "name"}
    for path in sorted((source_root / "contracts").rglob("*.json")):
        data = _Json_Read(path)
        contracts[path.relative_to(source_root).as_posix()] = {
            "declared_identity": {key: value for key, value in data.items() if key in identity_fields},
            "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    catalog = _Json_Read(source_root / "apps/SCG/plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema/sslog_schema.json")
    records = [{"id": row["id"], "name": row["name"], "version": row["version"],
                "payload_size": row["payload_size"],
                "entry_content_sha256": hashlib.sha256(json.dumps(row, sort_keys=True,
                    separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()}
               for row in catalog["records"]]
    return {"schema": manifest["schema"], "product": version.full,
            "maturity": manifest["product"]["maturity"], "python_package": version.package,
            "windows_numeric": version.windows, "identities": identities,
            "plugins": plugins, "contracts": contracts, "records": records,
            "record_digest_scope": "one catalog entry only; excludes catalog-wide defaults and semantics; informational, never decoder authorization",
            "compatibility": manifest["compatibility"]}


def _Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(VersionInventory_Resolve(args.root, source_root=args.source_root), ensure_ascii=False, indent=2))


__version__ = ReleaseIdentity_Load().package

if __name__ == "__main__":
    _Main()

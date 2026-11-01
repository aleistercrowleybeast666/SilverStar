"""Sealed exact compilation and linked-artifact review, never self-enrollment."""
import hashlib
import json
from pathlib import Path
import re
import shutil


def FileHash_Get(path, *, source=False):
    raw = path.read_bytes()
    if source:
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def InputPath_Get(root, name):
    path = root / name
    if Path(name).is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Unsafe or missing software stack proof input: " + name)
    return path


def ArtifactPaths_Get(root, graph):
    names = {Path(source).with_suffix(suffix).as_posix()
             for source in graph['sources'] for suffix in ('.o', '.su', '.d')}
    manifest = (root / 'Generated/project_sources.mk').read_text(encoding='utf8')
    assembly = re.search(r'(?ms)^ASM_SOURCES \+= \\\n(.*?)(?:\n\n|\Z)', manifest)
    if assembly is None:
        raise ValueError('Missing selected assembly input closure')
    names.update(Path(line.strip().removesuffix('\\').strip()).with_suffix('.o').as_posix()
                 for line in assembly[1].splitlines())
    names.update((graph['elf'].name, graph['elf'].with_suffix('.map').name))
    return sorted(names)


def Executable_Get(value):
    path = Path(value)
    if not path.is_file():
        found = shutil.which(value)
        if found is None:
            raise ValueError('Missing actual stack tool executable: ' + value)
        path = Path(found)
    return path.resolve()


def ToolchainInputs_Get(root, graph, prefix, command_read):
    """All linked external LOAD inputs plus the compiler tools and headers.

    The map is itself sealed byte-for-byte. No archive filename is inferred
    from a convenient compiler default that may select a different multilib.
    """
    driver = Executable_Get(prefix + 'gcc')
    files = {driver}
    for tool in ('objdump', 'nm', 'readelf'):
        files.add(Executable_Get(prefix + tool))
    for tool in ('cc1', 'as', 'ld', 'collect2'):
        files.add(Executable_Get(command_read([str(driver), '-print-prog-name=' + tool], root).strip()))
    map_text = graph['elf'].with_suffix('.map').read_text(encoding='utf8')
    externals = set()
    for line in map_text.splitlines():
        if not line.startswith('LOAD ') or line == 'LOAD linker stubs':
            continue
        path = Path(line[5:])
        if not path.is_absolute():
            InputPath_Get(root, path.as_posix())
        else:
            if not path.is_file():
                raise ValueError('Missing actual external linker input: ' + str(path))
            externals.add(path.resolve())
    if not any(path.name == 'libgcc.a' for path in externals) or not any(path.name.startswith('libc') for path in externals):
        raise ValueError('Missing actual compiler/runtime archive closure')
    files.update(externals)
    declarations = [root / 'Makefile', *root.glob('Targets/*/target.mk')]
    specs = set().union(*(set(re.findall(r'-specs=([\w.-]+)', path.read_text(encoding='utf8')))
                         for path in declarations))
    for spec in specs:
        value = command_read([str(driver), '-print-file-name=' + spec], root).strip()
        if value == spec or not Path(value).is_file():
            raise ValueError('Missing selected compiler specs: ' + spec)
        files.add(Path(value).resolve())
    # All installed C ABI headers are input, including compiler-provided
    # headers omitted by -MMD. The build's project headers are sealed separately.
    include_roots = {driver.parent.parent / 'arm-none-eabi/include'}
    for name in ('include', 'include-fixed'):
        include_roots.add(Path(command_read([str(driver), '-print-file-name=' + name], root).strip()))
    for directory in include_roots:
        if not directory.is_dir():
            raise ValueError('Missing compiler ABI header directory: ' + str(directory))
        files.update(path.resolve() for path in directory.rglob('*') if path.is_file())
    return {path.as_posix(): FileHash_Get(path) for path in sorted(files)}


def ReviewDocument_Verify(root, case):
    name = case.get('review_document')
    if not isinstance(name, str) or not name.startswith('Tools/'):
        raise ValueError('Missing software runtime/manual closure review document')
    path = InputPath_Get(root, name)
    if FileHash_Get(path) != case.get('review_document_sha256'):
        raise ValueError('Changed software runtime/manual closure review document')
    if not case.get('runtime_contract'):
        raise ValueError('Missing reviewed software runtime contract')


def Inputs_Verify(root, graph, configuration, prefix, command_read, manifest_path, manifest_sha256):
    if not manifest_path.is_file() or FileHash_Get(manifest_path) != manifest_sha256:
        raise ValueError("Unreviewed software stack manifest")
    review = json.loads(manifest_path.read_text(encoding="utf8"))
    if review.get("schema") != "silverstar.software-stack-inputs/1":
        raise ValueError("Unsupported software stack proof schema")
    target = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf8"))["build"]["target_profile"]
    declarations = {"Makefile", *(path.relative_to(root).as_posix() for path in root.rglob("*.mk")
        if path.relative_to(root).parts[0] not in ("build", ".git", ".fccg"))}
    if not (root / "Makefile").is_file():
        return None  # Legacy unit fixtures do not describe a whole firmware.
    declaration_hashes = {name: FileHash_Get(InputPath_Get(root, name), source=True) for name in sorted(declarations)}
    candidates = [case for case in review["cases"] if case["target_profile"] == target and
                  case["configuration"] == configuration and case["build_declarations"] == declaration_hashes]
    if not candidates:
        return None  # The existing strict legacy verifier remains authoritative.
    source_inputs = {*graph["sources"], *(path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in (".h", ".inc", ".s", ".ld") and
        path.relative_to(root).parts[0] not in ("build", ".git", ".fccg"))}
    hashes = {name: FileHash_Get(InputPath_Get(root, name), source=True) for name in sorted(source_inputs)}
    cases = [case for case in candidates if case["source_inputs"] == hashes and case["sources"] == sorted(graph["sources"])]
    if len(cases) != 1:
        raise ValueError("Changed or ambiguous complete software stack input closure")
    case = cases[0]
    if command_read([prefix + "gcc", "--version"], root).splitlines()[0] != case["compiler"]:
        raise ValueError("Unreviewed software stack compiler")
    expected_artifacts = set(ArtifactPaths_Get(root, graph))
    if set(case["compiled_artifacts"]) != expected_artifacts:
        raise ValueError("Incomplete sealed compiled stack artifact set")
    for name, expected in case["compiled_artifacts"].items():
        if FileHash_Get(InputPath_Get(graph["build"], name)) != expected:
            raise ValueError("Changed linked/compiler stack artifact: " + name)
    if ToolchainInputs_Get(root, graph, prefix, command_read) != case['toolchain_files']:
        raise ValueError('Changed or incomplete reviewed compiler/library input closure')
    ReviewDocument_Verify(root, case)
    return {"case": case, "review_revision": review["review_revision"], "source_proofs": [
        {"source": source, "normalized_source_sha256": hashes[source],
         "review_revision": review["review_revision"], "review_case": case["name"]}
        for source in graph["sources"]]}

# Shared Windows bundle

Run the existing Python environment's `-m PyInstaller` with `SilverStar_shared.spec`, explicit external `--distpath` / `--workpath`, and `SILVERSTAR_PACKAGE_EVIDENCE` pointing at the evidence directory. Set TEMP, TMP and PYINSTALLER_CONFIG_DIR to dedicated build directories. No tool installation is performed by this configuration.

Three independent Analysis/PYZ/EXE objects feed one COLLECT. Conflicting dependency bytes at a shared destination fail the build. First-party application modules are analyzed to discover dependencies, then distributed as unchanged source at their original apps/src paths, preserving relative VERSION/contracts/plugin/resource lookups. The normal main.py files run via dedicated packaging entries; application code is not patched.

Unused Qt PDF and virtual-keyboard plugins and their QtQuick/QML dependencies are excluded. Python/Qt dependencies stay dynamically loadable in `_internal`; do not combine separately collected dist directories. The final license inventory must derive from all three actual Analysis TOCs and collected output, not a source-only list.

The collection refuses to run when D free space is below 8 GiB. Inspect space before every large build/archive/extraction step. Offline QA and receipts belong outside the shipped distribution.

Windows 10/11 supplies the unversioned ICU imported by this Qt wheel. Exclude PATH-resolved Poppler ICU and use one unchanged MSVC CRT family from the installed PySide6 wheel; keep uniquely hashed vendor CRT names. Remove incompatible optional x86 PyOpenGL DLLs from the Win64 bundle. The developer-only compare_reference_project.py and nrf24_validate.py stay in the repository and is omitted from distribution.

After COLLECT, stage public documentation and original dependency license texts. Record any portable provenance JSON or document-link mapping with source and distribution hashes; application Python/C/H code must remain byte-for-byte unchanged. Keep temporary QA executables and evidence outside the final ZIP. This configuration does not itself publish, move tags, or sanitize Git history.

The active [build_candidate.ps1](build_candidate.ps1) runs the ordinary spec and then `stage_candidate.py`. Supply new destination, evidence and working directories, an explicit build tag, and the 0.1.2 portable archive that carries the original upstream notices. The staging step checks notice versions, verifies collected first-party files against the committed checkout, and records archive and executable SHA-256 values in `candidate.json`. The dated 2026-11-03 script and its results remain historical evidence.

```powershell
./tools/packaging/build_candidate.ps1 `
  -BuildTag gui-convergence-20261110 `
  -Destination "$PWD/dist/gui-convergence-20261110" `
  -Evidence "$PWD/.work/gui-convergence-20261110/package/evidence" `
  -BuildWork "$PWD/.work/gui-convergence-20261110/package/build" `
  -NoticeWitness 'D:/SilverStar_Archive/retained_inputs/SilverStar_0_1_2_Windows_Portable.zip'
```

The external notice witness is an exact hash-verified copy; do not remove the last copy before extracting and validating an equivalent original-notice input. Build outputs stay outside tracked source. `tools/check_repository_artifacts.py --base <commit>` checks only changed Git blobs; necessary small vendor/fixture exceptions are explained in `tools/repository_artifacts.json`, and never exempt workspace paths or the size limit.

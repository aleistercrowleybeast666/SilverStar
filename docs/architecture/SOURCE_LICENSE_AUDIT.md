# Source license and dependency audit (2026-09-30)

The repository root [LICENSE](../../LICENSE) contains the unmodified Apache License 2.0 text. The project owner approved Apache-2.0 for SilverStar first-party source. This records the intended license of original SilverStar code; it does not transfer rights, establish a copyright holder, or relicense third-party material. Git author names, product labels, and a GitHub account do not establish legal ownership. A reviewed first-party copyright attribution remains a release task.

## Included source and evidence level

| Material | Current evidence | Status / action before distribution |
| --- | --- | --- |
| SilverStar first-party Python, C, tests and docs | Owner-approved Apache-2.0; root LICENSE | Scope stated; copyright attribution needs owner review |
| FreeRTOS Kernel 11.3.0 | Bundled `LICENSE.md` states MIT | Preserve vendor notice and version; do not apply first-party license |
| ST HAL/CMSIS device and CubeMX output | Bundled ST source headers and some license files refer to package license or fallback BSD-3-Clause/Apache-2.0 | Map every included file to the exact ST package/license before binary distribution; retain source notices |
| CMSIS Core | Bundled Apache-2.0 notice | Preserve notice; confirm exact included version in package manifest |
| FatFs R0.12c | Bundled ChaN source header and redistribution terms | Retain header/notice in any source or binary distribution |
| Bosch BMI088 support | Bundled Bosch copyright and BSD-3-Clause license | Preserve separate Bosch terms |
| Semtech SX1280lib | Source says revised BSD and refers to `LICENSE.TXT`; referenced file was not found in the imported subtree | Obtain authoritative matching license text and verify provenance before distribution |
| Imported CubeMX board snapshots | Generated-source/vendor copyright headers | Verify the exact generated-file license set and preserve notices |

These are source-tree observations, not a complete binary bill of materials. The checker-generated first-party C set, header files, vendor files, and packaged dependencies have different scopes.

## Python environment

The root `pyproject.toml` specifies lower bounds rather than a lockfile. The locally tested interpreter was Python 3.14.0 on Windows 11. Installed packages during this audit included PySide6/Essentials/Addons/shiboken6 6.10.1, NumPy 2.4.0, matplotlib 3.10.8, pyqtgraph 0.14.0, PyOpenGL 3.1.10, Pillow 12.0.0, pyserial 3.5, PyYAML 6.0.3, pytest 9.1.1, pytest-qt 4.5.0, ruff 0.16.9, PyInstaller 6.16.0 and packaging 25.0. Those installed versions describe this local test environment only; they are not a locked release dependency set. In particular, PyOpenGL's installed metadata did not establish a reliable license conclusion. Other package metadata and transitive dependencies require verification for the exact release environment.

Installed package metadata reported NumPy as a combination of BSD-3-Clause/0BSD/MIT/Zlib/CC0 terms, matplotlib's own license and font terms, pyqtgraph as MIT plus a CC-BY color map, Pillow as MIT-CMU, pyserial as BSD, PyYAML and the local test packages as MIT, packaging as Apache/BSD, and PyInstaller as GPL with a special exception. These are **metadata declarations**, not a reviewed bill of materials or a determination that all distribution obligations have been met. In particular, a package's embedded assets and the modules actually collected into a binary still need separate review.

[Qt for Python licensing](https://doc.qt.io/qtforpython-6/) lists commercial and open-source options. [Qt's module licensing](https://doc.qt.io/qt-6/licensing.html) varies by module. Before shipping binaries, inspect the actual collected Qt libraries, plugins and modules, including any GPL-only material, then determine the applicable license option, notices and delivery obligations. No PyInstaller bundle, installer or final Qt collection was built or inspected in this source-only task. PyInstaller itself is a development/package dependency and has its own license exception; it does not make an application automatically compliant.

## Deferred release checks

1. Review first-party rightsholder attribution and third-party file provenance, including Semtech and ST package evidence.
2. Lock and audit exact Python dependency/transitive versions for the intended distribution.
3. Build a real Windows distribution and inventory every collected binary, Qt plugin, font and data asset against its license and notice obligations.
4. Recheck bundled LICENSE/NOTICE delivery and final Windows application/installer behavior.

This audit does not provide legal assurance or gate unrelated local source repair or controlled KF6 bench preparation.

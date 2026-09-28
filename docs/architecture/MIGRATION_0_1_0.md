# SilverStar 0.1.0 first monorepo migration

**This is a pre-release monorepo migration. No public 0.1.0 release has been made.**

## Source snapshots and working-tree decisions

| Former repository | Initial HEAD on inspection | Final-record HEAD, branch | Tracked local change recorded before migration |
| --- | --- | --- | --- |
| SilverStar_FCCG | `6288994b593ab47fda0554a35deaec2c71a10a0b` | `f58b17e98e73fc77afb288689e496b6e6bcf5832`, `main` | `.gitignore` cleanup exclusions |
| SilverStar_GSHC | `8be9fd6a7d03be8a7edd96a78454b33701869ad0` | `78c72cab0c56288a591742c9f95e4e8624ada502`, `main` | `.gitignore` and `VALIDATION.md` cleanup record |
| SilverStar_FLP | `10c546d8cc7e6779842a5f06b94c7dc17445aa94` | `d3872a9a564c11467dad9e80753bb70e15634f98`, `main` | `.gitignore`, `docs/Workspace_Cleanup.md`, cleanup tool and tests |

The user's later instruction explicitly authorized final source commits and pushes with message `清理、合仓前最终记录`. All three were pushed to their existing remotes. After those commits, tracked source status was clean; untracked historical test output remained in the former workspaces. There were no ambiguous tracked deletions to restore from HEAD. The tracked cleanup documentation/tool/test changes were imported where applicable. Former repository `.gitignore` rules were reviewed but replaced by a monorepo root policy.

## Imported layout and exclusions

- FCCG source, plugins, tools and active tests live in `apps/FCCG/`; GSHC flat modules and active tests in `apps/GSHC/`; FLP source and active tests in `apps/FLP/`.
- Former README, TARGETS, CHANGELOG, VALIDATION and `docs/` material is organized under `docs/FCCG/`, `docs/GSHC/`, `docs/FLP/`. The three `VALIDATION.md` files remain historical records. Their old paths and test counts are not monorepo results.
- `contracts/navigation_v1.json` is the byte-identical canonical copy from the former repositories. The three old `docs/contracts` copies and the FLP ESKF package copy are absent here; FCCG test, GSHC documentation and FLP runtime use the root contract.
- Other same-named documents were compared. The FCCG/GSHC AIR Calibration contract copies differ, as do all three GUI style guides; they retain component-specific context and were not merged into a false shared authority in this first round.
- Only Git tracked files were considered. `.git`, three `.venv` trees, generated firmware, top-level build/dist/release, pytest basetemp/cache, PyInstaller work/dist, `.work`, untracked logs/decoder/zip/user input and full historical `tests/joint_rework_20260927` analysis trees were excluded. Selected small tracked FCCG/FLP `evidence_final` JSON remains; GSHC historical GUI screenshots and full old run logs were excluded. The formal old validation text remains readable as history.
- One mistakenly excluded FCCG Python source package named `build` was restored from the source repository (`__init__.py`, `runner.py`, `toolchain.py`). No other `src/` modules were excluded.

The largest imported file is the required STM32 CMSIS `stm32f407xx.h` vendor header, about 1.14 MiB. It is source input for the MCU plugin, not a test artifact. The only staged binary test data are two active FLP numerical golden NPZ fixtures (about 30 and 98 KiB, used by `test_actual_parameters.py`) and one tracked FCCG final bridge `.ssdecoder` evidence file (about 130 KiB, identified in its evidence manifest). No imported test fixture exceeds 1 MiB; no large raw flight log, bulk decoder/NPZ analysis output or copied environment was imported. The reviewed source/docs/test tree is about 23.6 MiB excluding ignored work.

## Release, entry points and compatibility

Root `VERSION` is `0.1.0`. FCCG, GSHC and FLP runtime authorities read it. The root `pyproject.toml` obtains packaging version from the same file and declares the dependency union from the three former projects. Builtin SilverStar plugin release fields and the versioned core ID/directory use 0.1.0 / `silverstar.core.0_1_0`. FreeRTOS remains 11.3.0. Generated product release metadata and core dependency IDs were updated; `SYSTEM_PROFILE_ID` remains `0x0000000C` as an independent profile identity. AIR M0, SSLOG 0.0, decoder/project-semantics 1.2, navigation quality revision 3, board SS0.5 and MCU STM32F407VET6 are unchanged.

`FCCG.py`, `GSHC.py` and `FLP.py` are thin root launchers. A single ignored `.venv/` was created; a root setup script creates and installs a normal environment. This machine's offline validation environment was made with `--system-site-packages` because an isolated no-index install could not find setuptools; it still runs all three applications with one interpreter and one installed Qt. `SilverStar.code-workspace` selects that interpreter. No EXE was built.

The retained GSHC packaging helper was redirected to the root `.venv` and ignored `.work/package/GSHC` output so a later explicit package run does not install into global Python. Packaging metadata is checked against `VERSION`; package production remains unvalidated in this round. Git attributes preserve imported vendor/source whitespace and Markdown hard breaks during this baseline; root migration code and integration tests still receive normal whitespace checks.

## Verification and next round

The three root launchers stayed alive in bounded Qt offscreen smoke, without hardware. `FCCG.py --version` and `FLP.py --version` returned 0.1.0, and GSHC imported with APP_VERSION 0.1.0. FCCG localization: **5 passed**; FCCG GUI smoke: **13 passed**; FCCG documentation: **6 passed**; FCCG release and generated-project identity: **2 passed**; GSHC AIR protocol: **14 passed**; GSHC documentation: **31 passed**; GSHC GUI version: **1 passed**; FLP version and decoder profiles: **39 passed**; monorepo integration: **5 passed**. Compileall passed. Ruff passed for new migration code and the existing application fatal-rule profile. Staged `git diff --check` passed.

The direct `test_navigation_v1.py` collection exposes an import-order cycle in FCCG; the identical direct import also fails against the untouched old source, while normal application startup succeeds. It is recorded as a pre-existing focused-test limitation, not a new behavior change. Heavy historical hardware/firmware/field gates were not run. Before the new baseline commit, all three former repositories had clean tracked status at the final-record HEADs above. The new staged tree contains no nested `.git`/`.venv` or accidental large generated file.

The monorepo integration suite covers release identity, canonical contract, root GUI startup, absence of old absolute Python paths, current documentation links, ignored `.work`, and no nested `.git`/`.venv`.

Future work: hardware bench verification, firmware targets and broader shared-code refactoring remain separate tasks. No Ground Station firmware, new sensor, persistent storage, alignment, calibration, estimator behavior or Simulator work was implemented in this migration.

# SilverStar version management

`VERSION` is the only manually maintained product number. It currently remains
`0.1.3`. `versions.json` is the central registry: it references that file for the
suite/desktop applications and references independently owned protocol, schema
and plugin authorities. It does not copy their numbers into a second manual
source. `product.maturity=development` describes development status separately
from the version number; it is not hardware acceptance.

Run from the repository root:

```powershell
python -B tools/silverstar_version.py
```

The report resolves the current identities and component manifests. Missing or
ambiguous sources fail instead of returning invented defaults. The optional
`--root`/`--source-root` arguments support an isolated review overlay; they only
select sources for the inventory and never authorize decoding or execution.
It also lists the declared identities in shared JSON contracts and each SSLOG
record entry. Per-entry content digests are informational: they exclude
catalog-wide defaults and project semantics and do not authorize decoding.

## Product, package and compatibility fields

The shared resolver implements a bounded SemVer product identity. The supported
packaging prereleases are `alpha.N`, `beta.N`, `rc.N` and `dev.N`; numeric
identifiers have no leading zeros. Other SemVer labels are rejected at the
packaging boundary until a conversion policy is defined. Build metadata remains
in the full product string. Python package local metadata supports only dotted
alphanumeric identifiers: letters become lowercase and all-numeric identifiers
lose leading zeros as required by PEP 440 (e.g. `+Build.007` becomes `+build.7`).
The full SemVer product identity remains `+Build.007` in display, firmware and
provenance. Any metadata identifier containing a hyphen, including valid SemVer
`+ci-`, `+-ci`, `+-` or `+ci-build`, is explicitly rejected by the shared product
loader. It is not split, stripped or silently rewritten to another identifier.
Unsupported product identities therefore fail before application/firmware and
packaging consumers diverge. SemVer build metadata does not affect precedence;
PEP 440 local ordering is a separate package convention and is not used for
product, hardware or algorithm-compatibility decisions.

This follows [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html) and the distinct
[Python packaging version scheme](https://packaging.python.org/en/latest/specifications/version-specifiers/).

| Consumer | Derived identity |
|---|---|
| SCG, GSHC, FLP display | Full product string |
| Python distribution metadata | PEP 440 conversion, e.g. `0.2.0-alpha.1` → `0.2.0a1` |
| Windows fixed resource | `(major, minor, patch, 0)`, each field within 16-bit range; full string retained in FileVersion/ProductVersion |
| New SCG project and target name | Product number and a filename-safe suffix |
| Existing firmware request | Original explicit request retained; a difference from the generator product is reported |
| Firmware numeric wire fields | Three existing u8 fields; out-of-range values fail |
| Firmware text identity | Full requested version and development/test status; bounded text, never silent truncation |
| SSLOG short build tag | Existing `SILV0103` style where representable; otherwise a deterministic eight-character tag. It is a short correlation field, not complete provenance |

Legacy two-part firmware requests retain their original spelling in the project
and declaration, with patch zero in numeric compatibility fields. The product
`VERSION` itself always requires three-part SemVer. Explicit test builds retain
their existing three-part request requirement.

Ordinary generation now emits the version macros before the generated includes,
as does the explicit test-build path. External overrides of those generated
version macros fail compilation. The existing test build keeps its explicit
build number, tag and source-commit declaration; those fields do not establish
an exact dirty-source snapshot.

The generated `.fccg/version_identity.json` is a version declaration containing
the source/registry digests, requested identity and numeric projections. It is
managed metadata and is not edited by users. It does not claim that every user
source file matches the generator or that a particular ELF has been built.
Source/artifact evidence remains in the owning build audit and diagnostic
binding. Ordinary Make remains independent of the Python generator.
When the product maturity is explicitly set to `release`, generation rejects a
different firmware request or a test identity instead of silently rebranding an
old project. Development reproduction may retain the explicit old identity.

Ground metadata consumes the same resolver without introducing a new GSP packet
or changing AIR. Android's development preview and DeviceService's mock prototype
remain independently identified and registered; neither is silently converted
into a desktop release or hardware-qualified product. Their future joint release
policy must be decided before adding them to a common distribution.

The shared Windows portable configuration is the suite distribution path.
Standalone GSHC/FLP specs now include the same version resources; standalone
wheel installation is not claimed by the source-relative application layout.
Historical archives and installed user projects are not renamed or rewritten.

## Independent compatibility identities

The registry lists the owning sources rather than forcing all numbers to 0.1.3:

- AIR profile, GSP framing, maintenance/LOGFILE/DIAG and installation contracts;
- SSLOG container, Record Catalog, each record type/version and Descriptor;
- decoder package and project semantics, SCG project formats and FLP projects;
- algorithm manifests, parameter schemas, model revisions and operation journals.

An application release number is not a substitute for an exact format, declared
capability, compatible algorithm contract or recorded parameter set. The existing
minimum-FLP number is a declared floor; actual feature support still requires
the corresponding record and algorithm contracts.

## User modifications and hash boundaries

The current implementation already distinguishes several hash purposes. This
version-management change does not relax decoder, replay, copy-integrity or SWD
checks.

| Purpose | Current implementation and required boundary |
|---|---|
| Project generation state | `project/generation_state.py` hashes normalized project data; it is not a whole-repository source hash |
| User-owned code | `generator/assembler.py` preserves existing component source. Original expected digests remain provenance; edited files must not be relabelled as original |
| File/package integrity | Archive members, exported files and copied logs retain their checksum/size checks; these detect corruption independently of protocol compatibility |
| Telemetry compatibility | GSHC's AIR capability/profile and frame-layout checks remain authoritative; a repository source hash is not an AIR wire field |
| Log compatibility | Generation-profile SHA-256 is derived from Catalog/Semantics and container identity. `LogOpenCoordinator` still requires exact Descriptor matching |
| Unknown records | Within an accepted exact package, unknown CRC-valid type/version payloads are retained as partial raw records. A missing/wrong decoder does not permit guessed field decoding |
| Recorded recomputation | Actual algorithm/input/calibration/journal evidence and current fidelity gates remain required; user code changes do not acquire numerical fidelity through a matching product number |
| SWD addresses | `.ssdiag` remains bound to an actual successful ELF hash. Modified source must be rebuilt and rebound; addresses are never guessed |

Editing business logic while preserving the generated wire/log contracts should
not be treated as a universal loss of telemetry or recorded-data display.
Maintaining the matching log/decoder is still necessary. Changing a record's
layout or meaning requires an updated owning contract and matching decoder.

Some regeneration checks intentionally protect stronger timing/model claims
(`FusionTimingIdentity_Validate`, KF6 and ESKF identity checks). They remain
unchanged. A broader split into per-module layout, capability and algorithm
content identities needs its own versioned contract and migration review; adding
block hashes alone is not permission to skip the existing exact checks.

The isolated version candidate also exercises this boundary: the ordinary ARM
build and artifact checks can succeed while `stack-report` rejects the changed
`Generated/Inc/project_flight_config.h` as an unreviewed callback compilation
input. That refusal is retained. A version-only source change does not by itself
establish an unchanged callback closure or a safe stack bound. Requalification
of that proof is a separate review; the version change does not add hash
exceptions to make it pass.

For that separate migration, retain both original and current source identities,
report `modified`, and define each consumer's compatibility decision explicitly.
Tests must demonstrate that a business-code edit preserves ordinary log/telemetry
handling, a changed layout cannot be decoded incorrectly, unknown records retain
raw bytes, Recorded fidelity does not improve without evidence, and a mismatched
ELF remains rejected. No such gate refactor is included here.

## Validation and release

Changing `VERSION` must propagate through the resolver, application display,
package resources, new firmware configuration and the version declaration.
Prerelease/build strings, old explicit projects, external macro conflicts and
missing identities must be tested. Existing decoder, source-preservation and
ELF-binding tests remain applicable.

Before publishing, review the exact source snapshot, generated outputs, actual
compiler/linker results, diagnostic binding and artifact hashes. Development
status, source integrity, contract compatibility and hardware/flight acceptance
are independent facts. No version update creates a release tag or authorizes
hardware operations.

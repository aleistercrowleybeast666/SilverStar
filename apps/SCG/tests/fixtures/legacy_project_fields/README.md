# Frozen legacy field-migration fixtures

These are **synthetic compatibility fixtures**, not captured user projects or
hardware evidence. They exercise the v2鈥搗7 field migrations and the modern
explicit-device-identity admission boundary separately.

`build_fixtures.py` starts from the checked-in, fixed format-14
`radio_handshake.ssproject`, never from the evolving current ReferenceProject
factory. It projects the legacy root and hardware fields specified by
`_ProjectV0_Migrate` through `_ProjectV8_Migrate` in the original monorepo model
at `2763bb8f` (2026-09-28), then builds the individual old-version inputs.
The full source commit and source hashes are recorded in `provenance.json`.

The v3鈥搗7 fixtures retain explicit `interface` and `profile` keys from the
checked-in compatibility input, with their actual empty/unconfigured values;
no physical interface or profile is guessed. These are the supported explicit
identity shape, not a claim that every historical pre-release serializer wrote
those keys. The v2 fixture deliberately has its true positional plugin list and
must still be rejected because migration cannot invent those identities.

No mission_process, mission_functions, sensor_installation, native_usb or other
later-generation fields are carried into these files. Tests also inject a
current mission_process into each legacy version and require the existing
format-22 rejection. The explicit identity and future-field admission boundaries remain strict.
The tests cover repaired legacy link/Ground initialization and frozen old wire
identities; these files do not select SS-TM-S or a Ground automatically.

Format 12 additionally retains the fixed input algorithm parameters, while
removing the later AirLink/Ground/alignment fields. Older v2–v7 inputs omit the
v12 parameter field and generated glue. Retired alignment IDs are explicit
fixture inputs so the existing v13 transformation is exercised, not bypassed.

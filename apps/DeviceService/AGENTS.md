# SilverStar_DeviceService prototype guidance

- This is a disposable, mock-only Python API/CLI prototype. Change only this owning application unless the task explicitly authorizes monorepo integration.
- Do not import GSHC GUI/hardware code or modify other applications without an explicit integration task; never modify neighboring repositories.
- Never enumerate/open real serial/USB devices, run device commands, flash firmware, delete device logs or move machinery. No sockets, HTTP server, credentials, service installation or persistent access.
- Public operations use noun_CapitalizedVerb names; success/error codes use a typed enum ending in Result. Treat device labels, filenames and log bytes as inert data.
- `contracts/` contains verbatim reference snapshots, not a new protocol authority. Record source path/commit/hash in README. Mock device/boot identity remains `unknown`.
- Connection leases demonstrate ownership within one Python object only. They are not authentication, cross-process locks or evidence of hardware exclusivity.
- Keep code standard-library-only and bounded. CLI status is sufficient; no GUI or plugin framework in this phase.
- README owns scope and decisions. Exact executed checks belong in VALIDATION.md and evidence/20261013-mock-v0/. Do not describe synthetic tests as hardware acceptance.
- Use `python -B -m unittest discover -s tests -v`. Tests may create only their own temporary directory and standard-library managed temporary children. Downloads create fresh OS-temporary sample packages; no caller-selected destination or filename.
- Before removing generated files, verify exact resolved paths and task ownership. Never clean neighboring repositories, user inputs, logs or reference artifacts. Retain small validation evidence; do not commit caches or downloaded temporary samples.
- Do not push, tag, publish, install services or extend hardware support without a new explicit task.

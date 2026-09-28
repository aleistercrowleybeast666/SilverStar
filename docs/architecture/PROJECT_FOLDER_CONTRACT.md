# SilverStar project folder contract (0.1.0)

FCCG creates a user-selected project root containing `SilverStar.ssproject` and `Log/`. Firmware generation is optional for each target; saving the project does not prepare hardware or generate firmware.

```text
<ProjectRoot>/
├─ SilverStar.ssproject
├─ <ProjectName>.ssdecoder       # only after a valid Flight logging generation
├─ Flight_Controller/           # after Flight generation
│  ├─ Flight_Controller.code-workspace
│  ├─ Makefile
│  └─ build/
├─ Ground_Station/              # after Ground generation
│  ├─ Ground_Station.code-workspace
│  ├─ Makefile
│  └─ build/
└─ Log/                         # user copies TF/SD logs here
```

The root `.ssdecoder` is the canonical file FLP discovers. Flight generation atomically updates it from the generated logging contract and removes it when logging no longer produces a decoder. `SilverStar.ssproject` refers to that root file. A target's build and workspace files stay inside its own directory; no target build writes to the project root. FCCG does not copy logs from removable media.

FLP opens the project root, reads only root `*.ssdecoder` and log files in `Log/` and one level of log subdirectories, then asks the user to select one exact-matching log/decoder pair. It never searches generated firmware, `Drivers/`, or vendor trees in project-root mode. Exports default to `Log/<LogStem>_Export/`; standalone log and decoder opening remains supported.

Recommended flow: create root in FCCG → configure AIR Link and each target → generate Flight and/or Ground → build each independently → copy logs into `Log/` → open the project root in FLP.

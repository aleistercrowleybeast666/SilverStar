"""Export a native SCG project's current declarative flight configuration."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def MissionExport_Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replace", action="store_true", help="Replace a valid profile and retain .bak")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "apps/SCG/src"))
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfile_Write
    try:
        service = FccgService(ROOT / "apps/SCG")
        model = service.Project_Open(args.project)
        profile = MissionProfile_Build(model, service.catalog)
        MissionProfile_Write(args.output, profile, replace_existing=args.replace)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    print(str(args.output) + " sha256=" + profile["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(MissionExport_Main())

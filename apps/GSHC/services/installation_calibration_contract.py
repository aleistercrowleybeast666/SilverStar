"""Read the shared contract; no device capability can be inferred from it."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys


class InstallationContractUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class InstallationContract:
    raw: bytes
    sha256: str

    def Read(self):
        return json.loads(self.raw)


def InstallationContract_Load(path=None):
    if path is None:
        path = ((Path(sys._MEIPASS)/"contracts") if getattr(sys,"frozen",False)
                else Path(__file__).resolve().parents[3]/"contracts")/"installation_calibration_v1.json"
    try:
        raw = Path(path).read_bytes()
        if len(raw)>65536: raise ValueError("contract size")
        data = json.loads(raw)
        if (data["contract"]!="silverstar.installation-calibration" or data["contract_version"]!=1
                or data["versions"]["maintenance"]!="0.1"
                or data["limits"]["request_bytes"]!=191 or data["limits"]["response_bytes"]!=511
                or data["sample"]["payload_bytes"]!=154
                or any(data["safety"][key] is not False for key in ("apply_supported","save_supported","upload_supported"))):
            raise ValueError("incompatible installation contract")
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise InstallationContractUnavailable("Installation contract unavailable or incompatible") from exc
    return InstallationContract(raw,hashlib.sha256(raw).hexdigest())

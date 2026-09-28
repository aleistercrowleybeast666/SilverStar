"""Run separately paired logs; outputs/cache stay under the selected destination."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.algorithms.kf6.field_analysis import FieldSweep_Run
from silverstar_flp.plugins.registry import builtin_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair", nargs=2, action="append", required=True, metavar=("LOG", "DECODER")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-latency", action="store_true")
    parser.add_argument("--stationary-us", nargs=2, type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    opener = LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(args.output / "cache")
    )
    summary = []
    for index, (log, decoder) in enumerate(args.pair):
        paths = [Path(log), Path(decoder)]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        opened = opener.Open(LogOpenRequest(log_path=paths[0], decoder_package_path=paths[1]))
        report = FieldSweep_Run(
            opened.dataset,
            include_latency=not args.no_latency,
            stationary_interval_us=tuple(args.stationary_us) if args.stationary_us else None,
        )
        after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        if before != after:
            raise RuntimeError("input_hash_changed")
        report["input_sha256"] = dict(zip(("log", "decoder"), before, strict=True))
        (args.output / f"analysis_{index + 1}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        summary.append(
            {"log": str(paths[0]), "best_shift_ms": report.get("latency", {}).get("best_shift_ms")}
        )
    (args.output / "comparison.json").write_text(
        json.dumps(
            {"logs": summary, "firmware_compensation_authorized": False},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "validation" / "logs"
EVENT_LOG = LOG_DIR / "urban_core_monitor.jsonl"
STATUS_PATH = LOG_DIR / "urban_core_monitor_status.json"
PID_PATH = LOG_DIR / "urban_core_monitor.pid"
METRICS = ROOT / "validation/advanced/10_urban_gis_core/results/metrics.json"


def run(command: list[str], environment: dict[str, str]) -> dict:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1_200,
        check=False,
    )
    output = completed.stdout or ""
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_s": time.monotonic() - started,
        "output_tail": output[-4_000:],
    }


def write_status(payload: dict) -> None:
    STATUS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--until", required=True, help="ISO timestamp with UTC offset")
    parser.add_argument("--interval-s", type=int, default=1_800)
    args = parser.parse_args()
    end = datetime.fromisoformat(args.until)
    if end.tzinfo is None:
        raise SystemExit("--until must include a UTC offset")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{os.getpid()}\n", encoding="ascii")
    environment = os.environ.copy()
    environment["RAINFALL_FORCE_CPU"] = "1"
    environment["MPLCONFIGDIR"] = "/tmp/rainfall-monitor-mpl"
    commands = [
        ["uv", "run", "--extra", "dev", "--extra", "gis", "pytest", "-s"],
        [
            "uv", "run", "--extra", "dev", "--extra", "gis", "python",
            "validation/advanced/10_urban_gis_core/code/run_experiment.py",
        ],
        ["uv", "run", "python", "validation/build_validation_report.py"],
    ]
    cycles = 0
    failures = 0
    final_state = "completed"
    try:
        while datetime.now().astimezone() < end:
            cycle_started = datetime.now().astimezone()
            results = [run(command, environment) for command in commands]
            metrics = {}
            try:
                metrics = json.loads(METRICS.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            passed = all(item["returncode"] == 0 for item in results) and bool(
                metrics.get("all_gates_pass")
            )
            failures += int(not passed)
            cycles += 1
            event = {
                "cycle": cycles,
                "started_at": cycle_started.isoformat(),
                "finished_at": datetime.now().astimezone().isoformat(),
                "passed": passed,
                "all_gates_pass": metrics.get("all_gates_pass"),
                "relative_mass_error": metrics.get("with_buildings", {}).get(
                    "relative_mass_error"
                ),
                "commands": results,
            }
            with EVENT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            write_status(
                {
                    "state": "running",
                    "pid": os.getpid(),
                    "until": end.isoformat(),
                    "interval_s": args.interval_s,
                    "cycles": cycles,
                    "failures": failures,
                    "last_cycle": event,
                }
            )
            remaining = (end - datetime.now().astimezone()).total_seconds()
            wait_s = min(float(args.interval_s), max(0.0, remaining))
            while wait_s > 0:
                chunk = min(wait_s, 60.0)
                time.sleep(chunk)
                wait_s -= chunk
    except Exception as exc:
        final_state = "failed"
        failures += 1
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": datetime.now().astimezone().isoformat(),
                        "passed": False,
                        "monitor_error": repr(exc),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    finally:
        write_status(
            {
                "state": final_state,
                "pid": os.getpid(),
                "finished_at": datetime.now().astimezone().isoformat(),
                "until": end.isoformat(),
                "interval_s": args.interval_s,
                "cycles": cycles,
                "failures": failures,
            }
        )


if __name__ == "__main__":
    main()

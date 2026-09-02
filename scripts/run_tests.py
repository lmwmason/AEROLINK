#!/usr/bin/env python3
"""Offline test orchestrator with deterministic JSON and log artifacts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

FAST = [
    ("fc-native", ["sh", "src/test/run_aerolink_native.sh"], "flight-controller", 60),
    ("pi-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], "raspberry-pi", 60),
    ("server-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], "server", 60),
    ("fake-fleet", [sys.executable, "tools/run_simulation.py"], "server", 60),
    ("protocol-verification", [sys.executable, "scripts/protocol_coverage.py"], ".", 60),
    ("state-exploration", [sys.executable, "scripts/state_explorer.py"], ".", 60),
    ("security-scan", [sys.executable, "scripts/security_scan.py"], ".", 60),
    ("diagnostics-bundle", [sys.executable, "scripts/diagnostics_bundle.py"], ".", 60),
    ("repo-validation", [sys.executable, "scripts/validate_repo.py"], ".", 60),
]

BUILDS = [
    ("sitl-feature-off", ["make", "TARGET=SITL", "AUTOHYDRATE_SUBMODULES=", "BETAFLIGHT_CONFIG=src/config"], "flight-controller", 900),
    ("sitl-feature-on", ["make", "TARGET=SITL", "AEROLINK_SITL=1", "AUTOHYDRATE_SUBMODULES=", "BETAFLIGHT_CONFIG=src/config"], "flight-controller", 900),
]


def sitl(nodes: int):
    return (f"real-sitl-{nodes}", [sys.executable, "server/tools/run_real_sitl.py", "--nodes", str(nodes)], ".", 300 if nodes < 15 else 600)


def run_case(name, command, cwd, timeout, artifacts, env):
    started = time.monotonic()
    log_path = artifacts / f"{name}.log"
    try:
        result = subprocess.run(command, cwd=ROOT / cwd, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        output, code, status = result.stdout, result.returncode, "passed" if result.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or "") + f"\nTIMEOUT after {timeout}s\n"
        code, status = 124, "timed_out"
    log_path.write_text(output)
    try:reported_log=str(log_path.relative_to(ROOT))
    except ValueError:reported_log=str(log_path)
    return {"name": name, "status": status, "exit_code": code, "duration_seconds": round(time.monotonic() - started, 6),
            "command": command, "cwd": cwd, "log": reported_log}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=("fast", "all", "15-node"))
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    artifacts = args.artifacts.resolve();artifacts.mkdir(parents=True, exist_ok=True)
    cases = list(FAST)
    if args.profile == "all":cases += BUILDS + [sitl(1), sitl(3)]
    elif args.profile == "15-node":cases = BUILDS[-1:] + [sitl(15), ("reliability-soak", [sys.executable, "scripts/reliability_soak.py"], ".", 120)]
    env = {**os.environ, "PYTHONPATH": f"{ROOT/'server/src'}:{ROOT/'raspberry-pi/src'}", "PYTHONDONTWRITEBYTECODE": "1", "AEROLINK_ARTIFACTS": str(artifacts)}
    results = []
    for case in cases:
        result = run_case(*case, artifacts, env);results.append(result)
        print(f"{result['status'].upper():9} {result['name']:<24} {result['duration_seconds']:>8.3f}s")
        if result["status"] != "passed":break
    report = {"schema_version": 1, "profile": args.profile, "software_only": True,
              "control_path_connected": False, "passed": len(results) == len(cases) and all(r["status"] == "passed" for r in results), "results": results}
    (artifacts / "test-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":raise SystemExit(main())

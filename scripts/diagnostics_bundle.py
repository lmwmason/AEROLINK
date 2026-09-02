#!/usr/bin/env python3
"""Offline diagnostics bundle: config/version summary, an empty-server
metrics snapshot, the most recent local test report (if any), and the
most recent SBOM/dependency-scan evidence (if any). Redacted; no secrets.
"""
from __future__ import annotations
import json,os,platform,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.core import FleetServer
from aerolink_server.security import redact

def git(*args):
    return subprocess.run(["git",*args],cwd=ROOT,text=True,capture_output=True,check=False).stdout.strip()

def main():
    artifacts=Path(os.environ.get("AEROLINK_ARTIFACTS",ROOT/"artifacts"))
    out=Path(sys.argv[1]) if len(sys.argv)>1 else artifacts/"diagnostics"
    out.mkdir(parents=True,exist_ok=True)
    fleet=FleetServer()
    summary={
        "schema_version":1,"offline":True,"software_only":True,"control_path_connected":False,
        "generated_by":"scripts/diagnostics_bundle.py",
        "versions":{"python":platform.python_version(),"platform":platform.platform()},
        "git":{"commit":git("rev-parse","HEAD"),"branch":git("rev-parse","--abbrev-ref","HEAD"),"dirty":bool(git("status","--porcelain"))},
        "feature_gates":{"AEROLINK_SITL_default":"unset (feature-off by default)","runtime_gate":"--aerolink-vehicle required"},
        "reconciliation_state":fleet.reconciliation_state,
        "metrics_schema_example":fleet.metrics.snapshot(),
    }
    report=artifacts/"test-report.json"
    if report.exists():summary["last_test_report"]=json.loads(report.read_text())
    evidence=ROOT/"evidence"
    for name in ("sbom.spdx.json","dependency-scan.json"):
        f=evidence/name
        if f.exists():summary[name.split(".")[0].replace("-","_")]=json.loads(f.read_text())
    destination=out/"diagnostics.json";destination.write_text(json.dumps(redact(summary),indent=2,sort_keys=True,default=str)+"\n")
    print(f"diagnostics bundle written to {destination}")

if __name__=="__main__":main()

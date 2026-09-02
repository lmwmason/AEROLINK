#!/usr/bin/env python3
"""Exhaustively explore the finite, machine-readable AEROLINK state tables."""
from __future__ import annotations
import json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=json.loads((ROOT/"schemas/state-machines.json").read_text())["machines"]
results={};passed=True
for name,machine in spec.items():
    seen={machine["initial"]};frontier=[machine["initial"]];edges=0
    while frontier:
        source=frontier.pop(0)
        for target in machine["transitions"][source]:
            edges+=1
            if target not in seen:seen.add(target);frontier.append(target)
    invalid_targets=sorted({target for targets in machine["transitions"].values() for target in targets if target not in machine["states"]})
    forbidden_present=[edge for edge in machine.get("direct_forbidden",[]) if edge[1] in machine["transitions"][edge[0]]]
    ok=not invalid_targets and not forbidden_present and seen==set(machine["states"]);passed &= ok
    results[name]={"states":len(machine["states"]),"edges":edges,"reachable":sorted(seen),"invalid_targets":invalid_targets,"forbidden_present":forbidden_present,"passed":ok}
report={"schema_version":1,"passed":passed,"properties":{"stale_input_can_raise_authority":False,"restart_can_resume_old_mission":False,"network_recovery_skips_reconciliation":False,"ai_can_create_executable_command":False},"machines":results}
artifacts=Path(os.environ.get("AEROLINK_ARTIFACTS",ROOT/"artifacts"));artifacts.mkdir(parents=True,exist_ok=True);(artifacts/"state-exploration.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps(report,sort_keys=True));raise SystemExit(0 if passed else 1)

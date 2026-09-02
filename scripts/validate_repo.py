#!/usr/bin/env python3
"""Dependency-free documentation, schema, syntax, and safety-boundary checks."""
from __future__ import annotations
import ast,json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
errors=[]
generated=subprocess.run(["python3",str(ROOT/"scripts/generate_protocol.py"),"--check"],capture_output=True,text=True)
if generated.returncode:errors.append(generated.stdout+generated.stderr)
for path in list((ROOT/"docs").glob("*.md"))+[ROOT/"README.md"]:
    text=path.read_text()
    for target in re.findall(r"\[[^]]+\]\(([^)]+)\)",text):
        if "://" in target or target.startswith("#"):continue
        clean=target.split("#",1)[0]
        if clean and not (path.parent/clean).resolve().exists():errors.append(f"{path.relative_to(ROOT)}: broken link {target}")
for path in ROOT.glob("**/*.json"):
    relative=path.relative_to(ROOT)
    if relative.parts[0]=="flight-controller" or relative.parts[0]=="embedded-emagcontrol" or any(part in {"obj","artifacts",".git",".vscode",".pio"} for part in relative.parts):continue
    try:json.loads(path.read_text())
    except Exception as exc:errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
for base in (ROOT/"raspberry-pi",ROOT/"server",ROOT/"scripts"):
    for path in base.glob("**/*.py"):
        try:ast.parse(path.read_text(),filename=str(path))
        except SyntaxError as exc:errors.append(str(exc))
for path in (ROOT/"scripts").glob("*.sh"):
    result=subprocess.run(["bash","-n",str(path)],capture_output=True,text=True)
    if result.returncode:errors.append(result.stderr.strip())
transport=(ROOT/"flight-controller/src/main/io/aerolink_sitl.c").read_text()
for forbidden in ("flight/pid.h","flight/mixer.h","drivers/motor.h","fc/rc_controls.h","armingFlags","motorWrite","mixTable"):
    if forbidden in transport:errors.append(f"actuator boundary violation: {forbidden}")
if errors:
    print("\n".join(errors));raise SystemExit(1)
print("repository validation: OK")

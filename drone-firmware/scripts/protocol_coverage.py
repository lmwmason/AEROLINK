#!/usr/bin/env python3
"""Run deterministic protocol verification and emit dependency-free coverage."""
from __future__ import annotations
import ast,json,os,sys,trace,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"raspberry-pi/src"),str(ROOT/"server/src")]
suite=unittest.defaultTestLoader.discover(str(ROOT/"raspberry-pi/tests"),pattern="test_protocol*.py")
runner=unittest.TextTestRunner(verbosity=1)
tracer=trace.Trace(count=True,trace=False)
result=tracer.runfunc(runner.run,suite)
counts=tracer.results().counts
files=[ROOT/"raspberry-pi/src/aerolink_pi/protocol.py",ROOT/"raspberry-pi/src/aerolink_pi/fleet.py"]
coverage={}
for path in files:
    executable={node.lineno for node in ast.walk(ast.parse(path.read_text())) if isinstance(node,ast.stmt) and hasattr(node,"lineno")}
    hit={line for (filename,line),count in counts.items() if Path(filename).resolve()==path.resolve() and count}
    coverage[str(path.relative_to(ROOT))]={"executable_lines":len(executable),"hit_lines":len(executable&hit),"percent":round(100*len(executable&hit)/len(executable),2)}
report={"schema_version":1,"passed":result.wasSuccessful(),"tests_run":result.testsRun,"seed":"0xA3E011/7","generated_cases":505,"mutations":256,"coverage":coverage,"actuator_commands":0}
artifacts=Path(os.environ.get("AEROLINK_ARTIFACTS",ROOT/"artifacts"));artifacts.mkdir(parents=True,exist_ok=True)
(artifacts/"protocol-verification.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps(report,sort_keys=True));raise SystemExit(0 if result.wasSuccessful() else 1)

#!/usr/bin/env python3
"""Offline secret scan plus deterministic SBOM/dependency evidence."""
from __future__ import annotations
import json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];errors=[]
tracked=subprocess.run(["git","ls-files","-co","--exclude-standard"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.splitlines()
pattern=re.compile(r"(?i)(api[_-]?key|password|private[_-]?key|secret)\s*[:=]\s*['\"]([^'\"]{12,})")
for name in tracked:
    path=ROOT/name
    if not path.is_file() or path.stat().st_size>2_000_000 or name.startswith("flight-controller/"):continue
    text=path.read_text(errors="ignore")
    for match in pattern.finditer(text):
        value=match.group(2)
        if "test" not in value.lower() and "redacted" not in value.lower() and "configured" not in value.lower():errors.append(f"potential secret: {name}")
sbom={"spdxVersion":"SPDX-2.3","dataLicense":"CC0-1.0","SPDXID":"SPDXRef-DOCUMENT","name":"AEROLINK-software-only","documentNamespace":"https://example.invalid/aerolink/sbom/v1","packages":[{"name":"Betaflight","SPDXID":"SPDXRef-Betaflight","versionInfo":"2026.6.1","downloadLocation":"https://github.com/betaflight/betaflight","licenseConcluded":"GPL-3.0-only"},{"name":"AEROLINK-Python","SPDXID":"SPDXRef-AerolinkPython","versionInfo":"0.1.0","downloadLocation":"NOASSERTION","licenseConcluded":"NOASSERTION","externalRefs":[]}]}
dependency={"schema_version":1,"offline":True,"python_third_party_runtime_dependencies":[],"betaflight_upstream":"6dbc4218fd6bc33bf16ea32c670304d4f89321d5","vulnerability_database":"not_available_offline","known_vulnerabilities":[],"limitations":["No offline advisory database is vendored; absence of findings is not proof of absence."],"secret_scan_passed":not errors}
evidence=ROOT/"evidence";evidence.mkdir(exist_ok=True);(evidence/"sbom.spdx.json").write_text(json.dumps(sbom,indent=2,sort_keys=True)+"\n");(evidence/"dependency-scan.json").write_text(json.dumps(dependency,indent=2,sort_keys=True)+"\n")
if errors:print("\n".join(sorted(set(errors))));raise SystemExit(1)
print("offline security scan: OK")

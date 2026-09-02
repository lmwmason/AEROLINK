#!/usr/bin/env python3
"""Generate local, offline, test-only per-node HMAC keys for development.

Writes dev-credentials/nodes.json (git-ignored — never commit this file).
Operator sessions are not a stored credential in this system: they are
created in-process by calling SecurityContext.create_operator_session(role)
at server startup (see docs/api-examples.md), so there is nothing to
"generate" for them beyond picking a role.
"""
from __future__ import annotations
import json,secrets,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    count=int(sys.argv[1]) if len(sys.argv)>1 else 15
    out=ROOT/"dev-credentials";out.mkdir(exist_ok=True)
    destination=out/"nodes.json"
    if destination.exists() and "--force" not in sys.argv:
        print(f"{destination} already exists; pass --force to regenerate (this invalidates any running dev server's expectations)");return 1
    keys={str(i):secrets.token_hex(32) for i in range(1,count+1)}
    destination.write_text(json.dumps({"warning":"TEST-ONLY. Never commit. Never reuse for a real deployment.","node_keys_hex":keys},indent=2,sort_keys=True)+"\n")
    destination.chmod(0o600)
    print(f"wrote {count} test-only node keys to {destination} (mode 0600)")
    return 0

if __name__=="__main__":raise SystemExit(main())

# Release checklist

This is a pre-1.0, software-only research prototype (see
[`docs/versioning-policy.md`](versioning-policy.md)). "Release" here
means tagging a commit as a checkpoint others can build against — it
never means a physical/flight release; that path is explicitly out of
scope for any automated process (`AGENT.md`'s mandatory safety rules).

1. **Clean tree, on `main`, nothing uncommitted.**
   `git status --porcelain` is empty.
2. **Every test suite passes locally.**
   ```sh
   scripts/test-all.sh
   scripts/test-15-node.sh   # accept one retry for the known flaky readiness probe — docs/scale-test-report.md
   ```
3. **No secrets, SBOM/dependency evidence is current.**
   `python3 scripts/security_scan.py` passes; review the generated
   `evidence/sbom.spdx.json` and `evidence/dependency-scan.json` if
   dependencies changed (there should be none — see
   `docs/coding-standards.md`).
4. **Generated code matches its schema.**
   `python3 scripts/generate_protocol.py --check` passes (also part of
   `scripts/validate_repo.py`, which the fast profile already runs).
5. **Documentation is consistent.**
   `python3 scripts/validate_repo.py` passes (link/JSON/syntax/actuator-
   boundary checks); skim
   [`docs/software-verification-report.md`](software-verification-report.md)
   and update any table whose numbers materially changed.
6. **CHANGELOG.md has an entry** for what changed since the last tag,
   following [`docs/versioning-policy.md`](versioning-policy.md).
7. **No actuator/flight-control path was added.**
   Re-read the diff since the last tag against `AGENT.md`'s hard
   boundary; `scripts/validate_repo.py`'s keyword scan of
   `aerolink_sitl.c` is a floor, not a substitute for reading the diff.
8. **Hardware-progression state is unchanged or explicitly, separately
   reviewed.** No automated process may advance past the software
   simulation gates (`PRD.md` §10, items 1-7) — see
   [`docs/limitations.md`](limitations.md).
9. **Tag and record the upstream Betaflight commit** the tag was built
   against (`flight-controller/UPSTREAM.md`) if it changed.

Only after all of the above: tag the commit
(`vMAJOR.MINOR.PATCH-software-only`, see the versioning policy) and push
the tag. Do not force-push over an existing tag.

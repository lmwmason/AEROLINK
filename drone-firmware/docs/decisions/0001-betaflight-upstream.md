# ADR 0001: Betaflight upstream baseline

- Status: accepted
- Recorded: 2026-09-02
- Repository: `https://github.com/betaflight/betaflight`
- Tag: `2026.6.1`
- Commit: `6dbc4218fd6bc33bf16ea32c670304d4f89321d5`

The newest stable, non-release-candidate tag visible in the official repository
at baseline time was selected. Source was shallow-cloned at the tag, its commit
and exact tag were verified, and `git archive` was used to import the tree. The
upstream `.git` directory is intentionally not nested in this monorepo.

No FC target is selected. A baseline SITL build is a later verification gate;
hardware builds and flashing remain blocked on target evidence.

The pinned `src/config` gitlink is
`749fff19942fd7b44fa8020a086e1b566054cae9`; its source is imported without
nested Git metadata.

# Working on ios-extra

- Read `NOTES.md` before starting. This is the experimental playground for
  `ios-sweet`, with its own Git history and GitHub remote.
- Make experiments in `/home/dipa/ios-extra`. Treat `/home/dipa/ios-sweet` as
  a read-only reference unless the user asks to integrate changes upstream.
- The imported baseline is upstream commit
  `347e19018e3e4c0117635e9e444f73659b2ece53`, patches 0001–0079.
  Preserve focused commits so working changes can be ported separately.
- Update `NOTES.md` after milestones and before stopping. Distinguish source
  inspection, build results and phone observations. Record exact commits,
  CI run IDs, boot images, logs and unfinished work.
- Commit completed changes. Use `gh` with `-R dipa-studio/ios-extra` for this
  repository's builds and logs. Local single-file cross-compiles can avoid
  unnecessary CI runs. Do not edit the upstream research tree to check an
  experiment: stage a separate build tree here or in external scratch space.
- Keep the repository private until the user requests publication. The XNU
  workflow skips builds while private; public visibility enables its build job.
- Hardware constraints inherited from ios-sweet still apply: temporary
  `fastboot boot` images; iOS root in existing `userdata`; no GPT changes.
  Preserve bootloaders, recovery, modem, persist and partition backups.
  Confirm destructive device steps with the user before running them.
  Never run `fastboot getvar` (known device fastboot issues).
- Keep device dumps, serial numbers and downloaded Apple artifacts out of git.
  Historical local artifact paths are documented in `docs/UPSTREAM_NOTES.md`;
  they refer to the original workspace, not files present in this repository.

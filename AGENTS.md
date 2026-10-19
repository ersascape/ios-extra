# Working on ios-extra

- Read `HANDOFF.md` (how to continue, exact commands, pitfalls) and `NOTES.md`
  (current state) before starting; `docs/GPU_GMU_BOOT.md` is the hardware and
  mainline reference, `docs/GPU_LOG.md` the full history. This is the experimental playground for
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
- The user approved public visibility on 2026-10-18. The repository is now
  public and its XNU workflow can run. Keep local/device/Apple artifacts out
  of commits; use this repository's CI rather than the other agents' repo.
- Hardware constraints inherited from ios-sweet still apply: temporary
  `fastboot boot` images; iOS root in existing `userdata`; no GPT changes.
  Preserve bootloaders, recovery, modem, persist and partition backups.
  Confirm destructive device steps with the user before running them.
  Never run `fastboot getvar` (known device fastboot issues).
- Keep device dumps, serial numbers and downloaded Apple artifacts out of git.
  Historical local artifact paths are documented in `docs/UPSTREAM_NOTES.md`;
  they refer to the original workspace, not files present in this repository.
- Tracked helpers: `tools/gpu-package.py` (CI kernel -> temporary boot image),
  `tools/gpu-phone-test.py` (capture, one `fastboot boot`, decode),
  `tools/gpu-decode-pcap.py`, `tools/xnu-cc.py`. The phone is booted only after the
  user has put it in fastboot; never reboot it unannounced. No attribution text
  (assistant names, session links) in commits, docs or generated files.

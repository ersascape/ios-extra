# Working on ios-extra

- Read `HANDOFF.md` (how to continue, exact commands, pitfalls) and `NOTES.md`
  (current state) before starting; `docs/GPU_GMU_BOOT.md` is the hardware and
  mainline reference, `docs/GPU_LOG.md` the full history. This is the experimental playground for
  `ios-sweet`, with its own Git history and GitHub remote.
- Work in `/home/ersa/Dev/ios-extra-main` on branch `main`. This checkout's
  only GitHub remote is `ersascape/ios-extra`; use that repository for every
  push, build, log lookup, artifact download, and package record. Do not use
  `dipa-studio/ios-extra` or another account's repository.
- `/home/ersa/Dev/ios-extra` is a separate checkout with its own branch and
  existing work. Do not copy changes between checkouts or modify it unless the
  user asks. Treat `/home/dipa/ios-sweet` as read-only unless the user asks to
  integrate changes upstream.
- The imported baseline is upstream commit
  `347e19018e3e4c0117635e9e444f73659b2ece53`, patches 0001–0079.
  Preserve focused commits so working changes can be ported separately.
- Update `NOTES.md` after milestones and before stopping. Distinguish source
  inspection, build results and phone observations. Record exact commits,
  CI run IDs, boot images, logs and unfinished work.
- Commit completed changes. Use `gh` with `-R ersascape/ios-extra` for this
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
- Always check `fastboot devices` before asking the user to enter fastboot, and
  again immediately before each temporary boot (the test helper does the latter).
  Redact serials from displayed/stored output. If exactly one device is already
  in fastboot, announce and run the authorized pending test; do not ask the user
  to put it there again. If none is present, ask the user to enter fastboot. If
  multiple devices are present, stop until the target is unambiguous. This check
  never authorizes rebooting a running phone, flashing or using `getvar`.
- Keep device dumps, serial numbers and downloaded Apple artifacts out of git.
  Historical local artifact paths are documented in `docs/UPSTREAM_NOTES.md`;
  they refer to the original workspace, not files present in this repository.
- Tracked helpers: `tools/gpu-package.py` (CI kernel -> temporary boot image),
  `tools/gpu-phone-test.py` (capture, one `fastboot boot`, decode),
  `tools/gpu-decode-pcap.py`, `tools/xnu-cc.py`. The phone is booted only after the
  user has put it in fastboot; never reboot it unannounced. No attribution text
  (assistant names, session links) in commits, docs or generated files.

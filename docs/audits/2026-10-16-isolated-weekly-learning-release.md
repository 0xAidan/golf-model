# Isolated weekly learning release

Verified on 2026-10-16 UTC. This research service reads the live database and
retained verified corpus, appends private research artifacts, and publishes only
the sanitized reports. It does not replace the incumbent or promote a model.

## Installed boundary

- Current release: `/opt/golf-learning/releases/20261016-learning-memoryfix-95a82234e70b4248`;
  `/opt/golf-learning/current` points there. Earlier releases and all run versions remain.
- Private runs: `/opt/golf-learning/runs`, outside the application's legacy output API.
  All 94 files were mode `0600`, with directories `0700`, after completion.
- Shared database and snapshot: `/opt/golf-model/data`, mounted read-only in the
  actual service namespace. SQLite reads use `mode=ro` and `query_only=ON`.
  The ordinary application may still change its database independently.
- Sandbox: `ProtectSystem=strict`, `RestrictAddressFamilies=AF_UNIX`, one CPU,
  `MemoryMax=2147483648`, `UMask=0077`. Only private runs and the public reports
  directory are writable. Existing application source and units were not replaced.
- Public `learning-latest.json` and `learning-history.json` were mode `0644`.
  Each public temporary file is chmodded before atomic replacement; private
  artifacts retain the restrictive umask. The service drop-in also reapplies
  public modes after success/failure as a defense.

## Executed run and schedule

The first release (`9dc62b4ba005d9da`) hit its memory cgroup limit during corpus
readback, before training/publication. Kernel logs identify a cgroup OOM kill;
the two previously published report hashes were unchanged. That release, its
complete source snapshot, and failure receipts remain preserved.

The replacement changed only three runtime files: streamed canonical readback
instead of allocating a second full corpus; released redundant merged input
containers before feature construction; and set sanitized public modes before
replacement. Candidate families, cohort/split rules, baseline math, and resource
limits were unchanged. Forty-five focused challenger, identity, and publication
tests passed; Ruff and whitespace checks passed.

The protected retry completed successfully at **2026-10-16 05:10:19 UTC**:

- Invocation: `e730973569d346fdb2a2fdc02392dc0d`; exit `0`.
- CPU: `335833875000` ns; peak memory: `1589690368` bytes; peak swap: `0`.
- Run: `20261016-fcf57726c677264d`; 22 retained artifact files; all 14 declared
  implementation/input hashes and both model hashes verified.
- All 68 previously immutable run files remain byte-identical. The registry
  retains its original prefix and adds one row. Public history contains two valid
  runs and excludes five preserved invalidated runs.
- All 4,002 exposed-audit SG predictions match the independently reviewed local
  run within `1.84e-13`; published scalar metrics are identical. Raw calibration
  arrays differ by at most `2.17e-15` from platform floating-point roundoff.

The timer was enabled only after these checks. The successful manual completion
was recorded in the persistent timer stamp, avoiding an immediate duplicate fit.
Next execution: **Tuesday 2026-10-20 04:30:00 UTC**. The timer is active/waiting;
the service remained inactive/success with no second invocation after enablement.

## Exact identities

| Item | SHA-256 |
| --- | --- |
| Installed bundle, 19,752,346 bytes | `98bbd7ccae286218b6df21adcdb7cceef32d393e627ff402acdc3ea5ec14d977` |
| Release manifest; all 189 payload files verified | `55f62f96790dd011002e17ae13ee78a7274ac135455028e604d1d1ae6296cb26` |
| Payload identity | `95a82234e70b4248b7f64a18a26706da648d6f8700c6856d571697e99dae5e6a` |
| Verified seed gzip | `77fa175573bd03b214984de193e20466ecb4c0f045e7bd3e9a3b6ab722afb418` |
| Pinned incumbent | `453f49ec24f0e48a8f85250e678fce386bfbd072772e93111cf27c6b34b0f90c` |
| Canonical merged corpus | `529d84d0a7a25de5549b437c1a922a7083e5ece28f50f1f6ec34cceffc471216` |
| Retained corpus gzip | `80cd0002c408c88ea2b814f8c05f88a16ca82e4808d550bb78190173af3ca31d` |
| Evaluated challenger | `24db088fd8780332818cd7fdc9a1721080790248a2df1c22d939c3c2c74b3c48` |
| Forward-only refit | `03fbb5e99eb2f6ffec78115c5e2ac3aedd1bd013cfb2bf91d9d1147652f91ba4` |
| Published latest report, 118,366 bytes | `e394ff2a89253fc7d0aedb068fd578ab7adea4d202a305e1e3d7f55ad360bb3c` |
| Published history, 2,580 bytes | `6c0866903c2c7ac682549d20db7171ac18c181e89ec87f907ff77c8fb6d291a4` |

The retained corpus has 147,124 rounds and 371 calendar records. Its additional
calendar record relative to the reviewed local run is the Presidents Cup, which
existing team-event exclusion rules do not admit. No new completed events were
learned. The report explicitly records this freshness warning. Hash changes bind
the current retained source and implementation; they are not improvement claims.

## Evidence and limits

Server receipts, including failed-run kernel evidence, installed unit text,
running mount evidence, checkpoints, public report readback, history preservation
checks, and timer state, are under `/opt/golf-learning/install-receipts/`.
Private local copies are under
`/Users/aidannugent/websites/golf-model-preservation/2026-10-16-isolated-learning-release/server-receipts/`.
The receipts archive SHA-256 is
`6a30b1136c1c91bc9ff5ea30bfca53a3f149c24b51c31b9cbf68765ee0ca9dd8`.
The local 22-file run archive SHA-256 is
`15e93050c48631e6a9d25248cfced26219e8146009857cfe5a0f02a7335380c2`;
its 14 declared inputs were independently checked after transfer.

The standalone effective privacy override is retained at
`/Users/aidannugent/websites/golf-model-preservation/2026-10-16-isolated-learning-release/overrides/20261016-learning-memoryfix-95a82234e70b4248/privacy.conf`
with SHA-256 `a47b2ed79b18a0a5506828675aac6c3d4956092a6d5d64dc34da3a4f7aac36be`.

The 2026 evaluation remains exposed retrospective research: 37 events / 4,002
player-events, candidate log loss `0.642518`, Brier `0.225974`, SG RMSE `1.642753`,
versus SG50 log loss `0.656387`. Pair counts are correlated observations. ROI and
CLV remain unqualified/null, promotion remains false, and the sealed holdout was
not evaluated. One successful bounded run establishes operational readiness for
this corpus; growing future corpora remain subject to the same fail-closed cap.

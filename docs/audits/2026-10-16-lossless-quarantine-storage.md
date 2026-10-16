# Lossless server quarantine storage — October 16, 2026

At 04:44:55.098614 UTC, one inactive damaged database was switched from its
uncompressed physical representation to a verified lossless gzip. Historical
bytes remain preserved on the server and in an independently verified off-server
archive. The active application database was not changed.

## Exact preserved identity

- Original path: `/opt/golf-model/data/golf.db.malformed_20260913_180810`.
- Raw size: 6,835,355,648 bytes.
- Raw SHA-256: `2f514028ff41c6ac631129698017c8de56eb494a00ca35425dc4f1346c6f3ef4`.
- Gzip size: 382,825,848 bytes.
- Gzip SHA-256: `59b28d758aaae1d4081d9e788d962ee683c791305e804245b8276968a7946824`.
- Server archive directory:
  `/opt/golf-model-preservation/quarantine-compression/20261016/20261016T043848Z_ef02b84ae8cb/`.

Compression read the source without changing its bytes. A complete decompression
readback checked the raw byte count, raw SHA-256 and gzip CRC before cutover.
Source inode/device/size/timestamps/mode/link count, unchanged sidecars and absence
of open process handles were checked again before releasing the redundant raw
physical representation. This is a representation change, not an assertion that
the original raw path still exists.

The server directory retains the gzip, manifest, cutover receipt and
`restore_raw_copy.py`. The original directory retains an `.ARCHIVED.json` bridge.
The restore script refuses to overwrite an existing path and verifies restored
bytes before installing them at the exact original location. Private evidence
directories use mode 0700 and archive/receipt files use mode 0600.

## Independent retained copies

The pre-existing off-server `quarantines-with-sidecars.tar.gz` is 3,125,477,856
bytes with SHA-256
`d40c7d6ddc00f78fc8d4aebbee1a36e80458b7bcbc101c7d6bc65186258ad3e9`.
All 18 original database/WAL/SHM members were independently validated. Its
compressed hash and validation-manifest hash were freshly checked before the
server cutover. The validation-manifest SHA-256 is
`588a258084b080b32e1e125f907e231ebdd83e849555e87d74399852afbfc835`.

The separate disposable raw copy and complete forensic SQL recovery also remain
preserved locally. Salvaged rows remain uncorroborated and are not performance or
model-promotion evidence.

The active database, original sidecars and application processes were unchanged.
Free server space measured 12,694,892,544 bytes immediately after cutover. Other
raw quarantines remain untouched. Local copies of the cutover receipts and restore
script are under the private `2026-10-16-quarantine-compression` preservation
folder; no private database or source payload was added to public assets.

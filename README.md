# PipeCore

Custom NeoForge pipe mod project for Minecraft 26.1.2.

## Canonical project state

- Current development version: **V24**
- Internal mod version: **1.3.21**
- Canonical SHA-256: `46cfabdcf125a999df400ac00a15756a941c1b3febe8c08ae7f2b853b8cb69ca`

The exact V24 JAR supplied by the user is preserved losslessly in `baselines/parts/` as ordered Base64 chunks. Run `scripts/restore_baseline.py` to reconstruct `baselines/PipeCore-V24-1.3.21-NeoForge-26.1.2.jar` and verify its hash.

The older source/history already present in this repository remains preserved, but it must not be treated as equivalent to V24 unless verified against the canonical artifact.

Before implementing any new PipeCore change, read [`PROJECT_STATE.md`](PROJECT_STATE.md) and [`CHANGELOG.md`](CHANGELOG.md).

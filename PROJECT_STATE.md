# PipeCore — Project State

## Canonical status

- Project: PipeCore
- Minecraft: 26.1.2
- Loader: NeoForge
- Current project version: V24
- Internal mod version in the canonical supplied JAR: `1.3.21`
- Canonical JAR supplied by the user on 2026-08-19.
- Canonical JAR SHA-256: `46cfabdcf125a999df400ac00a15756a941c1b3febe8c08ae7f2b853b8cb69ca`
- Mod ID: `pipecore`
- Main package: `com.pipecore`

The supplied `1.3.21` JAR is the authoritative V24 runtime baseline. Older repository source/history must not be treated as equivalent to V24 unless it is verified against this artifact.

## Safety rule

Before changing PipeCore in any conversation:

1. Read this file.
2. Check the latest tag/release/commit.
3. Verify that the working source/artifact matches V24 / `1.3.21` or a later explicitly recorded version.
4. Compare the candidate baseline against the canonical SHA-256 when the original V24 JAR is involved.
5. Never infer or recreate missing versions from memory.
6. Never remove an existing feature unless the user explicitly requests it.

## Known design decisions that must be preserved

- UI priority controls remain available independently of upgrade cards.
- Energy pipes are bidirectional; no artificial input/output mode.
- Pipe/card art uses 16×16 textures.
- Cards do not use letters/names baked into the icon.
- Red is reserved for the Netherite tier.
- Pipe contents must remain visually readable through the pipe geometry.
- Filter/discard controls belong only to item-pipe functionality unless explicitly redesigned later.

## Repository/source status

The GitHub repository predates parts of the canonical V24 development line. The supplied V24 `1.3.21` JAR closes the version-identification gap, but the matching source tree has not yet been proven identical to that binary. For future development, verify/reconstruct/import the matching V24 source before making structural changes.

## Invalid historical branch/PR

PR #5 (`Pipe Core V18: render, UI and card rules`) was created from an outdated base and was closed without merge. It is not part of the canonical line.

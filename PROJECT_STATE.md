# PipeCore — Project State

## Canonical status

- Project: PipeCore
- Minecraft: 26.1.2
- Loader: NeoForge
- User-confirmed current development version: V24
- Repository `main` is currently behind the user-confirmed V24 baseline.
- Until the real V24 JAR/source is imported, **do not use the current `main` branch as the authoritative implementation baseline for new PipeCore development**.

## Safety rule

Before changing PipeCore in any conversation:

1. Read this file.
2. Check the latest tag/release/commit.
3. Confirm that the repository baseline matches the current project version.
4. If repository code and project version disagree, stop implementation and import/verify the correct baseline first.
5. Never infer or recreate missing versions from memory.

## Known design decisions that must be preserved

- UI priority controls remain available independently of upgrade cards.
- Energy pipes are bidirectional; no artificial input/output mode.
- Pipe/card art uses 16×16 textures.
- Cards do not use letters/names baked into the icon.
- Red is reserved for the Netherite tier.
- Pipe contents must remain visually readable through the pipe geometry.
- Filter/discard controls belong only to item-pipe functionality unless explicitly redesigned later.

## Version gap

The repository history currently available here does not contain the complete V18–V24 canonical line. Those versions must not be reconstructed by assumption. Import the real V24 artifact/source before the next PipeCore feature release.

## Invalid historical branch/PR

PR #5 (`Pipe Core V18: render, UI and card rules`) was created from an outdated base and has been closed without merge. It is not part of the canonical line.

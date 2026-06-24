# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-06-24

### Fixed

- **Release detection now handles all real-world VIB version formats.** Initial
  release only matched the HPE `OEM.<MMm>` build tag, so VMware base-depot VIBs
  (which use `vmw.<MMm>`, e.g. `41vmw.902`) and VMware system VIBs (bare leading
  version, e.g. `9.0.2-0.25148076`) all fell through to `unknown`. Validated
  against a real HPE Synergy AddOn depot + a VMware ESXi 9.0.2 base depot:
  detection now correctly groups HPE `OEM.*`, VMware `vmw.*`, and bare
  `MAJOR.MINOR` versions, while still leaving genuinely unmarked cross-version
  utilities (e.g. `storcli`, `tools-light`) in `unknown`.

## [1.0.0] - 2026-06-24

### Initial Release

Tooling to extract ESXi-relevant VIBs from an HPE Service Pack for ProLiant
(SPP), group them by ESXi release, and emit the OS-release manifest the SPP
content list doesn't provide. Built to fill the gap created by HPE's
deprecation of standalone Synergy custom ISOs and AddOn depots (SSP 2026.01.xx,
Customer Notice a00156316): drivers now live in the SPP, but the SPP mixes all
operating systems together with no per-release grouping.

### Added

- **`scripts/extract_esxi_vibs.py`** — The core. Walks an extracted SPP, parses
  VIB descriptors from bare `.vib` files, ESXi offline bundles, and HPE smart
  components that wrap offline bundles. Detects the target ESXi release from the
  `esx` dependency constraint (with an `OEM.<MMm>` version-string fallback),
  groups components into per-release folders, and writes a CSV + JSON manifest.
  Standard library only — no pip installs. Modes: `--release` filter,
  `--manifest-only`, `--link` (hardlink instead of copy).

- **`scripts/Extract-EsxiVibs.ps1`** — Windows wrapper so the tool fits the
  existing PowerCLI Image Builder workflow. Finds Python on PATH and forwards
  to the core.

- **`examples/example-manifest.csv`** — Sample of the output manifest.

- **`docs/HOW_IT_WORKS.md`** — SPP structure, the ESXi-content detection logic,
  release-detection method (constraint + OEM fallback + honest "unknown"),
  the 8.0-vs-9.0 boundary note, and limitations.

### Companion

Pairs with [esxi-hpe-synergy-imagebuilder](https://github.com/noahfarshad/esxi-hpe-synergy-imagebuilder):
this repo gets the right driver components out of the SPP and grouped by release;
that repo merges them with a VMware base depot into an installable custom ISO.

### Notes

- Redistributes no HPE/VMware binaries — the user provides the SPP (entitlement
  required).
- Read-only on the SPP; copies or hardlinks into the output directory.
- Community tooling, not an HPE product. Validate output against HPE's VMware
  Recipe and an HCL device-ID check before production.

[1.0.1]: https://github.com/noahfarshad/spp-esxi-vib-extractor/releases/tag/v1.0.1
[1.0.0]: https://github.com/noahfarshad/spp-esxi-vib-extractor/releases/tag/v1.0.0

# spp-esxi-vib-extractor

Scan an HPE Service Pack for ProLiant (SPP), pull out the ESXi-relevant VIBs, group them by ESXi release, and emit the OS-release manifest the SPP content list doesn't give you — so the output drops straight into PowerCLI Image Builder.

## Why this exists

As of HPE Synergy SSP 2026.01.xx, HPE no longer ships standalone Synergy custom ISOs or Certified Vendor Add-on depots. The supported path is now: take the VMware base ESXi image and apply HPE drivers/utilities delivered through the **SPP**. (HPE Customer Notice a00156316.)

The catch: the SPP is one big bundle of "smart components" for **every** operating system — ESXi, RHEL, SLES, Windows — plus firmware. Its content list has **no column grouping components by OS release**. So when you need "just the ESXi 9.0 VIBs" to build a custom image, you're stuck doing spreadsheet archaeology against the SPP contents report.

This tool does that grouping automatically. Point it at an extracted SPP and it gives you:

- Per-release folders (`esxi-9.0/`, `esxi-8.0/`, …) containing the relevant VIBs/bundles
- A **manifest** (CSV + JSON) with the `esxi_release` column the SPP report lacks — VIB name, version, vendor, the ESXi constraint, container type, and source file

It's the missing front-half of the workflow: this tool gets you the right driver components out of the SPP, then the companion [esxi-hpe-synergy-imagebuilder](https://github.com/noahfarshad/esxi-hpe-synergy-imagebuilder) merges them with a VMware base depot into an installable ISO.

## What's here

```
spp-esxi-vib-extractor/
├── scripts/
│   ├── extract_esxi_vibs.py     # the core: scan SPP, parse VIBs, group by release
│   └── Extract-EsxiVibs.ps1     # Windows wrapper for the Image Builder workflow
├── examples/
│   └── example-manifest.csv     # what the output manifest looks like
├── docs/
│   └── HOW_IT_WORKS.md          # detection logic, SPP structure, limitations
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## Quick start

You provide the SPP (it requires HPE entitlement to download — this repo redistributes nothing). Extract/mount the SPP first, then point the tool at that directory.

**Python (any platform):**

```bash
# Group everything by release + write the manifest
python3 scripts/extract_esxi_vibs.py --spp /path/to/extracted-spp --out ./esxi-vibs

# Only pull ESXi 9.0 content (manifest still covers everything)
python3 scripts/extract_esxi_vibs.py --spp /path/to/extracted-spp --out ./out --release 9.0

# Just survey what's in the SPP — manifest only, no file copying
python3 scripts/extract_esxi_vibs.py --spp /path/to/extracted-spp --out ./out --manifest-only
```

**PowerShell (fits the Windows Image Builder workflow):**

```powershell
.\scripts\Extract-EsxiVibs.ps1 -SppPath "D:\spp-extracted" -OutPath ".\esxi-vibs"
.\scripts\Extract-EsxiVibs.ps1 -SppPath "D:\spp-extracted" -OutPath ".\out" -Release 9.0
.\scripts\Extract-EsxiVibs.ps1 -SppPath "D:\spp-extracted" -OutPath ".\out" -ManifestOnly
```

Only requirement is Python 3.7–3.12 — the extractor uses the standard library only (no pip installs).

## What the output looks like

```
esxi-vibs/
├── esxi-9.0/
│   ├── qlnativefc-900-offline_bundle.zip
│   ├── qcnic-900-offline_bundle.zip
│   └── cp056789.zip            (smart component wrapping an ESXi 9.0 bundle)
├── esxi-8.0/
│   └── cp054321.zip
├── esxi-vib-manifest.csv
└── esxi-vib-manifest.json
```

And the manifest gives you the grouping the SPP report doesn't (see `examples/example-manifest.csv`):

| esxi_release | vib_name | version | vendor | container_type | source_file |
|---|---|---|---|---|---|
| 9.0 | qlnativefc | 5.5.0.50-1OEM.900… | MVL | offline_bundle | qlnativefc-900-offline_bundle.zip |
| 9.0 | amsd | 900.11.13.0.5-1OEM.900… | HPE | smart_component | cp056790.zip |
| 8.0 | bnxtnet | 225.0.130.0-1OEM.800… | BCM | smart_component | cp054321.zip |

## How release detection works (the short version)

For each VIB, the tool reads the descriptor and pulls the ESXi version from the `esx` dependency constraint (e.g. `9.0.0-0.0.0` → release `9.0`). When no constraint is present, it falls back to the `OEM.<MMm>` encoding in the VIB version string (`…OEM.900…` → `9.0`). Anything it can't classify lands in `esxi-unknown/` and is flagged in the run output, so you're never silently missing something. Full detail in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## What it deliberately doesn't do

- **No binaries redistributed.** You bring the SPP (HPE entitlement required).
- **Read-only on the SPP.** It copies (or `--link` hardlinks) into the output; it never modifies the source.
- **It doesn't build an ISO.** That's the companion repo's job — feed the grouped folder into PowerCLI Image Builder.
- **It's not an HPE tool.** Community tooling. Always validate the resulting image against HPE's support matrix and the current VMware Recipe before production.

## The bigger workflow

```
   HPE SPP (you download)
        │
        ▼
  spp-esxi-vib-extractor   ← this repo: pull + group ESXi VIBs by release
        │
        ▼
  esxi-9.0/ folder + manifest
        │
        ▼
  esxi-hpe-synergy-imagebuilder   ← companion repo: merge with VMware base → ISO
        │
        ▼
  custom ESXi ISO that boots HPE Synergy from SAN
```

## Story

Background on why both of these tools exist — and the HPE Synergy deprecation that made them necessary — is written up at [essential.coach](https://essential.coach/custom-esxi-iso-hpe-synergy/).

## License

GPL-3.0. See [LICENSE](LICENSE).

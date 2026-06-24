# How It Works

The detail behind the extractor: what an SPP actually contains, how the tool finds ESXi VIBs in it, how it decides which ESXi release each one targets, and where the limits are.

## What's in an SPP

An HPE Service Pack for ProLiant (SPP) is a large collection of "smart components" plus firmware, bundled for offline deployment via Smart Update Manager (SUM). The components cover **every** supported operating system — VMware ESXi, RHEL, SLES, Windows — and firmware for the server hardware itself. For each release HPE integration-tests all the components together.

The components show up in a few shapes:

- **Bare VIBs** (`*.vib`) — a single ESXi driver/tool package (a Unix `ar` archive containing `descriptor.xml`, a signature, and the payload).
- **ESXi offline bundles** (`*.zip`) — a VMware-format depot zip containing one or more VIBs, a `vmware.xml`, and a `metadata.zip` describing them.
- **HPE smart components** (`cp######.zip`) — HPE's packaging wrapper. For ESXi content these typically **wrap** an offline bundle inside the component zip, alongside HPE installer metadata.

The problem the tool solves: the SPP's content report lists all of these together with versions, but **without a column telling you which OS release each one is for**. Finding the ESXi 9.0 set means cross-referencing names and versions by hand.

## How the tool finds ESXi content

The scanner walks the extracted SPP tree and classifies each file:

1. **`*.vib`** → read the descriptor directly. A `.vib` is an `ar` archive, but the `descriptor.xml` is stored uncompressed, so the tool locates the XML by its `<vib>…</vib>` markers and parses it. (No external `ar` tooling needed — keeps the tool dependency-free.)

2. **`*.zip`** → check whether it looks like an ESXi offline bundle by testing for `vmware.xml`, `metadata.zip`, or `descriptor.xml` entries.
   - If yes → parse the descriptors out of it (directly, or from the nested `metadata.zip`).
   - If no → treat it as a possible **smart-component wrapper**: look for a nested `*.zip` inside that *does* look like an ESXi bundle, extract that, and parse it. This is what catches ESXi drivers delivered as `cp######.zip` components.

3. **Anything else** (Windows `.inf`, Linux `.rpm`, `.scexe`, firmware images) → ignored. Only ESXi-relevant content lands in the output. This is the OS filtering that the SPP report doesn't do for you.

De-duplication is by `(vib_name, version)`, so the same VIB appearing in multiple places is reported once.

## How release detection works

For each VIB descriptor the tool determines the ESXi release two ways, in order of reliability:

### 1. The `esx` dependency constraint (primary)

A VIB descriptor declares what it depends on. ESXi drivers depend on a specific `esx` base version:

```xml
<relationships>
  <depends>
    <constraint name="esx" relation="&gt;=" version="9.0.0-0.0.0"/>
  </depends>
</relationships>
```

The tool reads that `version` (`9.0.0-0.0.0`) and reduces it to a release label: `9.0`. This is authoritative — it's the VIB telling you what base it was built against.

### 2. The version-string encoding (fallback)

When a descriptor has no usable `esx` constraint, the tool reads the release from the VIB's own version string. Validated against a real HPE Synergy AddOn depot and a VMware ESXi 9.0.2 base depot, three formats appear:

| Version string | Source | Release |
|---|---|---|
| `234.0.159.1-1OEM.900.0.24755229` | HPE driver (`OEM.<MMm>`) | 9.0 |
| `2.0.67.0-1OEM.700.1.0.15843807` | HPE driver (`OEM.<MMm>`) | 7.0 |
| `226.0.31.0-41vmw.902.0.25148076` | VMware driver (`vmw.<MMm>`) | 9.0 |
| `5.4.82.0-3vmw.900.0.24755229` | VMware driver (`vmw.<MMm>`) | 9.0 |
| `9.0.2-0.25148076` | VMware system VIB (leading) | 9.0 |
| `9.0.2.0-9.0.25145108` | NSX component (leading) | 9.0 |

The `<MMm>` build tag encodes the release: `MM` = major, `m` = minor (so `900`/`902` → 9.0, `802` → 8.0, `700` → 7.0). Both HPE (`OEM.`) and VMware (`vmw.`) use this scheme. VMware system VIBs and NSX components instead carry a leading `MAJOR.MINOR` directly.

### 3. Unknown (honest fallback)

If none of the above yields a release, the VIB lands in an `esxi-unknown/` folder and is flagged. Genuinely unmarked components stay here on purpose — e.g. `storcli` (a cross-version management utility with a `007.3212...` version) and `tools-light` (a VMware-internal `13.0` version that isn't an ESXi release). The leading-version match is deliberately restricted to a plausible ESXi major range (6–12) and rejects zero-padded driver versions, so it doesn't mistake a driver's own version number for an ESXi release. The tool never silently drops or misfiles a component — if it can't classify something, it says so.

## Note on update boundaries (8.0 vs 9.0+)

Release detection here reports the **minor** release (`9.0`, `8.0`), which is the right granularity for the 9.0+ world. HPE's support rule changed at 9.0: for ESXi 8.0 and older, the support boundary is an "update" release (8.0 U2 → 8.0 U3); for 9.0 and newer, it's a "minor" release. The manifest's `esx_constraint` column preserves the full version string so you can see the exact base if you need finer detail than the release label. As always, validate the final combination against HPE's current VMware Recipe and your SSP — see the companion imagebuilder repo's build guide for the full support-boundary discussion.

## Output: the manifest

The manifest is the deliverable that closes the original gap a peer raised — the OS-release column the SPP report lacks. Two formats:

- **`esxi-vib-manifest.csv`** — one row per VIB: `esxi_release, vib_name, version, vendor, esx_constraint, container_type, source_file`. Open it in any spreadsheet and filter/sort by release.
- **`esxi-vib-manifest.json`** — same data plus a per-release count summary, for scripting.

## Limitations and honesty

- **Detection is descriptor-driven.** If HPE changes the SPP packaging format substantially, the smart-component unwrapping heuristic may need updating. The `--manifest-only` mode is a fast way to sanity-check what the tool sees before trusting a full extraction.
- **It classifies by what the VIB declares, not by HPE's certification matrix.** A VIB targeting `esx 9.0.0` is grouped under `9.0`; whether that specific driver is *supported* on your exact base patch and hardware is still a question for the HPE Recipe and an HCL check (VID/DID/SVID/SSID).
- **It's a starting point, not a support guarantee.** Community tooling. The output is meant to save you the manual grouping, not to replace validation against HPE's official documentation.

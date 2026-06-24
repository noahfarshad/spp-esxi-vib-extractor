#!/usr/bin/env python3
"""
extract_esxi_vibs.py

Scan an extracted/mounted HPE Service Pack for ProLiant (SPP) tree, find the
ESXi-relevant VIBs and offline bundles, determine which ESXi release each one
targets, and sort them into per-release folders -- plus emit the OS-release
manifest the SPP content list doesn't give you.

WHY THIS EXISTS
---------------
As of HPE Synergy SSP 2026.01.xx, HPE no longer ships standalone Synergy custom
ISOs or Certified Vendor Add-ons. The supported path is: take the VMware base
ESXi image and apply HPE drivers/utilities delivered through the SPP. But the
SPP is a single bundle of "smart components" for EVERY OS (ESXi, RHEL, SLES,
Windows) and firmware, and its content list has no column grouping components
by OS release. Finding "just the ESXi 9.0 VIBs" by hand is spreadsheet
archaeology. This tool does that grouping for you, so the output drops straight
into PowerCLI Image Builder (see the companion esxi-hpe-synergy-imagebuilder repo).

WHAT IT DOES
------------
1. Walks the SPP directory looking for:
   - Bare VIBs (*.vib)
   - ESXi offline bundles (*.zip containing vmware.xml / metadata.zip / a VIB index)
   - HPE smart-component zips (cp******.zip) that wrap an ESXi offline bundle
2. For each VIB, reads its descriptor.xml to get name, version, vendor, and the
   ESXi version it was built for (the "esx" software requirement, e.g. 9.0.0).
3. Groups everything by detected ESXi release into output subfolders.
4. Writes a manifest (CSV + JSON) with the OS-release column the SPP list lacks.

WHAT IT DOES NOT DO
-------------------
- Does not download or redistribute any HPE/VMware binaries. You provide the SPP.
- Does not modify the SPP. It copies (or with --link, hardlinks) into the output dir.
- Does not build an ISO. Feed the grouped output into Image Builder for that.

USAGE
-----
    python3 extract_esxi_vibs.py --spp /path/to/extracted-spp --out ./esxi-vibs
    python3 extract_esxi_vibs.py --spp /mnt/spp --out ./out --release 9.0 --link
    python3 extract_esxi_vibs.py --spp /mnt/spp --out ./out --manifest-only

Author : Noah Farshad / essential.coach
License : GPL-3.0
"""

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict


# ---------------------------------------------------------------------------
# VIB descriptor parsing
# ---------------------------------------------------------------------------

def parse_vib_descriptor(xml_bytes):
    """
    Parse a VIB descriptor.xml and return a dict of the fields we care about.

    A .vib file is an ar archive containing 'descriptor.xml'. An offline bundle
    stores the same descriptor content inside its metadata. The descriptor
    contains <name>, <version>, <vendor>, and a <relationships><depends> block
    with a constraint on 'esx' that tells us the ESXi version it targets.
    """
    info = {
        "vib_name": None,
        "version": None,
        "vendor": None,
        "esx_version": None,
        "summary": None,
    }
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return info

    def text(tag):
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else None

    info["vib_name"] = text("name")
    info["version"] = text("version")
    info["vendor"] = text("vendor")
    info["summary"] = text("summary")

    # The ESXi version a VIB targets shows up as a dependency constraint on the
    # 'esx' package, e.g. <constraint name="esx" relation="&gt;=" version="9.0.0-0.0.0"/>
    # We pull the first esx constraint version we find.
    for constraint in root.iter("constraint"):
        if (constraint.get("name") or "").lower() == "esx":
            ver = constraint.get("version")
            if ver:
                info["esx_version"] = ver
                break

    return info


def normalize_esx_release(esx_version, vib_name=None, vib_version=None):
    """
    Determine the ESXi release label ('9.0', '8.0', '7.0') for a VIB.

    Real-world VIB version strings come in several shapes (confirmed against an
    actual HPE Synergy AddOn depot and a VMware ESXi 9.0.2 base depot):

      HPE driver     : 234.0.159.1-1OEM.900.0.24755229     -> OEM.900  -> 9.0
      HPE driver     : 2.0.67.0-1OEM.700.1.0.15843807      -> OEM.700  -> 7.0
      VMware driver  : 226.0.31.0-41vmw.902.0.25148076     -> vmw.902  -> 9.0
      VMware driver  : 5.4.82.0-3vmw.900.0.24755229        -> vmw.900  -> 9.0
      VMware system  : 9.0.2-0.25148076                    -> leading  -> 9.0
      NSX component  : 9.0.2.0-9.0.25145108                -> leading  -> 9.0
      cross-version  : 007.3212.0000.0000-02 (storcli)     -> no marker -> unknown

    Detection order: (1) the esx dependency constraint if present, then the
    version string via (2) the OEM/vmw '<MMm>' build-tag encoding, then
    (3) a leading 'MAJOR.MINOR' at the very start of the version.
    """
    # 1) Primary: the esx dependency constraint, shaped like MAJOR.MINOR.PATCH-...
    if esx_version:
        m = re.match(r"^(\d+)\.(\d+)", esx_version)
        if m:
            return f"{m.group(1)}.{m.group(2)}"

    candidates = [c for c in (vib_version or "", vib_name or "") if c]

    # 2) Build-tag encoding: both HPE ('OEM.900') and VMware ('vmw.902') VIBs
    #    embed the release as '<vendor-tag>.<MMm>' where MM=major, m=minor.
    #    e.g. OEM.700 -> 7.0, vmw.902 -> 9.0, OEM.802 -> 8.0
    for candidate in candidates:
        m = re.search(r"(?:OEM|vmw)\.(\d)(\d)\d", candidate, re.IGNORECASE)
        if m:
            return f"{m.group(1)}.{m.group(2)}"

    # 3) Leading 'MAJOR.MINOR' on the version itself (VMware system VIBs and NSX
    #    components: '9.0.2-0.25148076', '9.0.2.0-9.0.25145108'). Only trust this
    #    on the version field, only for a plausible ESXi major (6-12), and not for
    #    zero-padded driver versions like '007.3212...' (storcli) which aren't
    #    ESXi releases at all.
    if vib_version:
        m = re.match(r"^(\d{1,2})\.(\d+)", vib_version)
        if m:
            major_str, minor = m.group(1), m.group(2)
            major = int(major_str)
            # Reject zero-padded leading numbers (e.g. '007') -- those are driver
            # version schemes, not ESXi releases.
            if not major_str.startswith("0") and 6 <= major <= 12:
                return f"{major}.{minor}"

    return "unknown"


# ---------------------------------------------------------------------------
# Reading VIBs out of various container formats
# ---------------------------------------------------------------------------

def read_descriptor_from_vib(path):
    """
    A .vib is a Unix 'ar' archive. We don't need a full ar parser -- the
    descriptor.xml is stored uncompressed, so we can locate it by scanning the
    bytes for the descriptor's XML root and reading to its close tag.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    start = data.find(b"<vib")
    end = data.find(b"</vib>")
    if start != -1 and end != -1:
        return data[start:end + len(b"</vib>")]
    return None


def iter_descriptors_from_bundle(path):
    """
    An ESXi offline bundle is a zip. The VIB descriptors live either as
    'descriptor.xml' inside per-VIB folders, or are referenced from the bundle's
    metadata.zip. We pull every descriptor.xml we can find.

    Yields raw descriptor XML byte strings.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()

            # Case A: descriptors stored directly in the bundle
            direct = [n for n in names if n.endswith("descriptor.xml")]
            for n in direct:
                with zf.open(n) as fh:
                    yield fh.read()

            # Case B: descriptors live inside metadata.zip
            metas = [n for n in names if n.endswith("metadata.zip")]
            for meta in metas:
                with zf.open(meta) as mfh:
                    meta_bytes = mfh.read()
                try:
                    with zipfile.ZipFile(io.BytesIO(meta_bytes)) as mzf:
                        for n in mzf.namelist():
                            if n.endswith("descriptor.xml") or (
                                n.startswith("vibs/") and n.endswith(".xml")
                            ):
                                with mzf.open(n) as fh:
                                    yield fh.read()
                except zipfile.BadZipFile:
                    continue
    except (zipfile.BadZipFile, OSError):
        return


def bundle_looks_like_esxi(path):
    """
    Quick check: does this zip look like an ESXi offline bundle (vs a Windows/
    Linux smart component that happens to be a zip)? We look for the tell-tale
    'vmware.xml', a metadata.zip, or descriptor.xml entries.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            return any(
                n.endswith("vmware.xml")
                or n.endswith("metadata.zip")
                or n.endswith("descriptor.xml")
                for n in names
            )
    except (zipfile.BadZipFile, OSError):
        return False


def unwrap_smart_component(path, workdir):
    """
    HPE smart components (cp######.zip / .scexe / .exe) often WRAP an ESXi
    offline bundle. If this zip contains a nested *.zip that looks like an ESXi
    bundle, extract that nested bundle to workdir and return its path. Otherwise
    return None.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            nested = [n for n in zf.namelist() if n.lower().endswith(".zip")]
            for n in nested:
                extracted = zf.extract(n, workdir)
                if bundle_looks_like_esxi(extracted):
                    return extracted
    except (zipfile.BadZipFile, OSError):
        return None
    return None


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_spp(spp_dir, workdir):
    """
    Walk the SPP tree and return a list of discovered ESXi component records.
    Each record: dict with source_path, container_type, vib_name, version,
    vendor, esx_version, release.
    """
    records = []
    seen = set()

    for dirpath, _dirs, files in os.walk(spp_dir):
        for fname in files:
            fpath = os.path.join(dirpath, fname)
            lower = fname.lower()

            # 1) Bare VIBs
            if lower.endswith(".vib"):
                desc = read_descriptor_from_vib(fpath)
                if desc:
                    info = parse_vib_descriptor(desc)
                    info["release"] = normalize_esx_release(
                        info["esx_version"], info["vib_name"], info["version"]
                    )
                    info["source_path"] = fpath
                    info["container_type"] = "vib"
                    key = (info["vib_name"], info["version"])
                    if key not in seen:
                        seen.add(key)
                        records.append(info)
                continue

            # 2) Zips: could be an ESXi offline bundle OR a smart component wrapper
            if lower.endswith(".zip"):
                bundle_path = None
                container = None

                if bundle_looks_like_esxi(fpath):
                    bundle_path = fpath
                    container = "offline_bundle"
                else:
                    # Maybe a smart component wrapping a bundle
                    unwrapped = unwrap_smart_component(fpath, workdir)
                    if unwrapped:
                        bundle_path = unwrapped
                        container = "smart_component"

                if bundle_path:
                    for desc in iter_descriptors_from_bundle(bundle_path):
                        info = parse_vib_descriptor(desc)
                        if not info["vib_name"]:
                            continue
                        info["release"] = normalize_esx_release(
                            info["esx_version"], info["vib_name"], info["version"]
                        )
                        info["source_path"] = fpath  # the original SPP file
                        info["container_type"] = container
                        key = (info["vib_name"], info["version"])
                        if key not in seen:
                            seen.add(key)
                            records.append(info)

    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_outputs(records, out_dir, release_filter=None, link=False,
                  manifest_only=False):
    os.makedirs(out_dir, exist_ok=True)

    grouped = defaultdict(list)
    for r in records:
        grouped[r["release"]].append(r)

    # Per-release folders + copied/linked source files
    if not manifest_only:
        for release, items in grouped.items():
            if release_filter and release != release_filter:
                continue
            rel_dir = os.path.join(out_dir, f"esxi-{release}")
            os.makedirs(rel_dir, exist_ok=True)
            copied = set()
            for r in items:
                src = r["source_path"]
                if src in copied:
                    continue
                copied.add(src)
                dst = os.path.join(rel_dir, os.path.basename(src))
                try:
                    if link:
                        if os.path.exists(dst):
                            os.remove(dst)
                        os.link(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except OSError as e:
                    print(f"  ! could not place {src}: {e}", file=sys.stderr)

    # Manifest (CSV + JSON) -- the OS-release column the SPP list lacks
    manifest_rows = sorted(
        records,
        key=lambda r: (r["release"], r["vendor"] or "", r["vib_name"] or ""),
    )

    csv_path = os.path.join(out_dir, "esxi-vib-manifest.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "esxi_release", "vib_name", "version", "vendor",
            "esx_constraint", "container_type", "source_file",
        ])
        for r in manifest_rows:
            w.writerow([
                r["release"], r["vib_name"], r["version"], r["vendor"],
                r["esx_version"], r["container_type"],
                os.path.basename(r["source_path"]),
            ])

    json_path = os.path.join(out_dir, "esxi-vib-manifest.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": {
                    rel: len(items) for rel, items in sorted(grouped.items())
                },
                "vibs": manifest_rows,
            },
            f,
            indent=2,
        )

    return grouped, csv_path, json_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Extract and group ESXi VIBs from an HPE SPP by OS release."
    )
    ap.add_argument("--spp", required=True,
                    help="Path to the extracted/mounted SPP directory.")
    ap.add_argument("--out", required=True,
                    help="Output directory for grouped VIBs + manifest.")
    ap.add_argument("--release", default=None,
                    help="Only output this ESXi release (e.g. 9.0). "
                         "Manifest still covers everything found.")
    ap.add_argument("--link", action="store_true",
                    help="Hardlink instead of copy (faster, no extra disk). "
                         "Requires output on the same filesystem as the SPP.")
    ap.add_argument("--manifest-only", action="store_true",
                    help="Only write the CSV/JSON manifest; don't copy files.")
    ap.add_argument("--workdir", default=None,
                    help="Scratch dir for unwrapping smart components "
                         "(default: <out>/.work).")
    args = ap.parse_args()

    if not os.path.isdir(args.spp):
        print(f"Error: SPP path '{args.spp}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    workdir = args.workdir or os.path.join(args.out, ".work")
    os.makedirs(workdir, exist_ok=True)

    print(f"Scanning SPP: {args.spp}")
    print("(reading VIB descriptors -- this can take a minute on a full SPP)\n")

    records = scan_spp(args.spp, workdir)

    if not records:
        print("No ESXi VIBs found. Is this an extracted SPP directory?",
              file=sys.stderr)
        print("Tip: point --spp at the directory where you extracted the SPP "
              "ISO/zip, not the ISO file itself.", file=sys.stderr)
        sys.exit(2)

    grouped, csv_path, json_path = write_outputs(
        records, args.out,
        release_filter=args.release,
        link=args.link,
        manifest_only=args.manifest_only,
    )

    # Clean up scratch
    shutil.rmtree(workdir, ignore_errors=True)

    print("=== ESXi VIBs found, grouped by release ===")
    for rel in sorted(grouped):
        marker = ""
        if args.release and rel != args.release:
            marker = "  (manifest only -- not copied, --release filter)"
        print(f"  ESXi {rel}: {len(grouped[rel])} VIBs{marker}")

    print()
    print(f"Manifest (CSV) : {csv_path}")
    print(f"Manifest (JSON): {json_path}")
    if not args.manifest_only:
        target = f"esxi-{args.release}" if args.release else "esxi-<release>"
        print(f"Grouped VIBs   : {os.path.join(args.out, target)}/")
        print()
        print("Next: feed the grouped folder into PowerCLI Image Builder.")
        print("See the companion repo: esxi-hpe-synergy-imagebuilder")

    # Flag anything we couldn't classify -- honesty about the tool's limits
    unknown = grouped.get("unknown", [])
    if unknown:
        print()
        print(f"NOTE: {len(unknown)} VIB(s) had no detectable ESXi release and "
              f"landed in 'esxi-unknown'.")
        print("      Check the manifest 'esx_constraint' column and classify "
              "these manually if needed.")


if __name__ == "__main__":
    main()

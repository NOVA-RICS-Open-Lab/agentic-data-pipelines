"""
save_aas_to_aasx.py
────────────────────────────────────────────────────────────────────────────
Persistent, cumulative export of BaSyx V3 shells into ./aasxs_agent/.

Behaviour
---------
1. FIRST RUN (aasxs_agent/ does not exist yet)
   → Copy every .aasx from ./aasxs/ into ./aasxs_agent/ as the baseline.
   → Then fetch all shells from BaSyx and upsert them on top.

2. SUBSEQUENT RUNS (aasxs_agent/ already exists)
   → Fetch all shells from BaSyx.
   → For each shell: write/overwrite its .aasx in aasxs_agent/.
   → Files for shells that no longer exist on the server are LEFT ALONE.
   → Files that were never touched by the agent are LEFT ALONE.

Rule: nothing is ever deleted from aasxs_agent/.

Usage
-----
    python save_aas_to_aasx.py [--url http://localhost:5001]
                                [--source ./aasxs]
                                [--out ./aasxs_agent]

Only requires: requests  (already in your stack)
────────────────────────────────────────────────────────────────────────────
"""

import argparse
import base64
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import requests

from src.config import Config

# ── BaSyx REST helpers ───────────────────────────────────────────────────────

def get_json(base_url: str, path: str) -> dict | list:
    url = f"{base_url}{path}"
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_all_shells(base_url: str) -> list[dict]:
    data = get_json(base_url, "/shells")
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    if isinstance(data, list):
        return data
    raise RuntimeError(f"Unexpected /shells response: {data}")


def encode_id(iri: str) -> str:
    return base64.urlsafe_b64encode(iri.encode()).decode().rstrip("=")


def fetch_submodels_for_shell(base_url: str, shell: dict) -> list[dict]:
    shell_enc = encode_id(shell["id"])
    submodels = []
    for sm_ref in shell.get("submodels", []):
        try:
            sm_id  = sm_ref["keys"][0]["value"]
            sm_enc = encode_id(sm_id)
            try:
                sm = get_json(base_url, f"/shells/{shell_enc}/submodels/{sm_enc}")
            except Exception:
                sm = get_json(base_url, f"/submodels/{sm_enc}")
            submodels.append(sm)
        except Exception as e:
            print(f"    [!] Could not fetch submodel {sm_ref}: {e}")
    return submodels


# ── AASX ZIP builder ─────────────────────────────────────────────────────────

CONTENT_TYPES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="json" ContentType="application/json"/>
  <Override PartName="/aasx/aasx-origin" ContentType="application/aas"/>
</Types>
"""

ROOT_RELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://www.admin-shell.io/aasx/relationships/aasx-origin"
    Target="/aasx/aasx-origin"/>
</Relationships>
"""

AASX_ORIGIN_RELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://www.admin-shell.io/aasx/relationships/aas-spec"
    Target="/aasx/data/aas-env.json"/>
</Relationships>
"""


def build_env(shell: dict, submodels: list[dict]) -> dict:
    clean_shell = {k: v for k, v in shell.items() if k != "submodels_content"}
    return {
        "assetAdministrationShells": [clean_shell],
        "submodels": submodels,
        "conceptDescriptions": [],
    }


def write_aasx(env: dict, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("aasx/aasx-origin", "")
        zf.writestr("aasx/_rels/aasx-origin.rels", AASX_ORIGIN_RELS)
        zf.writestr(
            "aasx/data/aas-env.json",
            json.dumps(env, indent=2, ensure_ascii=False),
        )


def safe_filename(name: str) -> str:
    name = name.rstrip("/").split("/")[-1]
    name = re.sub(r"[^\w\-.]", "_", name)
    return name or "unnamed"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Persistently sync BaSyx V3 shells into aasxs/ without ever deleting files."
    )
    parser.add_argument("--url",    default=Config.AAS_BASE_URL)
    parser.add_argument("--source", default=Config.AASX_SOURCE_DIR)
    parser.add_argument("--out",    default=Config.AASX_AGENT_DIR)
    args = parser.parse_args()

    base_url   = args.url.rstrip("/")
    source_dir = Path(args.source)
    out_dir    = Path(args.out)

    #Step 1: bootstrap from source folder on very first run
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
        if source_dir.exists():
            copied = 0
            for f in source_dir.glob("*.aasx"):
                dest = out_dir / f.name
                shutil.copy2(f, dest)
                copied += 1
            if copied:
                print(f"[*] First run — copied {copied} baseline file(s) from {source_dir}/ → {out_dir}/")
            else:
                print(f"[*] First run — {source_dir}/ has no .aasx files yet, starting fresh.")
        else:
            print(f"[*] First run — source folder {source_dir}/ not found, starting fresh.")
    else:
        print(f"[*] {out_dir}/ already exists — upsert mode (no files will be deleted).")

    #Step 2: fetch current server state
    print(f"[*] Connecting to BaSyx at {base_url} ...")
    try:
        shells = fetch_all_shells(base_url)
    except Exception as e:
        print(f"[!] Failed to fetch shells: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Found {len(shells)} shell(s) on server.")

    #Step 3: upsert — write/overwrite only shells that exist on server
    saved = 0
    for shell in shells:
        shell_id = shell.get("id", "")
        id_short = shell.get("idShort") or safe_filename(shell_id)
        filename = f"{safe_filename(id_short)}.aasx"
        out_path = out_dir / filename

        action = "updated" if out_path.exists() else "created"

        print(f"\n  Shell : {id_short}  [{action}]")
        print(f"  ID    : {shell_id}")

        submodels = fetch_submodels_for_shell(base_url, shell)
        print(f"  SMs   : {len(submodels)} submodel(s)")

        env = build_env(shell, submodels)

        try:
            write_aasx(env, out_path)
            size_kb = out_path.stat().st_size / 1024
            print(f"  Saved : {out_path}  ({size_kb:.1f} KB)")
            saved += 1
        except Exception as e:
            print(f"  [!] Failed to write {out_path}: {e}", file=sys.stderr)

    print(f"\n[✓] Done — {saved}/{len(shells)} shells saved to {out_dir}/")
    print(f"    (other files in {out_dir}/ were not touched)")


if __name__ == "__main__":
    main()
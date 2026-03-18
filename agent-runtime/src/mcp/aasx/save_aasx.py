"""
save_aasx.py
────────────────────────────────────────────────────────────────────────────
Persist a single BaSyx V3 shell to the local aasxs/ folder as a valid
AAS V3 XML .aasx package — matching the format this BaSyx image expects.

Rules
-----
- Receives one shell ID (--shell-id).
- If a .aasx already contains that shell ID → exit immediately. Existing
  files are never touched (they are used for data pipelines).
- If no file exists → fetch from BaSyx, write <idShort>.aasx in AAS V3 XML.
- Does NOT restart the server. That is the caller's responsibility.

Usage
-----
    python save_aasx.py --shell-id "https://example.com/ids/aas/1234_5678_9012_3456"
                        [--url http://localhost:5001]
                        [--out ./aasxs]
────────────────────────────────────────────────────────────────────────────
"""

import argparse
import base64
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from src.config.config import Config


DEFAULT_AAS_BASE_URL = Config.AAS_BASE_URL
DEFAULT_OUT_DIR      = "./aasxs"
AAS_NS               = "https://admin-shell.io/aas/3/0"

# BaSyx REST helpers 

def encode_id(iri: str) -> str:
    return base64.urlsafe_b64encode(iri.encode()).decode().rstrip("=")


def get_json(base_url: str, path: str) -> dict | list:
    url = f"{base_url}{path}"
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_shell(base_url: str, shell_id: str) -> dict:
    return get_json(base_url, f"/shells/{encode_id(shell_id)}")


def fetch_submodels(base_url: str, shell: dict) -> list[dict]:
    shell_enc = encode_id(shell["id"])
    submodels = []
    for ref in shell.get("submodels", []):
        try:
            sm_id  = ref["keys"][0]["value"]
            sm_enc = encode_id(sm_id)
            try:
                sm = get_json(base_url, f"/shells/{shell_enc}/submodels/{sm_enc}")
            except Exception:
                sm = get_json(base_url, f"/submodels/{sm_enc}")
            submodels.append(sm)
        except Exception as e:
            print(f"  [!] Could not fetch submodel {ref}: {e}", file=sys.stderr)
    return submodels




def shell_already_on_disk(folder: Path, shell_id: str) -> Path | None:
    """Return path of existing .aasx for this shell ID, or None."""
    for aasx_path in folder.glob("*.aasx"):
        try:
            with zipfile.ZipFile(aasx_path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith(".aas.xml"):
                        content = zf.read(name).decode("utf-8", errors="ignore")
                        if shell_id in content:
                            return aasx_path
        except Exception:
            pass
    return None


# AAS V3 XML builder 

def _ns(tag: str) -> str:
    return f"{{{AAS_NS}}}{tag}"


def _sub(parent, tag: str, text: str = None) -> ET.Element:
    e = ET.SubElement(parent, _ns(tag))
    if text is not None:
        e.text = text
    return e


def _write_reference(parent: ET.Element, ref: dict) -> None:
    _sub(parent, "type", ref.get("type", "ModelReference"))
    keys_elem = _sub(parent, "keys")
    for key in ref.get("keys", []):
        key_elem = _sub(keys_elem, "key")
        _sub(key_elem, "type", key.get("type", "Submodel"))
        _sub(key_elem, "value", key.get("value", ""))


def _write_lang_strings(parent: ET.Element, items: list, tag: str) -> None:
    for ls in items:
        e = ET.SubElement(parent, _ns(tag))
        e.set("language", ls.get("language", "en"))
        e.text = ls.get("text", "")


def _write_common_attrs(elem: ET.Element, sme: dict) -> None:
    """Write idShort, category, description, semanticId common to all SMEs."""
    if sme.get("category"):
        _sub(elem, "category", sme["category"])
    if sme.get("idShort"):
        _sub(elem, "idShort", sme["idShort"])
    if sme.get("displayName"):
        dn = _sub(elem, "displayName")
        _write_lang_strings(dn, sme["displayName"], "langStringNameType")
    if sme.get("description"):
        desc = _sub(elem, "description")
        _write_lang_strings(desc, sme["description"], "langStringTextType")
    if sme.get("semanticId"):
        sem = _sub(elem, "semanticId")
        _write_reference(sem, sme["semanticId"])
    if sme.get("supplementalSemanticIds"):
        sup = _sub(elem, "supplementalSemanticIds")
        for ref in sme["supplementalSemanticIds"]:
            ref_elem = _sub(sup, "reference")
            _write_reference(ref_elem, ref)
    if sme.get("qualifiers"):
        quals = _sub(elem, "qualifiers")
        for q in sme["qualifiers"]:
            q_elem = _sub(quals, "qualifier")
            if q.get("kind"):
                _sub(q_elem, "kind", q["kind"])
            if q.get("type"):
                _sub(q_elem, "type", q["type"])
            if q.get("valueType"):
                _sub(q_elem, "valueType", q["valueType"])
            if q.get("value") is not None:
                _sub(q_elem, "value", str(q["value"]))


def _model_type_to_tag(model_type: str) -> str:
    if not model_type:
        return "property"
    return model_type[0].lower() + model_type[1:]


def _write_sme(parent: ET.Element, sme: dict) -> None:
    """Recursively write a submodel element to XML."""
    model_type = sme.get("modelType", "Property")
    tag        = _model_type_to_tag(model_type)
    elem       = ET.SubElement(parent, _ns(tag))

    _write_common_attrs(elem, sme)

    if model_type == "Property":
        if sme.get("valueType"):
            _sub(elem, "valueType", sme["valueType"])
        if sme.get("value") is not None:
            _sub(elem, "value", str(sme["value"]))
        if sme.get("valueId"):
            vid = _sub(elem, "valueId")
            _write_reference(vid, sme["valueId"])

    elif model_type == "MultiLanguageProperty":
        if sme.get("value"):
            val = _sub(elem, "value")
            _write_lang_strings(val, sme["value"], "langStringTextType")
        if sme.get("valueId"):
            vid = _sub(elem, "valueId")
            _write_reference(vid, sme["valueId"])

    elif model_type == "SubmodelElementCollection":
        if sme.get("value"):
            val = _sub(elem, "value")
            for child in sme["value"]:
                _write_sme(val, child)

    elif model_type == "SubmodelElementList":
        if sme.get("orderRelevant") is not None:
            _sub(elem, "orderRelevant", str(sme["orderRelevant"]).lower())
        if sme.get("semanticIdListElement"):
            s = _sub(elem, "semanticIdListElement")
            _write_reference(s, sme["semanticIdListElement"])
        if sme.get("typeValueListElement"):
            _sub(elem, "typeValueListElement", sme["typeValueListElement"])
        if sme.get("valueTypeListElement"):
            _sub(elem, "valueTypeListElement", sme["valueTypeListElement"])
        if sme.get("value"):
            val = _sub(elem, "value")
            for child in sme["value"]:
                _write_sme(val, child)

    elif model_type == "File":
        if sme.get("contentType"):
            _sub(elem, "contentType", sme["contentType"])
        if sme.get("value") is not None:
            _sub(elem, "value", sme["value"])

    elif model_type == "Blob":
        if sme.get("contentType"):
            _sub(elem, "contentType", sme["contentType"])
        if sme.get("value") is not None:
            _sub(elem, "value", sme["value"])

    elif model_type == "ReferenceElement":
        if sme.get("value"):
            val = _sub(elem, "value")
            _write_reference(val, sme["value"])

    elif model_type == "Range":
        if sme.get("valueType"):
            _sub(elem, "valueType", sme["valueType"])
        if sme.get("min") is not None:
            _sub(elem, "min", str(sme["min"]))
        if sme.get("max") is not None:
            _sub(elem, "max", str(sme["max"]))

    elif model_type == "RelationshipElement":
        if sme.get("first"):
            first = _sub(elem, "first")
            _write_reference(first, sme["first"])
        if sme.get("second"):
            second = _sub(elem, "second")
            _write_reference(second, sme["second"])

    elif model_type == "AnnotatedRelationshipElement":
        if sme.get("first"):
            first = _sub(elem, "first")
            _write_reference(first, sme["first"])
        if sme.get("second"):
            second = _sub(elem, "second")
            _write_reference(second, sme["second"])
        if sme.get("annotations"):
            anns = _sub(elem, "annotations")
            for ann in sme["annotations"]:
                _write_sme(anns, ann)

    elif model_type == "Operation":
        for field, xml_tag in [
            ("inputVariables",    "inputVariables"),
            ("outputVariables",   "outputVariables"),
            ("inoutputVariables", "inoutputVariables"),
        ]:
            if sme.get(field):
                vars_elem = _sub(elem, xml_tag)
                for var in sme[field]:
                    ov = _sub(vars_elem, "operationVariable")
                    if var.get("value"):
                        val = _sub(ov, "value")
                        _write_sme(val, var["value"])

    elif model_type == "BasicEventElement":
        if sme.get("observed"):
            obs = _sub(elem, "observed")
            _write_reference(obs, sme["observed"])
        for f in ("direction", "state", "messageTopic", "minInterval", "maxInterval"):
            if sme.get(f):
                _sub(elem, f, str(sme[f]))

    elif model_type == "Entity":
        if sme.get("entityType"):
            _sub(elem, "entityType", sme["entityType"])
        if sme.get("statements"):
            stmts = _sub(elem, "statements")
            for s in sme["statements"]:
                _write_sme(stmts, s)
        if sme.get("globalAssetId"):
            _sub(elem, "globalAssetId", sme["globalAssetId"])


def _write_submodel(sm_elem: ET.Element, sm: dict) -> None:
    clean = {k: v for k, v in sm.items() if k != "submodels_content"}

    if clean.get("category"):
        _sub(sm_elem, "category", clean["category"])
    if clean.get("idShort"):
        _sub(sm_elem, "idShort", clean["idShort"])
    if clean.get("description"):
        desc = _sub(sm_elem, "description")
        _write_lang_strings(desc, clean["description"], "langStringTextType")
    if clean.get("administration"):
        adm = clean["administration"]
        adm_elem = _sub(sm_elem, "administration")
        if adm.get("version"):
            _sub(adm_elem, "version", adm["version"])
        if adm.get("revision"):
            _sub(adm_elem, "revision", adm["revision"])
    if clean.get("id"):
        _sub(sm_elem, "id", clean["id"])
    if clean.get("kind"):
        _sub(sm_elem, "kind", clean["kind"])
    if clean.get("semanticId"):
        sem = _sub(sm_elem, "semanticId")
        _write_reference(sem, clean["semanticId"])
    if clean.get("qualifiers"):
        quals = _sub(sm_elem, "qualifiers")
        for q in clean["qualifiers"]:
            q_elem = _sub(quals, "qualifier")
            if q.get("type"):
                _sub(q_elem, "type", q["type"])
            if q.get("valueType"):
                _sub(q_elem, "valueType", q["valueType"])
            if q.get("value") is not None:
                _sub(q_elem, "value", str(q["value"]))
    if clean.get("submodelElements"):
        smes = _sub(sm_elem, "submodelElements")
        for sme in clean["submodelElements"]:
            _write_sme(smes, sme)


def build_aas_xml(shell: dict, submodels: list[dict]) -> str:
    """Convert BaSyx JSON shell + submodels to AAS V3 XML string."""
    ET.register_namespace("", AAS_NS)
    root = ET.Element(_ns("environment"))

    
    shells_elem = _sub(root, "assetAdministrationShells")
    shell_elem  = _sub(shells_elem, "assetAdministrationShell")

    clean_shell = {k: v for k, v in shell.items() if k != "submodels_content"}

    if clean_shell.get("idShort"):
        _sub(shell_elem, "idShort", clean_shell["idShort"])
    if clean_shell.get("id"):
        _sub(shell_elem, "id", clean_shell["id"])

    asset_info = clean_shell.get("assetInformation", {})
    if asset_info:
        ai = _sub(shell_elem, "assetInformation")
        _sub(ai, "assetKind", asset_info.get("assetKind", "Instance"))
        if asset_info.get("globalAssetId"):
            _sub(ai, "globalAssetId", asset_info["globalAssetId"])
        

    sm_refs = clean_shell.get("submodels", [])
    if sm_refs:
        sms_elem = _sub(shell_elem, "submodels")
        for ref in sm_refs:
            ref_elem = _sub(sms_elem, "reference")
            _write_reference(ref_elem, ref)

    
    if submodels:
        sms_root = _sub(root, "submodels")
        for sm in submodels:
            sm_elem = _sub(sms_root, "submodel")
            _write_submodel(sm_elem, sm)

    
    ET.indent(root, space="  ")
    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue().decode("utf-8")


# AASX ZIP writer 

_CONTENT_TYPES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/aasx/aasx-origin" ContentType="application/aas"/>
</Types>
"""

_ROOT_RELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://www.admin-shell.io/aasx/relationships/aasx-origin"
    Target="/aasx/aasx-origin"/>
</Relationships>
"""


def _aasx_origin_rels(id_short: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://www.admin-shell.io/aasx/relationships/aas-spec"
    Target="/aasx/{id_short}/{id_short}.aas.xml"/>
</Relationships>
"""


def write_aasx(xml_content: str, id_short: str, output_path: Path) -> None:
    """Atomic write: .tmp → rename."""
    tmp = output_path.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("aasx/aasx-origin",            "")
            zf.writestr("_rels/.rels",                  _ROOT_RELS)
            zf.writestr("aasx/_rels/aasx-origin.rels",  _aasx_origin_rels(id_short))
            zf.writestr(f"aasx/{id_short}/{id_short}.aas.xml", xml_content)
            zf.writestr("[Content_Types].xml",           _CONTENT_TYPES_XML)
        tmp.replace(output_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise




def safe_filename(name: str) -> str:
    name = name.rstrip("/").split("/")[-1]
    return re.sub(r"[^\w\-.]", "_", name) or "unnamed"




def main() -> None:
    parser = argparse.ArgumentParser(description="Persist a new BaSyx shell to aasxs/ as AAS V3 XML.")
    parser.add_argument("--shell-id", required=True, help="Full shell IRI")
    parser.add_argument("--url", default=DEFAULT_AAS_BASE_URL)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    out_dir  = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    shell_id = args.shell_id

    # 1. already on disk?
    existing = shell_already_on_disk(out_dir, shell_id)
    if existing:
        print(f" Shell already on disk: {existing.name} — nothing to do.")
        sys.exit(0)

    # 2. Fetch from BaSyx 
    print(f" Fetching shell: {shell_id}")
    try:
        shell = fetch_shell(base_url, shell_id)
    except requests.HTTPError as e:
        print(f" Shell not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f" Could not connect to {base_url}: {e}", file=sys.stderr)
        sys.exit(1)

    id_short       = shell.get("idShort") or safe_filename(shell_id)
    safe_id_short  = safe_filename(id_short)
    print(f"    idShort : {id_short}")

    print(f" Fetching submodels...")
    submodels = fetch_submodels(base_url, shell)
    print(f"    Found   : {len(submodels)} submodel(s)")

    #  3. Build XML 
    print(f" Building AAS V3 XML...")
    xml_content = build_aas_xml(shell, submodels)

    # 4. Write .aasx 
    out_path = out_dir / f"{safe_id_short}.aasx"
    print(f" Writing {out_path.name} ...")
    try:
        write_aasx(xml_content, safe_id_short, out_path)
    except Exception as e:
        print(f"Write failed: {e}", file=sys.stderr)
        sys.exit(1)

    size_kb = out_path.stat().st_size / 1024
    print(f"Saved {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
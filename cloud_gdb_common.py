"""Read-only File GDB inspection through GDAL/OGR. No ArcGIS dependency."""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from osgeo import gdal, ogr

gdal.UseExceptions()
ogr.UseExceptions()


def open_gdb(path):
    ds = gdal.OpenEx(str(path), gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=["OpenFileGDB"])
    if ds is None:
        raise ValueError("GDAL could not open this File GDB. Upload the complete .gdb folder as a ZIP.")
    return ds


def local_tag(node):
    return node.tag.rsplit("}", 1)[-1]


def child_text(node, name, default=""):
    return next((c.text or "" for c in list(node) if local_tag(c) == name), default)


def parse_definition(xml):
    if len(xml) > 10 * 1024 * 1024:
        raise ValueError("GDB layer metadata exceeds the 10 MB parser limit.")
    root = ET.fromstring(xml)
    catalog = next((n.text or "" for n in root.iter() if local_tag(n) == "CatalogPath"), "")
    subtype_field = next((n.text or "" for n in root.iter() if local_tag(n) == "SubtypeFieldName"), "")
    default_subtype = next((n.text for n in root.iter() if local_tag(n) == "DefaultSubtypeCode"), None)
    has_oid64 = any(local_tag(n) == "HasOID64" and (n.text or "").lower() == "true" for n in root.iter())
    fields = {}
    for node in root.iter():
        if local_tag(node) not in {"Field", "GPFieldInfoEx"}:
            continue
        name = child_text(node, "Name")
        if not name:
            continue
        fields[name.lower()] = {"name": name, "type": child_text(node, "FieldType") or child_text(node, "Type"),
                               "domain": child_text(node, "DomainName"), "alias": child_text(node, "AliasName"),
                               "nullable": child_text(node, "IsNullable", "true").lower() == "true",
                               "length": child_text(node, "Length")}
    subtypes = {}
    for node in root.iter():
        if local_tag(node) != "Subtype":
            continue
        code = child_text(node, "SubtypeCode")
        if code == "":
            continue
        overrides = {}
        for info in node.iter():
            if local_tag(info) == "SubtypeFieldInfo":
                name = child_text(info, "FieldName")
                if name:
                    overrides[name.lower()] = child_text(info, "DomainName")
        subtypes[code] = {"name": child_text(node, "SubtypeName"), "domains": overrides}
    return {"catalog": catalog, "fields": fields, "subtype_field": subtype_field,
            "default_subtype": default_subtype, "subtypes": subtypes, "has_oid64": has_oid64}


def layer_definition(ds, layer):
    name = layer.GetName()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("Layer XML lookup requires a standard ArcGIS layer name: " + name)
    result = ds.ExecuteSQL("GetLayerDefinition " + name)
    if result is None:
        raise ValueError("The GDB driver did not return layer-definition XML.")
    try:
        feature = result.GetNextFeature()
        if feature is None or not feature.GetField(0):
            raise ValueError("The GDB layer-definition XML is empty.")
        return parse_definition(feature.GetField(0))
    finally:
        ds.ReleaseResultSet(result)


def layer_fields(layer, metadata=None):
    definition = layer.GetLayerDefn()
    fields = []
    for i in range(definition.GetFieldCount()):
        field = definition.GetFieldDefn(i)
        name = field.GetName()
        xml_field = (metadata or {}).get("fields", {}).get(name.lower(), {})
        esri_type = xml_field.get("type", "")
        if field.GetType() == ogr.OFTBinary or esri_type in {"esriFieldTypeOID", "esriFieldTypeGeometry", "esriFieldTypeGlobalID", "esriFieldTypeBlob", "esriFieldTypeRaster"}:
            continue
        fields.append({"index": i, "name": name, "alias": xml_field.get("alias") or name,
                       "type": esri_type or ogr.GetFieldTypeName(field.GetType()) + ":" + ogr.GetFieldSubTypeName(field.GetSubType()),
                       "ogr_type": field.GetType(), "length": field.GetWidth(),
                       "nullable": bool(field.IsNullable()),
                       "domain": xml_field["domain"] if "domain" in xml_field else (field.GetDomainName() or "")})
    return fields


def inventory(path):
    ds = open_gdb(path)
    rows = []
    for index in range(ds.GetLayerCount()):
        layer = ds.GetLayerByIndex(index)
        if layer.GetGeomType() == ogr.wkbNone:
            continue  # Nonspatial/relationship tables are outside this first QC scope.
        metadata_error = None
        try:
            metadata = layer_definition(ds, layer)
        except Exception as exc:
            metadata = {}
            metadata_error = str(exc)
        if metadata.get("has_oid64") and int(gdal.VersionInfo("VERSION_NUM")) < 3100000:
            raise ValueError("This GDB uses 64-bit OBJECTIDs. Deploy GDAL 3.10+ and validate its OID support before QC.")
        relative = metadata.get("catalog", "").replace("\\", "/").strip("/") or layer.GetName()
        sr = layer.GetSpatialRef()
        geom_type = layer.GetGeomType()
        rows.append({"path": relative, "name": layer.GetName(), "dataset": relative.rsplit("/", 1)[0] if "/" in relative else "",
                     "geometry": ogr.GeometryTypeToName(ogr.GT_Flatten(geom_type)),
                     "count": layer.GetFeatureCount(), "crs": sr.GetName() if sr else "Unknown",
                     "epsg": sr.GetAuthorityCode(None) if sr else None,
                     "has_z": bool(ogr.GT_HasZ(geom_type)), "has_m": bool(ogr.GT_HasM(geom_type)),
                     "fields": [{k: v for k, v in f.items() if k != "index"} for f in layer_fields(layer, metadata)],
                     "metadata_warning": metadata_error})
    ds = None
    if len({r["path"].lower() for r in rows}) != len(rows):
        raise ValueError("Ambiguous layer paths in this GDB. Resolve its dataset metadata before running QC.")
    return sorted(rows, key=lambda r: r["path"].lower())


def resolve_schema(source, candidates):
    exact = [r for r in candidates if r["path"].lower() == source["path"].lower()]
    if len(exact) == 1:
        return exact[0]
    same_name = [r for r in candidates if r["name"].lower() == source["name"].lower()]
    if len(same_name) > 1:
        raise ValueError("Ambiguous schema class: " + source["path"])
    return same_name[0] if same_name else None

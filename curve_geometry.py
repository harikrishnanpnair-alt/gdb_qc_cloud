"""Curve checks without changing source data or hashing a densified approximation."""
from __future__ import annotations
import hashlib
import json
import math
from osgeo import ogr
import shapely

ARC_STEP_DEGREES = 0.25
MAX_LINEAR_POINTS = 250000


def minimum_rotation(sequence):
    """Booth's algorithm: smallest cyclic rotation in linear time."""
    values = tuple(sequence)
    n = len(values)
    if n < 2:
        return values
    twice = values + values
    i, j, k = 0, 1, 0
    while i < n and j < n and k < n:
        a, b = twice[i + k], twice[j + k]
        if a == b:
            k += 1
            continue
        if a > b:
            i += k + 1
            if i <= j:
                i = j + 1
        else:
            j += k + 1
            if j <= i:
                j = i + 1
        k = 0
    start = min(i, j)
    return twice[start:start + n]


def coordinates(geometry, index):
    point = geometry.GetPointZM(index)
    values = [point[0], point[1]]
    if geometry.Is3D():
        values.append(point[2])
    if geometry.IsMeasured():
        values.append(point[3])
    if not math.isfinite(point[0]) or not math.isfinite(point[1]):
        raise ValueError("Curve contains non-finite XY coordinates.")
    # Exact floating values, including Z/M. Normalize signed zero, not precision.
    return tuple((0.0 if value == 0 else float(value)).hex() for value in values)


def curve_edges(geometry):
    name = geometry.GetGeometryName().upper()
    if name == "COMPOUNDCURVE":
        edges = []
        for index in range(geometry.GetGeometryCount()):
            edges.extend(curve_edges(geometry.GetGeometryRef(index)))
        return edges
    if name not in {"LINESTRING", "LINEARRING", "CIRCULARSTRING"}:
        raise ValueError("Unsupported curve path type: " + name)
    points = [coordinates(geometry, index) for index in range(geometry.GetPointCount())]
    if name == "CIRCULARSTRING":
        if len(points) < 3 or len(points) % 2 != 1:
            raise ValueError("Invalid circular string control-point count.")
        return [("ARC", points[index], points[index + 1], points[index + 2]) for index in range(0, len(points) - 2, 2)]
    if len(points) < 2:
        raise ValueError("Nonempty curve path has fewer than two points.")
    return [("LINE", points[index], points[index + 1]) for index in range(len(points) - 1)]


def canonical_path(geometry):
    edges = tuple(curve_edges(geometry))
    if not edges:
        raise ValueError("Nonempty compound curve has no segments.")
    reversed_edges = tuple((edge[0], *reversed(edge[1:])) for edge in reversed(edges))
    closed = edges[0][1] == edges[-1][-1]
    if closed:
        edges, reversed_edges = minimum_rotation(edges), minimum_rotation(reversed_edges)
    return ("PATH", bool(geometry.Is3D()), bool(geometry.IsMeasured()), closed, min(edges, reversed_edges))


def canonical_curve(geometry):
    name = geometry.GetGeometryName().upper()
    dimensions = (bool(geometry.Is3D()), bool(geometry.IsMeasured()))
    if geometry.IsEmpty():
        return (name, dimensions, "EMPTY")
    if name in {"LINESTRING", "LINEARRING", "CIRCULARSTRING", "COMPOUNDCURVE"}:
        return canonical_path(geometry)
    if name in {"POLYGON", "CURVEPOLYGON"}:
        rings = [canonical_path(geometry.GetGeometryRef(index)) for index in range(geometry.GetGeometryCount())]
        if not rings:
            raise ValueError("Nonempty curve polygon has no rings.")
        return ("SURFACE", dimensions, rings[0], tuple(sorted(rings[1:])))
    families = {"MULTILINESTRING": "MULTIPATH", "MULTICURVE": "MULTIPATH", "MULTIPOLYGON": "MULTISURFACE",
                "MULTISURFACE": "MULTISURFACE", "GEOMETRYCOLLECTION": "COLLECTION", "MULTIPOINT": "MULTIPOINT"}
    if name in families:
        parts = [canonical_curve(geometry.GetGeometryRef(index)) for index in range(geometry.GetGeometryCount())]
        return (families[name], dimensions, tuple(sorted(parts)))
    if name == "POINT":
        return (name, dimensions, coordinates(geometry, 0))
    raise ValueError("Unsupported native curve container: " + name)


def curve_digest(geometry):
    # Linear features keep their existing normalized Shapely WKB rule. Curved
    # features use native arc/line control records, never a flattened shape.
    representation = json.dumps(canonical_curve(geometry), separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(b"native-curve-v1:" + representation).digest()


def point_count(geometry):
    children = geometry.GetGeometryCount()
    if children:
        return sum(point_count(geometry.GetGeometryRef(index)) for index in range(children))
    return geometry.GetPointCount()


def shape_for_length(geometry):
    """A private XY-only approximation for measuring curved features."""
    if geometry.HasCurveGeometry():
        linear = geometry.GetLinearGeometry(ARC_STEP_DEGREES, ["ADD_INTERMEDIATE_POINT=YES"])
        if linear is None or linear.HasCurveGeometry():
            raise ValueError("GDAL could not construct the curve length approximation.")
    else:
        linear = geometry.Clone()
    if point_count(linear) > MAX_LINEAR_POINTS:
        raise ValueError("Curve length approximation exceeds the per-feature point limit.")
    linear.FlattenTo2D()
    return shapely.from_wkb(bytes(linear.ExportToIsoWkb()))

"""Minimal deterministic glTF 2.0 (GLB) writer for baked chunks: positions, normals, vertex colours, indices, materials."""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Mesh:
    name: str
    material: str
    positions: np.ndarray  # (n,3) float32, glTF Y-up
    indices: np.ndarray    # (m,) uint32
    normals: np.ndarray | None = None
    colors: np.ndarray | None = None  # (n,3) float in 0..1 (baked AO etc.)
    extras: dict = field(default_factory=dict)


def compute_normals(pos: np.ndarray, idx: np.ndarray) -> np.ndarray:
    tri = idx.reshape(-1, 3)
    a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    fn = np.cross(b - a, c - a)
    n = np.zeros_like(pos, dtype=np.float64)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return (n / ln).astype(np.float32)


def enu_to_gltf(x, y, z) -> np.ndarray:
    """ENU (x east, y north, z up) → glTF (X right, Y up, Z toward viewer): (x, z, -y)."""
    return np.c_[x, z, -np.asarray(y)].astype(np.float32)


def write_glb(meshes: list[Mesh], materials: dict[str, dict], extras: dict | None = None) -> bytes:
    buf = bytearray()
    views, accessors, gl_meshes, nodes = [], [], [], []
    mat_index: dict[str, int] = {}
    gl_mats = []

    def add_view(data: bytes, target: int | None) -> int:
        while len(buf) % 4:
            buf.append(0)
        off = len(buf)
        buf.extend(data)
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            v["target"] = target
        views.append(v)
        return len(views) - 1

    def add_acc(arr: np.ndarray, comp: int, typ: str, target: int | None, minmax: bool = False) -> int:
        view = add_view(np.ascontiguousarray(arr).tobytes(), target)
        acc = {"bufferView": view, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        accessors.append(acc)
        return len(accessors) - 1

    for m in meshes:
        if len(m.indices) == 0:
            continue
        if m.material not in mat_index:
            spec = materials.get(m.material, {"baseColor": [0.6, 0.6, 0.6], "roughness": 0.9, "metallic": 0.0})
            mat_index[m.material] = len(gl_mats)
            gl_mats.append({"name": m.material, "pbrMetallicRoughness": {"baseColorFactor": [*spec["baseColor"], 1.0],
                            "metallicFactor": spec.get("metallic", 0.0), "roughnessFactor": spec.get("roughness", 0.9)},
                            "extras": {"materialId": m.material}})
        pos = m.positions.astype(np.float32)
        nrm = m.normals if m.normals is not None else compute_normals(pos, m.indices)
        attrs = {"POSITION": add_acc(pos, 5126, "VEC3", 34962, True), "NORMAL": add_acc(nrm.astype(np.float32), 5126, "VEC3", 34962)}
        if m.colors is not None:
            attrs["COLOR_0"] = add_acc(m.colors.astype(np.float32), 5126, "VEC3", 34962)
        idx = m.indices.astype(np.uint32)
        ia = add_acc(idx.reshape(-1, 1), 5125, "SCALAR", 34963)
        gl_meshes.append({"name": m.name, "primitives": [{"attributes": attrs, "indices": ia, "material": mat_index[m.material]}]})
        nodes.append({"name": m.name, "mesh": len(gl_meshes) - 1, **({"extras": m.extras} if m.extras else {})})
    gltf = {"asset": {"version": "2.0", "generator": "gpx2course"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes, "meshes": gl_meshes, "materials": gl_mats, "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(buf)}]}
    if extras:
        gltf["extras"] = extras
    if not nodes:
        gltf.pop("meshes")
        gltf.pop("accessors")
        gltf.pop("bufferViews")
        gltf["buffers"] = [{"byteLength": 0}]
    js = json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode()
    while len(js) % 4:
        js += b" "
    while len(buf) % 4:
        buf.append(0)
    chunks = struct.pack("<II", len(js), 0x4E4F534A) + js
    if len(buf):
        chunks += struct.pack("<II", len(buf), 0x004E4942) + bytes(buf)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def read_glb_json(data: bytes) -> dict:
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2:
        raise ValueError("not a GLB v2 file")
    jlen, jtype = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + jlen])

"""3D trophies made by Python from our pixel art (owner: A).

Every coloured pixel of a picture in pixel_art.py becomes a little 3D block ("voxel"),
DEPTH blocks thick, so the flat sprite turns into a chunky 3D trophy. Python writes it
as a .glb file: the standard 3D format (glTF 2.0) that phones open in AR and that the
<model-viewer> web component shows on the Collection page.

Only the Python standard library is used (struct, json). To make the files again:

    python voxel_models.py

How a .glb file is built:
  header:  "glTF", version 2, total length
  chunk 1: JSON that describes the model (which bytes are corners, normals, triangles,
           and one coloured material per pixel colour)
  chunk 2: the bytes themselves (BIN)
"""

import json
import re
import struct
from pathlib import Path

from pixel_art import PALETTE, SPRITES

HERE = Path(__file__).parent
PIXEL_CSS = HERE / "static" / "css" / "pixel.css"
OUTPUT_DIR = HERE / "static" / "models"

VOXEL_M = 0.02   # one block is 2 cm, so a 13-pixel trophy is about 26 cm tall in AR
DEPTH = 2        # blocks thick (front to back)

# Which pictures become 3D trophies (name in pixel_art.SPRITES -> file name)
TROPHIES = ["trophy", "coin-spin", "chest-open", "badge", "gold-pin", "explorer", "flag",
            "bubble-tea", "coffee", "map",
            # A: the creatures and trees from the random landscapes (scenery.py) can be collected too
            "cat", "dog", "butterfly", "bird", "sakura", "pine"]

# The six faces of a block: (normal, the 4 corners as offsets from the block's corner)
FACES = [
    ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),    # front
    ((0, 0, -1), [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)]),   # back
    ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),   # left
    ((1, 0, 0), [(1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)]),    # right
    ((0, 1, 0), [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)]),    # top
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),   # bottom
]


def palette_hex(css_text):
    """The colours from pixel.css, e.g. {"--px-ink": "#14231f", ...}."""
    return dict(re.findall(r"(--px-[a-z-]+):\s*(#[0-9a-fA-F]{6})", css_text))


def srgb_to_linear(channel):
    """Screens use sRGB, but glTF colours must be linear light (the standard formula)."""
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def letter_colours(css_text):
    """Each picture letter -> (r, g, b, a) as linear floats for the model."""
    hexes = palette_hex(css_text)
    colours = {}
    for letter, variable in PALETTE.items():
        h = hexes[variable].lstrip("#")
        colours[letter] = tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4)) + (1.0,)
    return colours


def build_mesh(rows, depth=DEPTH, size=VOXEL_M):
    """Turn a picture into blocks, grouped by colour letter.

    Returns {letter: (corners, normals, triangle indices)}. Each colour is kept apart
    because each colour becomes its own material in the .glb (see glb_bytes).
    Only faces you can see are kept: a side face between two filled blocks is hidden,
    so it is skipped (smaller file, cleaner model).
    """
    height, width = len(rows), len(rows[0])

    def filled(x, y, z):
        return 0 <= y < height and 0 <= x < width and 0 <= z < depth and rows[y][x] != "."

    groups = {}
    for y, row in enumerate(rows):
        for x, letter in enumerate(row):
            if letter == ".":
                continue
            positions, normals, indices = groups.setdefault(letter, ([], [], []))
            for z in range(depth):
                for normal, corners in FACES:
                    nx, ny, nz = normal
                    # picture rows go down, but 3D "up" is +y: the neighbour above is row y - 1
                    if filled(x + nx, y - ny, z + nz):
                        continue
                    start = len(positions)
                    for cx, cy, cz in corners:
                        positions.append((
                            (x + cx - width / 2) * size,      # centred left to right
                            (height - 1 - y + cy) * size,     # standing on the floor
                            (z + cz - depth / 2) * size,      # centred front to back
                        ))
                        normals.append(normal)
                    indices += [start, start + 1, start + 2, start, start + 2, start + 3]
    return groups


def _pad(data, filler):
    return data + filler * ((4 - len(data) % 4) % 4)


def glb_bytes(groups, colours, name="StepQuest trophy"):
    """Pack the blocks into a .glb file (glTF 2.0 binary).

    WHY one material per colour: an earlier version stored the colour on every corner
    ("vertex colours") under one white material. The web viewer showed the colours, but
    phone AR (Android Scene Viewer, iPhone Quick Look) ignores vertex colours, so the
    trophy looked plain white. A material colour works in every viewer.
    """
    chunks, views, accessors, primitives, materials = [], [], [], [], []
    offset = 0

    def add_view(data, target):
        nonlocal offset
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        chunks.append(data)
        offset += len(data)  # every part is a multiple of 4 bytes, so no padding is needed
        return len(views) - 1

    all_corners = []
    for letter, (positions, normals, indices) in groups.items():
        all_corners += positions
        xs, ys, zs = zip(*positions)
        pos = add_view(b"".join(struct.pack("<3f", *p) for p in positions), 34962)
        nor = add_view(b"".join(struct.pack("<3f", *n) for n in normals), 34962)
        idx = add_view(struct.pack(f"<{len(indices)}I", *indices), 34963)
        accessors += [
            {"bufferView": pos, "componentType": 5126, "count": len(positions), "type": "VEC3",
             "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]},
            {"bufferView": nor, "componentType": 5126, "count": len(normals), "type": "VEC3"},
            {"bufferView": idx, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ]
        first = len(accessors) - 3
        primitives.append({"attributes": {"POSITION": first, "NORMAL": first + 1},
                           "indices": first + 2, "material": len(materials)})
        materials.append({"name": f"pixel {letter}", "pbrMetallicRoughness": {
            "baseColorFactor": list(colours[letter]), "metallicFactor": 0.0, "roughnessFactor": 0.7}})

    binary = b"".join(chunks)
    gltf = {
        "asset": {"version": "2.0", "generator": "StepQuest voxel_models.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": primitives}],
        "materials": materials,
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    json_chunk = _pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk
            + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)


def trophy_glb(name, css_text=None):
    """The .glb bytes for one trophy (its first animation frame)."""
    css_text = css_text if css_text is not None else PIXEL_CSS.read_text(encoding="utf-8")
    rows = SPRITES[name][0]
    return glb_bytes(build_mesh(rows), letter_colours(css_text), name=f"StepQuest {name}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    css_text = PIXEL_CSS.read_text(encoding="utf-8")
    for name in TROPHIES:
        data = trophy_glb(name, css_text)
        (OUTPUT_DIR / f"{name}.glb").write_bytes(data)
        print(f"{name}.glb  {len(data) // 1024} KB")


if __name__ == "__main__":
    main()

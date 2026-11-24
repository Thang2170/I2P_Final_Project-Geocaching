"""The app icon for "Add to Home screen", drawn from the pixel-art coin (owner: B).

Only the standard library (zlib + struct): a PNG is a short header plus zlib-packed rows.
Run `python app_icon.py` to (re)make static/icons/*.png after changing the coin in pixel_art.py.
"""

import struct
import zlib
from pathlib import Path

from pixel_art import COIN_FULL

OUTPUT = Path(__file__).parent / "static" / "icons"
BACKGROUND = "#17332d"  # --px-green, the top bar
COLOURS = {"o": "#14231f", "g": "#f2a93b", "G": "#ffe08a", "d": "#a85e0c"}  # pixel.css
SIZES = (192, 512)
COIN_SHARE = 0.6  # the coin covers 60% of the icon, so a round "maskable" crop never cuts it


def rgb(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))


def icon_pixels(rows, size, colours=COLOURS, background=BACKGROUND, share=COIN_SHARE):
    """A size x size grid of (r, g, b): the picture scaled up in whole blocks, centred."""
    block = max(1, int(size * share) // max(len(r) for r in rows))
    width, height = block * max(len(r) for r in rows), block * len(rows)
    left, top = (size - width) // 2, (size - height) // 2
    bg = rgb(background)
    grid = [[bg] * size for _ in range(size)]
    for y, row in enumerate(rows):
        for x, letter in enumerate(row):
            if letter not in colours:  # "." is see-through: the background shows
                continue
            colour = rgb(colours[letter])
            for dy in range(block):
                line = grid[top + y * block + dy]
                for dx in range(block):
                    line[left + x * block + dx] = colour
    return grid


def png_bytes(grid):
    """Encode a grid of (r, g, b) as a PNG file."""
    height, width = len(grid), len(grid[0])
    raw = b"".join(b"\x00" + bytes(c for pixel in row for c in pixel) for row in grid)  # filter 0 each row

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB, no interlace
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def icon_files():
    """{file name: PNG bytes} for every size."""
    return {f"icon-{size}.png": png_bytes(icon_pixels(COIN_FULL, size)) for size in SIZES}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, data in icon_files().items():
        (OUTPUT / name).write_bytes(data)
        print(f"wrote static/icons/{name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()

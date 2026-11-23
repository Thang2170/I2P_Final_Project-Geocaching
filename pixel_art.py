"""StepQuest's pixel art, drawn as text and turned into CSS by Python (owner: A).

Every sprite is a small picture made of letters: one letter = one pixel,
"." = see-through. PALETTE says which colour each letter is. Python turns each
picture into CSS box-shadows (one shadow per pixel) and writes static/css/sprites.css.

To change a picture: edit it below, then run

    python pixel_art.py

A sprite with more than one frame (the walking explorer, the spinning coin) gets a
CSS animation that jumps from frame to frame, like an old game.

Use a sprite in HTML like this:  <span class="sprite sprite--explorer"></span>
(pixel.css has the .sprite base rule.)
"""

from pathlib import Path

PIXEL = 3  # each picture pixel is a 3 x 3 screen pixel box
SMALL_PIXEL = 2  # the little marks on map pins use 2 x 2 boxes (see PIXEL_SIZE)
OUTPUT = Path(__file__).parent / "static" / "css" / "sprites.css"

# One letter per colour. The colours themselves live in pixel.css (--px-...).
PALETTE = {
    "o": "--px-ink",          # outline
    "g": "--px-gold",
    "G": "--px-gold-light",
    "d": "--px-gold-dark",
    "l": "--px-leaf",
    "h": "--px-green",
    "R": "--px-grass-light",
    "w": "--px-wood",
    "W": "--px-wood-light",
    "b": "--px-wood-dark",
    "s": "--px-skin",
    "c": "--px-orange",
    "t": "--px-stone",
    "K": "--px-cloud-shade",
    "e": "--px-dirt",
    "a": "--px-water",
    "p": "--px-paper",
    "n": "--px-bad",
}

# ------------------------------------------------------------------ the pictures

EXPLORER_TOP = [
    "......oooo......",
    ".....ollllo.....",
    "....ollllllo....",
    "..oooooooooooo..",
    "....osssssso....",
    "....osossoso....",
    "....osssssso....",
    ".....oooooo.....",
    "..wwoccccccoo...",
    "..wbocccccccos..",
    "..wbocccccco....",
    "..wwoggggggo....",
    "....ohhhhhho....",
]
EXPLORER_LEGS_APART = [
    "...ohho..ohho...",
    "...obbo..obbo...",
    "...oooo..oooo...",
]
EXPLORER_LEGS_TOGETHER = [
    ".....ohhhho.....",
    ".....obbbbo.....",
    ".....oooooo.....",
]

COIN_FULL = [
    "....oooo....",
    "..ooGGGGoo..",
    ".oGGggggddo.",
    ".oGgGggggdo.",
    "oGgGggggggdo",
    "oGgGggggggdo",
    "oGgggggggddo",
    "oGgggggggddo",
    ".oggggggddo.",
    ".odggggdddo.",
    "..ooddddoo..",
    "....oooo....",
]
COIN_TURNING = [
    "....oooo....",
    "...oGGdo....",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oGgggddo..",
    "..oggggddo..",
    "...oddddo...",
    "....oooo....",
]
COIN_EDGE = [
    ".....oo.....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    "....oGdo....",
    ".....oo.....",
]

SPRITES = {
    # name: list of frames (each frame is a list of rows)
    "explorer": [EXPLORER_TOP + EXPLORER_LEGS_APART, EXPLORER_TOP + EXPLORER_LEGS_TOGETHER],
    "coin-spin": [COIN_FULL, COIN_TURNING, COIN_EDGE, COIN_TURNING],
    "chest-open": [[
        "..oooooooooooo..",
        ".obbbbbbbbbbbbo.",
        ".owwwwwwwwwwwwo.",
        ".oGGGGGGGGGGGGo.",
        "oGgGgGGgGgGGgGgo",
        "oooooooooooooooo",
        "owwwwwwddwwwwwwo",
        "oWWWWWodGoWWWWWo",
        "owwwwwoddowwwwwo",
        "owwwwwwoowwwwwwo",
        "obbbbbbbbbbbbbbo",
        "oooooooooooooooo",
    ]],
    "flag": [[
        "oo..........",
        "obooooooooo.",
        "obocccccccco",
        "obocccGcccco",
        "obocccccccco",
        "obooooooooo.",
        "ob..........",
        "ob..........",
        "ob..........",
        "ob..........",
        "ob..........",
        "ob..........",
        "ob..........",
        "otto........",
        "oooo........",
    ]],
    "trophy": [[
        "..ooooooooo..",
        "..oGGgggddo..",
        "oooGgggggdooo",
        "o.oGgggggdo.o",
        "o.oGgggggdo.o",
        ".ooGgggggdoo.",
        "...oGgggdo...",
        "....oggdo....",
        ".....ogo.....",
        ".....odo.....",
        "...ooooooo...",
        "...owwwwwo...",
        "..ooooooooo..",
    ]],
    "badge": [[
        ".oo......oo.",
        ".oao....oao.",
        "..oao..oao..",
        "...oaooao...",
        "....oooo....",
        "..ooGGGgoo..",
        ".oGGggggddo.",
        ".oGggpgggdo.",
        ".oGgpppggdo.",
        ".oGggpgggdo.",
        ".oggggggddo.",
        "..ooddddoo..",
        "....oooo....",
    ]],
    "gold-pin": [[
        "...oooo...",
        ".ooGGGgoo.",
        ".oGGgggdo.",
        "oGGgooggdo",
        "oGgoppogdo",
        "oGgoppogdo",
        "oGgoooogdo",
        ".oggggddo.",
        ".oggggddo.",
        "..ogggdo..",
        "..oggddo..",
        "...oggo...",
        "....oo....",
    ]],
    "bubble-tea": [[
        "......o...",
        ".....o....",
        ".oooooooo.",
        "oppppppppo",
        ".oooooooo.",
        ".oeeeeeeo.",
        ".oeeeeeeo.",
        ".oeeeeeeo.",
        ".oebebbeo.",
        ".obebebbo.",
        "..obbbbo..",
        "..oooooo..",
    ]],
    "coffee": [[
        "...K..K.....",
        "....K..K....",
        ".oooooooo...",
        ".oppppppooo.",
        ".oppppppo.o.",
        ".owwwwwwo.o.",
        ".owwwwwwooo.",
        ".oppppppo...",
        "..oppppo....",
        "..oooooo....",
        "oooooooooo..",
    ]],
    "map": [[
        "oooooooooooooo",
        "oeneeoeeeeoeeo",
        "oeeeeoeeleoeeo",
        "oeeeeoelleoeeo",
        "oeeeeoeeeeoaao",
        "oeeaaoaaeeoaeo",
        "oeaaeoeeeeoeeo",
        "oeeeeoeeeeoeno",
        "oeeeeoeeeeoeeo",
        "oooooooooooooo",
    ]],
    "signal": [[
        ".........RR",
        ".........RR",
        ".........RR",
        "......RR.RR",
        "......RR.RR",
        "......RR.RR",
        "...RR.RR.RR",
        "...RR.RR.RR",
        "...RR.RR.RR",
        "RR.RR.RR.RR",
        "RR.RR.RR.RR",
        "RR.RR.RR.RR",
    ]],
    # Street-crossing warning sign (Feature 7), drawn on the map at each crossing
    "warning": [[
        ".....oo.....",
        "....oGGo....",
        "....oGGo....",
        "...oGGGGo...",
        "...oGooGo...",
        "..oGGooGGo..",
        "..oGGooGGo..",
        ".oGGGooGGGo.",
        ".oGGGGGGGGo.",
        "oGGGGooGGGGo",
        "oGGGGGGGGGGo",
        "oooooooooooo",
    ]],
    # Little marks that sit on a map pin (2 x 2 pixels each, see PIXEL_SIZE)
    "mark-verified": [[
        ".oooooo.",
        "ollllllo",
        "olllllpo",
        "ollllplo",
        "olplpllo",
        "ollplllo",
        "ollllllo",
        ".oooooo.",
    ]],
    "mark-collectible": [[
        "...oo...",
        "..oGgo..",
        ".oGggdo.",
        "oGgggddo",
        "oggggddo",
        ".oggddo.",
        "..oddo..",
        "...oo...",
    ]],
}

FRAME_TIME_S = {"explorer": 0.6, "coin-spin": 0.8}  # one whole animation loop
PIXEL_SIZE = {"mark-verified": SMALL_PIXEL, "mark-collectible": SMALL_PIXEL, "warning": SMALL_PIXEL}  # the rest use PIXEL


# ------------------------------------------------------------------ picture -> CSS


def check_sprite(name, frames):
    """Raise ValueError if a picture is broken: uneven rows, frames of different
    sizes, or a letter that is not in PALETTE."""
    if not frames:
        raise ValueError(f"{name}: no frames")
    width, height = len(frames[0][0]), len(frames[0])
    for number, rows in enumerate(frames, start=1):
        if len(rows) != height:
            raise ValueError(f"{name} frame {number}: {len(rows)} rows, expected {height}")
        for y, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(f"{name} frame {number} row {y}: {len(row)} wide, expected {width}")
            for letter in row:
                if letter != "." and letter not in PALETTE:
                    raise ValueError(f"{name} frame {number} row {y}: unknown colour letter {letter!r}")
    return width, height


def box_shadow(rows, size=PIXEL):
    """One CSS shadow per coloured pixel. The shadow box sits one pixel up-left
    of the sprite (see .sprite::before in pixel.css), hence the + 1."""
    shadows = []
    for y, row in enumerate(rows):
        for x, letter in enumerate(row):
            if letter != ".":
                shadows.append(f"{(x + 1) * size}px {(y + 1) * size}px 0 0 var({PALETTE[letter]})")
    return ",\n    ".join(shadows)


def sprite_css(name, frames):
    """The CSS for one sprite: its size, its first frame, and (if it has more
    frames) an animation that steps through them."""
    width, height = check_sprite(name, frames)
    size = PIXEL_SIZE.get(name, PIXEL)  # most sprites use PIXEL; the little pin marks are smaller
    css = [f".sprite--{name} {{ width: {width * size}px; height: {height * size}px; }}"]
    if size != PIXEL:  # the shadow box must be exactly one picture pixel big
        css.append(f".sprite--{name}::before {{ left: -{size}px; top: -{size}px; "
                   f"width: {size}px; height: {size}px; }}")
    css.append(f".sprite--{name}::before {{\n  box-shadow:\n    {box_shadow(frames[0], size)};")
    if len(frames) == 1:
        css[-1] += "\n}"
        return "\n".join(css)

    seconds = FRAME_TIME_S.get(name, 0.6)
    css[-1] += f"\n  animation: sprite-{name} {seconds}s steps(1) infinite;\n}}"
    keyframes = [f"@keyframes sprite-{name} {{"]
    for number, rows in enumerate(frames):
        percent = round(number * 100 / len(frames), 2)
        keyframes.append(f"  {percent}% {{ box-shadow:\n    {box_shadow(rows, size)}; }}")
    keyframes.append("}")
    css.append("\n".join(keyframes))
    # People who asked their computer for less motion get the first frame only
    css.append("@media (prefers-reduced-motion: reduce) {\n"
               f"  .sprite--{name}::before {{ animation: none; }}\n}}")
    return "\n".join(css)


def build_css():
    """The whole sprites.css file, as text."""
    parts = ["/* sprites.css: MADE BY pixel_art.py. Don't edit this file by hand:\n"
             "   change the picture in pixel_art.py and run  python pixel_art.py  */"]
    for name, frames in SPRITES.items():
        parts.append(sprite_css(name, frames))
    return "\n\n".join(parts) + "\n"


def main():
    OUTPUT.write_text(build_css(), encoding="utf-8")
    print(f"Wrote {len(SPRITES)} sprites to {OUTPUT}")


if __name__ == "__main__":
    main()

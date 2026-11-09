"""Draw each foraging map as the board looks to a player, with the fog removed.

The floor is the cave from static/cave.js (same seed, same tiles, same rock border).
Food is the same 10x10 gem, drawn on every cell that holds a point. The torch
darkness is left off, so the whole board is visible.

    python tools/draw_worlds.py                 # the ten round maps
    python tools/draw_worlds.py --map andrade16_map0
    python tools/draw_worlds.py --all           # every file in static/maps

Writes figures/worlds/<name>.png at 300 dpi. x increases to the right and y
increases downward, as on the board.
"""
import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = ROOT / "static" / "maps"
OUT_DIR = ROOT / "figures" / "worlds"

# static/cave.js draws the floor texture at this many pixels per cell.
GAME_PX = 48
FLOOR_SEED = 12345
BORDER = 0.5  # rock wall around the board, in cells
DPI = 300
# Pixels per cell in the saved image. A multiple of 20 keeps the 10px gem
# on an integer scale inside its half-cell.
CELL_PX = 120

GEM = [
    "...OOOO...",
    "..OLLBBO..",
    ".OLWBBBBO.",
    "OLWBBBBBDO",
    "OLBBBBBBDO",
    "OBBBBBBBDO",
    "OBBBBBBDDO",
    ".OBBBBDDO.",
    "..ODDDDO..",
    "...OOOO...",
]
PALETTE = {
    "O": (0x0D, 0x10, 0x36, 255),
    "L": (0x8F, 0xB4, 0xFF, 255),
    "W": (0xFF, 0xFF, 0xFF, 255),
    "B": (0x2A, 0x50, 0xF0, 255),
    "D": (0x17, 0x28, 0x9A, 255),
}


def rng(seed: int = FLOOR_SEED):
    """Same generator as cave.js: each call is one value in [0, 1)."""

    def rand() -> float:
        nonlocal seed
        seed = (seed * 1664525 + 1013904223) % 4294967296
        return seed / 4294967296

    return rand


def _blend(base: Image.Image, layer: Image.Image, xy: tuple[int, int]) -> None:
    x, y = xy
    region = base.crop((x, y, x + layer.width, y + layer.height))
    base.paste(Image.alpha_composite(region, layer), xy)


def _fill(base: Image.Image, box: tuple[int, int, int, int], color: tuple) -> None:
    layer = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), color)
    _blend(base, layer, (box[0], box[1]))


def floor_texture(grid_size: int) -> Image.Image:
    """Stone tiles and the rock wall, at the resolution cave.js uses."""
    px = GAME_PX
    cells = grid_size + 2 * BORDER
    size = round(cells * px)
    image = Image.new("RGBA", (size, size), (0x3B, 0x2F, 0x25, 255))
    draw = ImageDraw.Draw(image)
    rand = rng()

    for _ in range(int(cells * 6)):
        color = (0x4A, 0x3B, 0x2E, 255) if rand() < 0.5 else (0x2C, 0x23, 0x1B, 255)
        cx, cy = rand() * size, rand() * size
        radius = px * (0.12 + rand() * 0.22)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)

    origin = int(BORDER * px)
    for x in range(grid_size):
        for y in range(grid_size):
            tile = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            shade = 150 + int(rand() * 22)
            ImageDraw.Draw(tile).rectangle(
                (0, 0, px - 1, px - 1),
                fill=(shade, int(shade * 0.84), int(shade * 0.66), 255),
            )
            light = (255, 240, 210, int(0.18 * 255))
            dark = (40, 25, 10, int(0.35 * 255))
            _fill(tile, (0, 0, px, 2), light)
            _fill(tile, (0, 0, 2, px), light)
            _fill(tile, (0, px - 3, px, px), dark)
            _fill(tile, (px - 3, 0, px, px), dark)
            for _ in range(7):
                speckle = (70, 45, 20, int(0.22 * 255)) if rand() < 0.5 else (255, 235, 200, int(0.16 * 255))
                sx = int(4 + rand() * (px - 10))
                sy = int(4 + rand() * (px - 10))
                _fill(tile, (sx, sy, sx + 2, sy + 2), speckle)
            if rand() < 0.12:
                crack = Image.new("RGBA", (px, px), (0, 0, 0, 0))
                cx = 8 + rand() * (px - 16)
                cy = 8 + rand() * (px - 16)
                ImageDraw.Draw(crack).line(
                    [
                        (cx, cy),
                        (cx + (rand() - 0.5) * 18, cy + (rand() - 0.5) * 18),
                        (cx + (rand() - 0.5) * 22, cy + (rand() - 0.5) * 22),
                    ],
                    fill=(60, 38, 18, int(0.35 * 255)),
                    width=1,
                )
                tile.alpha_composite(crack)
            image.paste(tile, (origin + x * px, origin + y * px))
    return image


def gem_sprite(pixels: int) -> Image.Image:
    sprite = Image.new("RGBA", (len(GEM), len(GEM)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    for y, row in enumerate(GEM):
        for x, pixel in enumerate(row):
            if pixel in PALETTE:
                draw.point((x, y), fill=PALETTE[pixel])
    return sprite.resize((pixels, pixels), Image.Resampling.NEAREST)


def board_size(name: str) -> int:
    if name.startswith(("andrade16", "split16", "scatter16")):
        return 16
    if name.startswith("andrade10"):
        return 10
    if name.startswith("andrade_"):
        return 20
    return 10


def round_terrains() -> list[str]:
    """The pac-man round list in foraging.py, before a variant replaces it."""
    text = (ROOT / "foraging.py").read_text()
    block = re.search(r"^ROUND_TERRAINS = \[(.*?)\n\]", text, re.M | re.S)
    if block is None:
        raise RuntimeError("ROUND_TERRAINS not found in foraging.py")
    return re.findall(r'"([^"]+)"', block.group(1))


def draw_world(name: str, coins: list, grid_size: int, cell_px: int) -> Image.Image:
    if cell_px % 20 != 0:
        raise ValueError(f"cell size must be a multiple of 20, got {cell_px}")
    floor = floor_texture(grid_size)
    out = (grid_size + 1) * cell_px  # half a cell of rock on every side
    image = floor.resize((out, out), Image.Resampling.LANCZOS)
    gem_px = cell_px // 2  # the gem occupies half a cell, as in the game
    gem = gem_sprite(gem_px)
    border = cell_px // 2
    for x, y in coins:
        if not (0 <= x < grid_size and 0 <= y < grid_size):
            raise ValueError(f"{name}: coin {(x, y)} is outside the {grid_size} board")
        gx = border + x * cell_px + (cell_px - gem_px) // 2
        gy = border + y * cell_px + (cell_px - gem_px) // 2
        image.alpha_composite(gem, (gx, gy))
    return image.convert("RGB")


def load_map(name: str) -> list[tuple[int, int]]:
    path = MAPS_DIR / f"{name}.json"
    return [tuple(pos) for pos in json.loads(path.read_text())]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", help="one map name, without .json")
    parser.add_argument("--all", action="store_true", help="every map in static/maps")
    parser.add_argument("--dpi", type=int, default=DPI)
    parser.add_argument("--cell-px", type=int, default=CELL_PX)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.map:
        names = [args.map]
    elif args.all:
        names = sorted(path.stem for path in MAPS_DIR.glob("*.json"))
    else:
        names = round_terrains()

    args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        coins = load_map(name)
        image = draw_world(name, coins, board_size(name), args.cell_px)
        path = args.out / f"{name}.png"
        image.save(path, dpi=(args.dpi, args.dpi))
        print(f"{name}: {len(coins)} points, {image.width}px -> {path}")


if __name__ == "__main__":
    main()

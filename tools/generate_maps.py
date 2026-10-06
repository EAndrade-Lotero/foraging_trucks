"""Generate the coin maps for each terrain (writes static/maps/<terrain>.json).

Ported from the World class of EAndrade-Lotero/Coordinator_and_Foragers (helper_classes.py):
coins are sampled from bivariate normals around centroids, and `dispersion` is the variance.
Maps are fixed and seeded so every dyad sees the same terrain in a given round.

    python tools/generate_maps.py            # regenerate with the default seed
    python tools/generate_maps.py --show     # also print the maps as ASCII
    python tools/generate_maps.py --andrade DIR  # Andrade's 80x80 map*.json -> 10x10 andrade10_*
    python tools/generate_maps.py --andrade DIR --size 16  # -> 16x16 andrade16_* (pac-man board)
    python tools/generate_maps.py --andrade DIR --size 20  # -> 20x20 andrade_* (trucks variant)

Andrade's maps (DIR is static/ in EAndrade-Lotero/Coordinator_and_Foragers) were made with
World.create_and_place_coins, which samples coins from bivariate normals around centroids laid
out by World.get_centroids (circular, linear_up, linear_down or random). The per-map biases were
not recorded, so the saved 80x80 maps are scaled instead of regenerated.
"""
import argparse
import json
from pathlib import Path

import numpy as np

GRID_SIZE = 10
SEED = 42
# Spawn corners stay free so nobody starts on a coin (see SPAWN_POSITIONS in foraging.py).
BLOCKED = {(0, 0), (GRID_SIZE - 1, 0), (0, GRID_SIZE - 1), (GRID_SIZE - 1, GRID_SIZE - 1)}

# Slides 7-8: abundant concentrated resources vs. scattered scarce resources.
TERRAINS = {
    "abundant": {"n_coins": 16, "n_centroids": 1, "dispersion": 1.0},
    "scarce": {"n_coins": 8, "n_centroids": 4, "dispersion": 6.0},
}

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "maps"


def generate(n_coins: int, n_centroids: int, dispersion: float, rng) -> list:
    margin = 1 if n_centroids == 1 else 0
    centroids = rng.uniform(margin, GRID_SIZE - 1 - margin, size=(n_centroids, 2))
    coins = set()
    # Sample until the requested number of distinct free cells is reached.
    while len(coins) < n_coins:
        cx, cy = centroids[rng.integers(n_centroids)]
        x, y = rng.multivariate_normal((cx, cy), [[dispersion, 0], [0, dispersion]])
        pos = (int(np.clip(round(x), 0, GRID_SIZE - 1)), int(np.clip(round(y), 0, GRID_SIZE - 1)))
        if pos not in BLOCKED:
            coins.add(pos)
    return sorted(coins)


def corners(size: int) -> set:
    return {(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)}


def scale_andrade(path: Path, size: int, source_size: int = 80) -> list:
    """Coordinator_and_Foragers maps are lists of (x, y) coins on an 80x80 world.

    Each factor x factor block becomes one cell, which keeps their shape (shifted circular
    clusters or lines). On the pac-man boards the start corners stay free; the trucks variant
    (20x20) starts at the centre instead.
    """
    factor = source_size // size
    coins = {(x // factor, y // factor) for x, y in json.loads(path.read_text())}
    if size != 20:
        coins -= corners(size)
    return sorted(coins)


def andrade_prefix(size: int) -> str:
    return "andrade" if size == 20 else f"andrade{size}"


def ascii_map(coins: list, size: int = GRID_SIZE) -> str:
    cells = set(map(tuple, coins))
    return "\n".join(
        "".join("o" if (x, y) in cells else "." for x in range(size))
        for y in range(size)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--andrade", type=Path, help="folder with Andrade's map*.json")
    parser.add_argument("--size", type=int, default=GRID_SIZE, help="board size for --andrade")
    args = parser.parse_args()

    if args.andrade:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        prefix = andrade_prefix(args.size)
        for path in sorted(args.andrade.glob("map*.json")):
            coins = scale_andrade(path, args.size)
            (OUT_DIR / f"{prefix}_{path.stem}.json").write_text(json.dumps(coins))
            print(f"{prefix}_{path.stem}: {len(coins)} coins")
            if args.show:
                print(ascii_map(coins, args.size), end="\n\n")
        return

    rng = np.random.default_rng(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for terrain, params in TERRAINS.items():
        coins = generate(rng=rng, **params)
        (OUT_DIR / f"{terrain}.json").write_text(json.dumps(coins))
        print(f"{terrain}: {len(coins)} coins -> {OUT_DIR / f'{terrain}.json'}")
        if args.show:
            print(ascii_map(coins), end="\n\n")


if __name__ == "__main__":
    main()

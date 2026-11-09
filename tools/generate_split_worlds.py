"""Four 16x16 worlds with the round maps' average number of pebbles, split in half.

The ten round maps average 22.2 pebbles (foraging.py). 22 is the even count nearest
that average, so each side can hold the same number: 11 on the left half (x 0-7)
and 11 on the right half (x 8-15). Each half is one cluster, sampled the same way
as tools/generate_maps.py (a normal around a centroid). The four worlds are the
four ways to set the height of the two clusters. Spawn corners stay empty.

    python tools/generate_split_worlds.py
"""
import json
from pathlib import Path

import numpy as np

GRID_SIZE = 16
PER_SIDE = 11  # 22 in total, the even number nearest the 22.2 round-map average
DISPERSION = 1.1  # variance of the normal; matches the abundant terrain's scale
SEED = 16
OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "maps"
CORNERS = {(0, 0), (GRID_SIZE - 1, 0), (0, GRID_SIZE - 1), (GRID_SIZE - 1, GRID_SIZE - 1)}

# Left centroid x=3, right centroid x=12. High sits near the top, low near the bottom.
LAYOUTS = {
    "split16_level_top": ((3, 4), (12, 4)),
    "split16_level_bottom": ((3, 11), (12, 11)),
    "split16_diagonal": ((3, 4), (12, 11)),
    "split16_antidiagonal": ((3, 11), (12, 4)),
}


def cluster(rng, centroid: tuple[int, int], x_min: int, x_max: int) -> list[tuple[int, int]]:
    coins = set()
    while len(coins) < PER_SIDE:
        x, y = rng.multivariate_normal(centroid, [[DISPERSION, 0], [0, DISPERSION]])
        pos = (int(np.clip(round(x), 0, GRID_SIZE - 1)), int(np.clip(round(y), 0, GRID_SIZE - 1)))
        if x_min <= pos[0] <= x_max and pos not in CORNERS:
            coins.add(pos)
    return sorted(coins)


def world(name: str, rng) -> list[tuple[int, int]]:
    left, right = LAYOUTS[name]
    return cluster(rng, left, 0, 7) + cluster(rng, right, 8, GRID_SIZE - 1)


def main():
    rng = np.random.default_rng(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in LAYOUTS:
        coins = world(name, rng)
        left = sum(x < GRID_SIZE // 2 for x, _ in coins)
        (OUT_DIR / f"{name}.json").write_text(json.dumps(coins))
        print(f"{name}: {len(coins)} pebbles, {left} left and {len(coins) - left} right")


if __name__ == "__main__":
    main()

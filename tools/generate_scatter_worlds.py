"""Four more scattered 16x16 worlds, made the same way as andrade16_map_scattered.

tools/generate_scattered_map.py drops coins independently on Andrade's 80x80 world
(expected 10 coins) and tools/generate_maps.py folds each 5x5 block into one cell.
That saved map has 11 pebbles. This writes four more draws from the same process.
A draw is kept when it is about as full as that map and the pebbles reach both
halves of the board, so a nearly empty draw is not saved.

    python tools/generate_scatter_worlds.py
"""
import json
from pathlib import Path

import numpy as np

SOURCE = 80
SIZE = 16
EXPECTED = 10  # expected coins on the 80x80 world, as in generate_scattered_map.py
SEED = 16
COUNT = 4
OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "maps"
CORNERS = {(0, 0), (SIZE - 1, 0), (0, SIZE - 1), (SIZE - 1, SIZE - 1)}


def scatter(rng) -> list[tuple[int, int]]:
    p = EXPECTED / (SOURCE * SOURCE)
    factor = SOURCE // SIZE
    coins = set()
    for x in range(SOURCE):
        for y in range(SOURCE):
            if rng.random() < p:
                coins.add((x // factor, y // factor))
    coins -= CORNERS
    return sorted(coins)


def spread_out(coins: list[tuple[int, int]]) -> bool:
    """Close to the saved scatter map: 11 pebbles, spanning the board."""
    if not 8 <= len(coins) <= 14:
        return False
    xs = [x for x, _ in coins]
    ys = [y for _, y in coins]
    if max(xs) - min(xs) < 10 or max(ys) - min(ys) < 10:
        return False
    left = sum(x < SIZE // 2 for x, _ in coins)
    return 2 <= left <= len(coins) - 2


def main():
    rng = np.random.default_rng(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    draws = 0
    while saved < COUNT:
        draws += 1
        coins = scatter(rng)
        if not spread_out(coins):
            continue
        saved += 1
        name = f"scatter16_{saved}"
        (OUT_DIR / f"{name}.json").write_text(json.dumps(coins))
        left = sum(x < SIZE // 2 for x, _ in coins)
        print(f"{name}: {len(coins)} pebbles, {left} left and {len(coins) - left} right")
    print(f"kept {COUNT} of {draws} draws")


if __name__ == "__main__":
    main()

"""Scattered, scarce coin map made with Andrade's own generator (slides 7-8).

Runs World.create_random_coins from EAndrade-Lotero/Coordinator_and_Foragers (helper_classes.py,
uniform random coins) on his 80x80 world and writes an 80x80 map; tools/generate_maps.py then
scales it like his other maps (add --size 16 for the 16x16 board):

    git clone https://github.com/EAndrade-Lotero/Coordinator_and_Foragers /tmp/coord
    cd /tmp/coord && uv run --with numpy --with matplotlib --with pillow \\
        python ~/Projects/research/foraging_trucks/tools/generate_scattered_map.py \\
        ~/Projects/research/foraging_trucks/referencias/coordinator_maps_80x80/map_scattered.json
    python tools/generate_maps.py --andrade referencias/coordinator_maps_80x80
"""
import json
import logging
import sys
import types

# helper_classes only uses PsyNet for a logger; a stub lets it run outside an experiment.
psynet, utils = types.ModuleType("psynet"), types.ModuleType("psynet.utils")
utils.get_logger = lambda *args, **kwargs: logging.getLogger("world")
sys.modules.update({"psynet": psynet, "psynet.utils": utils})
sys.path.insert(0, ".")

from helper_classes import World  # noqa: E402  (Andrade's code, run from his repo)

COINS = 10  # expected coins on the 6400-cell world

world = World(num_coins=COINS, num_centroids=COINS, distribution="random", dispersion=1)
world.clear()
world.place_given_coins(world.create_random_coins(p=COINS / 6400))
json.dump(world.coin_positions(), open(sys.argv[1], "w"))
print(f"{len(world.coin_positions())} coins -> {sys.argv[1]}")

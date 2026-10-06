# Foraging trucks

This experiment is implemented using *PsyNet*. Pairs of players are grouped and play 2 rounds.
Before the first round they see how the game works and an interactive example of the contract.
Each round then runs:

1. Buy fuel (slider, 0–20 litres; every move uses fuel)
2. Collective foraging on a shared board (one fixed terrain per round, `static/maps/`)
3. Score under the current commission–wages contract, minus fuel and a fixed cost
4. Propose a new contract (slider); the next round uses the average of both proposals

The economy constants are at the top of `experiment.py` and `foraging.py`.
Terrain maps are generated with `python tools/generate_maps.py --show`.

Local setup:

```bash
uv venv --python 3.13
source .venv/bin/activate
uv pip install -r constraints.txt
psynet debug local
```

For comprehensive guidance, see [PsyNet's documentation](https://psynetdev.gitlab.io/PsyNet/).

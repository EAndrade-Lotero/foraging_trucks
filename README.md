# Foraging trucks

This experiment is implemented using *PsyNet*. After grouping, each static-chain trial runs:

1. Tutorial
2. Buy fuel
3. Collective foraging (same board format as `collective_foraging_demo`)
4. Score under the current contract
5. Propose a new contract (payment per coin)

Local setup:

```bash
uv venv --python 3.13
source .venv/bin/activate
uv pip install -r constraints.txt
psynet debug local
```

For comprehensive guidance, see [PsyNet's documentation](https://psynetdev.gitlab.io/PsyNet/).

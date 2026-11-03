#!/usr/bin/env python
"""Run the flexible-lobby checks.

Historical session fixtures belong to the ultimatum experiment, so they are
not copied here. Pass --allow-missing-history to record that choice.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing-history",
        action="store_true",
        help="this experiment has no archived lobby sessions to replay",
    )
    parser.parse_args()
    started = time.time()
    script = ROOT / "tests" / "flexible_lobby" / "test_lobby_logic.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--run-regression"],
        cwd=ROOT,
    )
    total = time.time() - started
    if completed.returncode != 0:
        print(f"\nFlexible-lobby suite FAILED after {total:.1f}s")
        sys.exit(completed.returncode)
    print(f"\nFlexible-lobby suite PASSED in {total:.1f}s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Cheap pre-check (standard library only) so the expensive steps - installing packages and starting
the MT5 terminal - run ONLY when something can happen:
  The bot now runs every 30 minutes, every day, at all hours (no session or weekday filter),
  except Saturday (UTC), which is skipped.
Writes `active=true|false` to $GITHUB_OUTPUT.
"""
import json
import os
import sys
import time

from utils.time_utils import now_utc
from config import STATE_DIR


def open_trades() -> int:
    try:
        with open(os.path.join(STATE_DIR, "trades.json")) as f:
            trades = json.load(f)
    except (OSError, ValueError):
        return 0
    return sum(1 for t in trades if t.get("status") == "OPEN")


def main() -> int:
    force = os.environ.get("KB_FORCE_SCAN", "false").lower() == "true"
    not_saturday = now_utc().weekday() != 5      # Monday=0 ... Saturday=5 (UTC)
    n_open = open_trades()
    active = not_saturday                        # every day, all hours, except Saturday (UTC)
    print(f"gate: not_saturday={not_saturday} open_trades={n_open} force={force} -> active={active}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"active={'true' if active else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

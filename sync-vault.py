#!/usr/bin/env python3
"""Refresh the Claude Code Brain vault in one command.

Part of the Claude Code Command Center toolkit. This is a MANUAL command -
it is not a cron job and must never be scheduled to run automatically. Run it
yourself whenever you want the brain to reflect your latest session history.

It runs the pipeline stages in order:

  1. export.py      -- re-export ~/.claude/projects/ into the markdown vault
  2. secret_scan.py -- scan the fresh vault and redact any secrets in place
  3. consolidate.py -- rebuild topic/tool/entity hubs from Stage 3 reports

Stage 3 caveat
--------------
consolidate.py needs JSON reports under vault/_build/reports/agent_*.json.
Those are produced by the Stage 3 backlink subagent run (a manual Claude Code
step - see STAGE3_BACKLINK.md), NOT by any script. If no reports are present,
this script SKIPS consolidate.py and tells you to do a Stage 3 run. The
existing hub pages are left untouched in that case.

Usage:
    python sync-vault.py                 # source -> ./vault
    python sync-vault.py --vault DIR     # use a different vault dir
    python sync-vault.py --source DIR    # use a different ~/.claude source
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_stage(label: str, args: list[str]) -> None:
    """Run one pipeline stage; abort the whole sync if it fails."""
    print(f"\n{'=' * 60}\n  {label}\n{'=' * 60}")
    print(f"  $ {' '.join(args)}\n")
    result = subprocess.run(args, cwd=HERE)
    if result.returncode != 0:
        print(f"\nERROR: {label} failed (exit {result.returncode}). Sync aborted.",
              file=sys.stderr)
        sys.exit(result.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Manually refresh the Claude Code Brain vault.")
    ap.add_argument("--vault", type=Path, default=Path("vault"),
                    help="vault directory (default: ./vault)")
    ap.add_argument("--source", type=Path, default=None,
                    help="Claude Code projects dir (default: export.py auto-detects)")
    args = ap.parse_args()

    py = sys.executable  # same interpreter that launched this script
    vault = args.vault

    print("Claude Code Brain - vault sync")
    print(f"  toolkit dir : {HERE}")
    print(f"  vault dir   : {(HERE / vault).resolve()}")
    print("  NOTE: this is a manual command - never schedule it.")

    # ----- Stage 2: export ------------------------------------------------
    export_args = [py, "export.py", "--out", str(vault)]
    if args.source is not None:
        export_args += ["--source", str(args.source)]
    run_stage("Stage 2: export.py  (re-export session history)", export_args)

    # ----- Stage 2.5: secret scan ----------------------------------------
    run_stage("Stage 2.5: secret_scan.py  (redact secrets in place)",
              [py, "secret_scan.py", "--vault", str(vault)])

    # ----- Stage 3 (final step): consolidate -----------------------------
    reports = sorted((HERE / vault / "_build" / "reports").glob("agent_*.json"))
    if reports:
        print(f"\nFound {len(reports)} Stage 3 report(s) - rebuilding hub pages.")
        run_stage("Stage 3: consolidate.py  (rebuild topic/tool/entity hubs)",
                  [py, "consolidate.py", "--vault", str(vault)])
    else:
        print("\n" + "-" * 60)
        print("  SKIPPING consolidate.py - no Stage 3 reports found at")
        print(f"  {(HERE / vault / '_build' / 'reports').resolve()}")
        print("  Run the Stage 3 backlink subagents (see STAGE3_BACKLINK.md)")
        print("  to regenerate agent_*.json, then re-run this script.")
        print("  Existing hub pages were left unchanged.")
        print("-" * 60)

    print("\nSync complete. The brain is up to date.")
    print("The claude-brain skill will read the refreshed vault on the next "
          "Claude Code session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

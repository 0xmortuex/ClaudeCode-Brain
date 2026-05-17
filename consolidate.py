#!/usr/bin/env python3
"""Stage 3 (final step) - Consolidate backlink agent reports into hub pages.

Part of the Claude Code Command Center toolkit. Run this AFTER the 10 backlink
subagents have finished and written their reports to vault/_build/reports/.

It reads every _build/reports/agent_*.json file and generates:
  - topics/<slug>.md   one hub page per topic
  - tools/<slug>.md    one hub page per tool/framework
  - entities/<slug>.md one hub page per entity
  - TOP-TOPICS.md      a leaderboard at the vault root

Hub pages are written atomically (temp file + replace) so a crash mid-run
never leaves a half-written page.

Each agent report must be JSON of the form:
    {
      "agent": 1,
      "sessions": [
        {
          "session_file": "projects/<name>/sessions/<stem>.md",
          "project": "<name>",
          "topics":   ["kebab-case", ...],
          "tools":    ["pytest", ...],
          "entities": ["castLabs", ...],
          "summary":  "One sentence."
        }
      ]
    }

Usage:
    python consolidate.py                 # uses ./vault
    python consolidate.py --vault DIR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

CATEGORIES = ("topics", "tools", "entities")


def slugify(text: str, fallback: str = "untitled") -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or fallback


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def wikilink(session_file: str) -> str:
    return Path(session_file).stem


def main() -> int:
    ap = argparse.ArgumentParser(description="Consolidate backlink reports into hub pages.")
    ap.add_argument("--vault", type=Path, default=Path("vault"))
    args = ap.parse_args()

    vault: Path = args.vault
    reports_dir = vault / "_build" / "reports"
    if not reports_dir.exists():
        print(f"ERROR: reports dir not found: {reports_dir}", file=sys.stderr)
        print("Run the Stage 3 backlink agents first.", file=sys.stderr)
        return 1

    report_files = sorted(reports_dir.glob("agent_*.json"))
    if not report_files:
        print(f"ERROR: no agent_*.json reports in {reports_dir}", file=sys.stderr)
        return 1

    # category -> slug -> {"label": str, "sessions": {(file, project, summary)}}
    index: dict[str, dict] = {c: defaultdict(lambda: {"label": "", "sessions": set()})
                              for c in CATEGORIES}
    field_map = {"topics": "topics", "tools": "tools", "entities": "entities"}
    sessions_seen = 0
    bad_reports: list[str] = []

    for rf in report_files:
        try:
            data = json.loads(rf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            bad_reports.append(f"{rf.name}: {exc}")
            continue
        for sess in data.get("sessions", []):
            sessions_seen += 1
            sfile = sess.get("session_file", "")
            project = sess.get("project", "")
            summary = sess.get("summary", "")
            ref = (sfile, project, summary)
            for cat, key in field_map.items():
                for raw in sess.get(key, []) or []:
                    slug = slugify(str(raw))
                    bucket = index[cat][slug]
                    bucket["label"] = bucket["label"] or str(raw)
                    bucket["sessions"].add(ref)

    written = {c: 0 for c in CATEGORIES}
    for cat in CATEGORIES:
        (vault / cat).mkdir(parents=True, exist_ok=True)
        for slug, bucket in index[cat].items():
            refs = sorted(bucket["sessions"])
            lines = [
                f"# {bucket['label']}", "",
                f"_{cat[:-1].capitalize()} hub - {len(refs)} session(s)._", "",
                "## Sessions", "",
            ]
            for sfile, project, summary in refs:
                tail = f" - {summary}" if summary else ""
                lines.append(f"- [[{wikilink(sfile)}]] (`{project}`){tail}")
            atomic_write(vault / cat / f"{slug}.md", "\n".join(lines) + "\n")
            written[cat] += 1

    topic_counts = sorted(
        ((b["label"], len(b["sessions"])) for b in index["topics"].values()),
        key=lambda kv: (-kv[1], kv[0]))
    leaderboard = [
        "# Top Topics", "",
        f"_Leaderboard across {sessions_seen} session record(s)._", "",
        "| Rank | Topic | Sessions |",
        "|------|-------|----------|",
    ]
    for rank, (label, count) in enumerate(topic_counts, 1):
        leaderboard.append(f"| {rank} | [[{slugify(label)}]] | {count} |")
    atomic_write(vault / "TOP-TOPICS.md", "\n".join(leaderboard) + "\n")

    print("=== Stage 3: Consolidation complete ===")
    print(f"Reports read       : {len(report_files)}")
    print(f"Session records    : {sessions_seen}")
    print(f"Topic hub pages    : {written['topics']}")
    print(f"Tool hub pages     : {written['tools']}")
    print(f"Entity hub pages   : {written['entities']}")
    print(f"TOP-TOPICS.md      : {len(topic_counts)} topics ranked")
    if bad_reports:
        print("\nWARNING: unparseable reports:")
        for line in bad_reports:
            print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

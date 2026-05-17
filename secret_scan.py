#!/usr/bin/env python3
"""Stage 2.5 - Scan the exported vault for secrets and redact them in place.

Part of the Claude Code Command Center toolkit. Run this AFTER export.py and
BEFORE the Stage 3 backlink run, so the vault is safe to commit or share.

Each match is replaced with <REDACTED:type>. A SECRETS-REDACTED.md report is
written to the vault root listing redaction counts per file (never the
secrets themselves).

Usage:
    python secret_scan.py                 # scans ./vault
    python secret_scan.py --vault DIR
    python secret_scan.py --vault DIR --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# (label, compiled pattern). Order matters: more specific patterns first so a
# broad pattern cannot swallow a prefix a narrower one would match.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic-key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("openai-key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("github-token", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    ("xai-key", re.compile(r"xai-[a-zA-Z0-9]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("discord-token", re.compile(r"OTY[0-9]{2}[a-zA-Z0-9]{20,}")),
    ("discord-token", re.compile(r"MTI[a-zA-Z0-9]{20,}")),
    ("jwt", re.compile(r"[a-zA-Z0-9_-]{40,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}")),
    ("pem-private-key", re.compile(
        r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
        re.DOTALL)),
]

STOP_THRESHOLD = 50


def scan_text(text: str) -> tuple[str, Counter]:
    counts: Counter = Counter()

    def make_sub(label: str):
        def _sub(_m: re.Match) -> str:
            counts[label] += 1
            return f"<REDACTED:{label}>"
        return _sub

    for label, pattern in PATTERNS:
        text = pattern.sub(make_sub(label), text)
    return text, counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Redact secrets in the exported vault.")
    ap.add_argument("--vault", type=Path, default=Path("vault"),
                    help="Vault directory to scan (default: ./vault)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report matches without modifying files")
    args = ap.parse_args()

    vault: Path = args.vault
    if not vault.exists():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 1

    md_files = sorted(p for p in vault.rglob("*.md")
                      if p.name != "SECRETS-REDACTED.md")
    per_file: dict[Path, Counter] = {}
    total = Counter()

    for path in md_files:
        original = path.read_text(encoding="utf-8", errors="replace")
        redacted, counts = scan_text(original)
        if counts:
            per_file[path] = counts
            total.update(counts)
            if not args.dry_run:
                path.write_text(redacted, encoding="utf-8")

    grand_total = sum(total.values())
    report = [
        "# Secrets Redacted", "",
        f"- **Files scanned:** {len(md_files)}",
        f"- **Files with redactions:** {len(per_file)}",
        f"- **Total redactions:** {grand_total}",
        "",
        "## By type", "",
    ]
    for label, n in sorted(total.items(), key=lambda kv: -kv[1]):
        report.append(f"- `{label}`: {n}")
    report += ["", "## By file", ""]
    if per_file:
        report.append("| File | Redactions | Types |")
        report.append("|------|-----------|-------|")
        for path, counts in sorted(per_file.items()):
            rel = path.relative_to(vault).as_posix()
            types = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
            report.append(f"| {rel} | {sum(counts.values())} | {types} |")
    else:
        report.append("_No secrets found._")

    (vault / "SECRETS-REDACTED.md").write_text("\n".join(report) + "\n",
                                               encoding="utf-8")

    mode = "DRY RUN - no files modified" if args.dry_run else "files redacted in place"
    print("=== Stage 2.5: Secret scan complete ===")
    print(f"Mode                  : {mode}")
    print(f"Files scanned         : {len(md_files)}")
    print(f"Files with redactions : {len(per_file)}")
    print(f"Total redactions      : {grand_total}")
    if grand_total > STOP_THRESHOLD:
        print(f"\nWARNING: {grand_total} matches exceeds the stop threshold "
              f"({STOP_THRESHOLD}). Review SECRETS-REDACTED.md before continuing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

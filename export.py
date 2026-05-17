#!/usr/bin/env python3
"""Stage 2 - Export Claude Code session history into a markdown vault.

Part of the Claude Code Command Center toolkit. Reads the JSONL transcripts
that Claude Code stores under ~/.claude/projects/ and renders them into an
Obsidian-friendly markdown vault.

Cross-platform: Path.home() resolves the correct location on Windows, macOS
and Linux, so there are no hard-coded C:\\ paths. Run it on the machine that
holds your Claude Code history.

Usage:
    python export.py                       # default source -> ./vault
    python export.py --source DIR --out DIR
    python export.py --discover             # Stage 1 only: report, do not export
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TOOL_RESULT_CAP = 4000


def default_source() -> Path:
    return Path.home() / ".claude" / "projects"


def slugify(text: str, fallback: str = "untitled") -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or fallback


def read_jsonl(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def stringify(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    out.append(block.get("text", ""))
                elif "text" in block:
                    out.append(str(block["text"]))
                else:
                    out.append(json.dumps(block, ensure_ascii=False))
            else:
                out.append(str(block))
        return "\n".join(out)
    return json.dumps(content, ensure_ascii=False)


def collapsible(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def render_message(entry: dict) -> str:
    msg = entry.get("message") or {}
    content = msg.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "thinking":
            parts.append(collapsible("Thinking", block.get("thinking", "")))
        elif btype == "tool_use":
            name = block.get("name", "tool")
            payload = json.dumps(block.get("input", {}), indent=2, ensure_ascii=False)
            parts.append(collapsible(f"Tool call: {name}", f"```json\n{payload}\n```"))
        elif btype == "tool_result":
            text = stringify(block.get("content"))
            if len(text) > TOOL_RESULT_CAP:
                text = text[:TOOL_RESULT_CAP] + f"\n\n... [truncated - {len(text)} chars total]"
            parts.append(collapsible("Tool result", f"```\n{text}\n```"))
        elif btype == "image":
            parts.append("_[image omitted]_")
        else:
            dump = json.dumps(block, ensure_ascii=False, indent=2)
            parts.append(collapsible(f"Block: {btype}", f"```json\n{dump}\n```"))
    return "\n\n".join(p for p in parts if p)


def first_field(events: list[dict], field: str) -> str | None:
    for e in events:
        if e.get(field):
            return e[field]
    return None


def session_summary(events: list[dict]) -> str:
    for e in events:
        if e.get("type") == "summary" and e.get("summary"):
            return str(e["summary"])
    return ""


def thread_split(events: list[dict]) -> tuple[list[dict], list[list[dict]]]:
    """Split events into the main thread and one list per subagent thread."""
    main = [e for e in events if not e.get("isSidechain")]
    side = [e for e in events if e.get("isSidechain")]
    threads: list[list[dict]] = []
    thread_of: dict[str, int] = {}
    for e in side:
        parent = e.get("parentUuid")
        if parent in thread_of:
            idx = thread_of[parent]
        else:
            idx = len(threads)
            threads.append([])
        threads[idx].append(e)
        if e.get("uuid"):
            thread_of[e["uuid"]] = idx
    return main, threads


def render_thread(events: list[dict]) -> str:
    blocks: list[str] = []
    for e in events:
        etype = e.get("type")
        if etype not in ("user", "assistant"):
            continue
        body = render_message(e)
        if not body.strip():
            continue
        role = "User" if etype == "user" else "Assistant"
        ts = parse_ts(e.get("timestamp"))
        stamp = f" - {ts:%H:%M:%S}" if ts else ""
        blocks.append(f"### {role}{stamp}\n\n{body}")
    return "\n\n---\n\n".join(blocks)


def yaml_block(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None or value == "":
            value = ""
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def discover(source: Path) -> dict:
    jsonl = sorted(source.rglob("*.jsonl"))
    folders = {p.parent for p in jsonl}
    total_bytes = sum(p.stat().st_size for p in jsonl)
    mtimes = [p.stat().st_mtime for p in jsonl]
    return {
        "jsonl_count": len(jsonl),
        "folder_count": len(folders),
        "total_mb": round(total_bytes / 1_048_576, 2),
        "oldest": datetime.fromtimestamp(min(mtimes), tz=timezone.utc).isoformat() if mtimes else None,
        "newest": datetime.fromtimestamp(max(mtimes), tz=timezone.utc).isoformat() if mtimes else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Claude Code history to a markdown vault.")
    ap.add_argument("--source", type=Path, default=default_source(),
                    help="Claude Code projects dir (default: ~/.claude/projects)")
    ap.add_argument("--out", type=Path, default=Path("vault"),
                    help="Vault output directory (default: ./vault)")
    ap.add_argument("--discover", action="store_true",
                    help="Stage 1 only: report corpus size and exit")
    args = ap.parse_args()

    source: Path = args.source
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        print("Run this on the machine that holds your Claude Code history.", file=sys.stderr)
        return 1

    if args.discover:
        info = discover(source)
        print("=== Stage 1: Discovery ===")
        print(f"Source              : {source}")
        print(f"JSONL files         : {info['jsonl_count']}")
        print(f"Project folders     : {info['folder_count']}")
        print(f"Total size on disk  : {info['total_mb']} MB")
        print(f"Oldest file         : {info['oldest']}")
        print(f"Newest file         : {info['newest']}")
        if info["total_mb"] > 5120:
            print("\nWARNING: corpus exceeds 5 GB - review before a full backlink run.")
        return 0

    jsonl_files = sorted(source.rglob("*.jsonl"))
    raw_folders = {p.parent.name for p in jsonl_files}

    # Group sessions by cwd so worktrees of the same project collapse together.
    by_cwd: dict[str, list[tuple[Path, list[dict]]]] = defaultdict(list)
    processed = 0
    for jf in jsonl_files:
        events = read_jsonl(jf)
        if not events:
            continue
        processed += 1
        cwd = first_field(events, "cwd") or jf.parent.name
        by_cwd[cwd].append((jf, events))

    out: Path = args.out
    for sub in ("projects", "topics", "tools", "entities", "_build/reports"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    used_names: dict[str, str] = {}
    md_written = 0
    project_rows: list[dict] = []

    for cwd, sessions in sorted(by_cwd.items()):
        base = slugify(Path(cwd).name)
        name = base
        suffix = 2
        while name in used_names and used_names[name] != cwd:
            name = f"{base}-{suffix}"
            suffix += 1
        used_names[name] = cwd

        pdir = out / "projects" / name
        (pdir / "sessions").mkdir(parents=True, exist_ok=True)
        (pdir / "subagents").mkdir(parents=True, exist_ok=True)

        session_rows: list[dict] = []
        for jf, events in sessions:
            session_id = first_field(events, "sessionId") or jf.stem
            main, threads = thread_split(events)
            ts_list = [parse_ts(e.get("timestamp")) for e in events]
            ts_list = [t for t in ts_list if t]
            started = min(ts_list) if ts_list else None
            ended = max(ts_list) if ts_list else None
            date_str = f"{started:%Y-%m-%d}" if started else "0000-00-00"
            summary = session_summary(events)
            slug = slugify(session_id[:8] if len(session_id) > 8 else session_id)
            stem = f"{date_str}_{slug}"

            git_branch = first_field(events, "gitBranch")
            msg_count = sum(1 for e in main if e.get("type") in ("user", "assistant"))

            sub_links: list[str] = []
            for i, thread in enumerate(threads, 1):
                sub_stem = f"{stem}_subagent-{i}"
                sub_fm = yaml_block({
                    "type": "subagent",
                    "project": name,
                    "parent_session": f"../sessions/{stem}.md",
                    "session_id": session_id,
                    "date": date_str,
                })
                sub_body = render_thread(thread) or "_[no renderable content]_"
                (pdir / "subagents" / f"{sub_stem}.md").write_text(
                    f"{sub_fm}\n\n# Subagent {i} - session {slug}\n\n"
                    f"Parent session: [[{stem}]]\n\n{sub_body}\n",
                    encoding="utf-8")
                md_written += 1
                sub_links.append(f"[[{sub_stem}]]")

            fm = yaml_block({
                "type": "session",
                "project": name,
                "session_id": session_id,
                "date": date_str,
                "started": started.isoformat() if started else "",
                "ended": ended.isoformat() if ended else "",
                "messages": msg_count,
                "subagents": len(threads),
                "git_branch": git_branch or "",
                "cwd": cwd,
                "topics": [],
                "tools": [],
                "entities": [],
            })
            head = f"# Session {slug} - {date_str}\n\n"
            head += f"Project: [[_project]] | cwd: `{cwd}`\n\n"
            if summary:
                head += f"> **Summary:** {summary}\n\n"
            if sub_links:
                head += f"**Subagents:** {', '.join(sub_links)}\n\n"
            body = render_thread(main) or "_[no renderable content]_"
            (pdir / "sessions" / f"{stem}.md").write_text(
                f"{fm}\n\n{head}---\n\n{body}\n", encoding="utf-8")
            md_written += 1

            session_rows.append({
                "date": date_str, "stem": stem, "messages": msg_count,
                "subagents": len(threads), "summary": summary or "-",
            })

        session_rows.sort(key=lambda r: r["date"], reverse=True)
        total_msgs = sum(r["messages"] for r in session_rows)
        dates = [r["date"] for r in session_rows if r["date"] != "0000-00-00"]
        proj_md = [
            f"# Project: {name}", "",
            f"- **Path:** `{cwd}`",
            f"- **Sessions:** {len(session_rows)}",
            f"- **Total messages:** {total_msgs}",
            f"- **First activity:** {min(dates) if dates else '-'}",
            f"- **Last activity:** {max(dates) if dates else '-'}",
            "", "## Sessions", "",
            "| Date | Session | Messages | Subagents | Summary |",
            "|------|---------|----------|-----------|---------|",
        ]
        for r in session_rows:
            link = f"[{r['stem']}](sessions/{r['stem']}.md)"
            summ = r["summary"].replace("|", "\\|")[:100]
            proj_md.append(
                f"| {r['date']} | {link} | {r['messages']} | {r['subagents']} | {summ} |")
        (pdir / "_project.md").write_text("\n".join(proj_md) + "\n", encoding="utf-8")
        md_written += 1

        project_rows.append({
            "name": name, "sessions": len(session_rows),
            "messages": total_msgs, "last": max(dates) if dates else "-",
        })

    project_rows.sort(key=lambda r: r["last"], reverse=True)
    readme = [
        "# Claude Code Command Center", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from `{source}`.", "",
        f"- **Projects:** {len(project_rows)}",
        f"- **Sessions:** {sum(r['sessions'] for r in project_rows)}",
        f"- **Markdown files:** {md_written}",
        "", "## Projects", "",
        "| Project | Sessions | Messages | Last activity |",
        "|---------|----------|----------|---------------|",
    ]
    for r in project_rows:
        link = f"[{r['name']}](projects/{r['name']}/_project.md)"
        readme.append(f"| {link} | {r['sessions']} | {r['messages']} | {r['last']} |")
    (out / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    if not (out / "TOP-TOPICS.md").exists():
        (out / "TOP-TOPICS.md").write_text(
            "# Top Topics\n\n_Placeholder - generated by consolidate.py in Stage 3._\n",
            encoding="utf-8")

    vault_bytes = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    deduped = len(raw_folders) - len(by_cwd)

    print("=== Stage 2: Export complete ===")
    print(f"Raw project folders found : {len(raw_folders)}")
    print(f"JSONL files processed     : {processed}")
    print(f"Markdown files written    : {md_written}")
    print(f"Deduped projects (by cwd) : {deduped}")
    print(f"Distinct projects         : {len(by_cwd)}")
    print(f"Vault size                : {round(vault_bytes / 1_048_576, 2)} MB")
    print(f"Vault location            : {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

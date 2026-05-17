#!/usr/bin/env python3
"""
generate-context.py - Build a dense LLM context profile from the Brain vault.

Reads the local Obsidian vault produced by export.py + consolidate.py and
distills it into `my-context.md`: a ~300-500 word profile used as LLM context
by the AI News Tracker's "Explain for me" personalization feature.

Stdlib only (Python 3.9+). The vault stays LOCAL; only the generated
my-context.md is copied into the worker repo for deployment.

Run:  python generate-context.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --- paths ----------------------------------------------------------------
BRAIN = Path(r"C:\Users\USER\IdeaProjects\ClaudeCode-Brain")
VAULT = BRAIN / "vault"
OUT = Path(r"C:\Users\USER\IdeaProjects\ai-news-cors\src\my-context.md")

# --- tech-stack categorisation (tool slug -> category) --------------------
# The list of slugs is read live from vault/tools/; this map only decides
# which bucket each known slug lands in and gives it a display name.
TOOL_DISPLAY = {
    "javascript": "JavaScript", "typescript": "TypeScript", "python": "Python",
    "html-css-js": "HTML/CSS",
    "electron": "Electron", "node-js": "Node.js", "nodejs": "Node.js",
    "pyqt6": "PyQt6", "chromium": "Chromium",
    "castlabs-electron-releases": "castLabs Electron (DRM fork)",
    "django": "Django", "django-apscheduler": "django-apscheduler",
    "react": "React", "tailwindcss": "Tailwind CSS",
    "vite": "Vite", "electron-builder": "electron-builder", "nsis": "NSIS",
    "turborepo": "Turborepo", "wrangler": "Wrangler", "npm": "npm", "npx": "npx",
    "pnpm": "pnpm", "asar": "asar", "equilotl": "Equilotl",
    "cloudflare-workers": "Cloudflare Workers", "github-pages": "GitHub Pages",
    "github-api": "GitHub API", "github-cli": "GitHub CLI", "github": "GitHub",
    "git": "git", "vitest": "Vitest", "unittest": "unittest",
    "playwright": "Playwright", "playwright-mcp": "Playwright MCP", "jsdom": "jsdom",
    "eslint": "ESLint", "prettier": "Prettier",
    "numpy": "NumPy", "scipy": "SciPy", "sounddevice": "sounddevice",
    "fast-xml-parser": "fast-xml-parser", "feedparser": "feedparser", "rss": "RSS",
    "claude-code": "Claude Code", "claude-flow": "claude-flow", "ruflo": "Ruflo",
    "octogent": "Octogent", "bash": "bash", "curl": "curl", "obsidian": "Obsidian",
    "sqlite": "SQLite", "localstorage": "localStorage", "argparse": "argparse",
}
CATEGORIES = [
    ("Languages", ["javascript", "typescript", "python", "html-css-js"]),
    ("Desktop & runtime", ["electron", "node-js", "nodejs", "pyqt6",
                           "castlabs-electron-releases", "chromium"]),
    ("Web frameworks", ["django", "django-apscheduler", "react", "tailwindcss"]),
    ("Build & packaging", ["vite", "electron-builder", "nsis", "turborepo",
                           "wrangler", "npm", "npx", "pnpm", "asar", "equilotl"]),
    ("Cloud & VCS", ["cloudflare-workers", "github-pages", "github-api",
                     "github-cli", "github", "git"]),
    ("Testing & QA", ["vitest", "unittest", "playwright", "playwright-mcp",
                      "jsdom", "eslint", "prettier"]),
    ("Libraries", ["numpy", "scipy", "sounddevice", "fast-xml-parser",
                   "feedparser", "rss"]),
    ("AI & agent tooling", ["claude-code", "claude-flow", "ruflo", "octogent"]),
]

# Friendly names + one-liners for the projects worth surfacing.
PROJECT_INFO = {
    "vex": "Vex - custom Electron desktop browser (primary, long-running project)",
    "untitled1": "AI News Tracker - static news/guides site + Cloudflare Worker proxy",
    "vencord-dev": "Vencord / Equicord - Discord client mod plugin development",
    "crux": "Crux - Electron app bug-fixing and feature work",
    "crux-2": "Crux - Electron app bug-fixing and feature work",
    "brain": "ClaudeCode-Brain - Obsidian vault tooling for session history",
}


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not VAULT.is_dir():
        fail(f"vault not found at {VAULT} - run export.py first")

    # --- session totals ---------------------------------------------------
    top_topics_md = read(VAULT / "TOP-TOPICS.md")
    m = re.search(r"across\s+(\d+)\s+session", top_topics_md)
    total_sessions = int(m.group(1)) if m else 0

    # --- per-project rollups ---------------------------------------------
    projects = {}
    for pfile in sorted(VAULT.glob("projects/*/_project.md")):
        text = read(pfile)
        name = pfile.parent.name
        sess = re.search(r"\*\*Sessions:\*\*\s*(\d+)", text)
        msgs = re.search(r"\*\*Total messages:\*\*\s*(\d+)", text)
        last = re.search(r"\*\*Last activity:\*\*\s*([\d-]+)", text)
        projects[name] = {
            "sessions": int(sess.group(1)) if sess else 0,
            "messages": int(msgs.group(1)) if msgs else 0,
            "last": last.group(1) if last else "?",
        }

    vex_sessions = projects.get("vex", {}).get("sessions", 0)

    # --- active projects from the vault README table ---------------------
    readme = read(VAULT / "README.md")
    rows = re.findall(r"\|\s*\[([a-z0-9-]+)\]\([^)]+\)\s*\|", readme)
    seen, active = set(), []
    for name in rows:
        info = PROJECT_INFO.get(name)
        if not info:
            continue
        key = info.split(" - ")[0]
        if key in seen:
            continue
        seen.add(key)
        p = projects.get(name, {})
        active.append(f"- {info} ({p.get('sessions', 0)} sessions, "
                      f"last {p.get('last', '?')})")

    # --- tech stack from tools/ ------------------------------------------
    tool_slugs = {p.stem for p in VAULT.glob("tools/*.md")}
    if len(tool_slugs) < 5:
        fail(f"only {len(tool_slugs)} tool notes found - vault looks incomplete")

    stack_lines = []
    for label, slugs in CATEGORIES:
        present = []
        for s in slugs:
            if s in tool_slugs:
                disp = TOOL_DISPLAY.get(s, s)
                if disp not in present:
                    present.append(disp)
        if present:
            stack_lines.append(f"- **{label}:** {', '.join(present)}")

    # --- entity sanity check ---------------------------------------------
    for ent in ("vex", "ai-news-tracker", "claude"):
        if not (VAULT / "entities" / f"{ent}.md").is_file():
            fail(f"missing key entity note: entities/{ent}.md")

    # --- assemble my-context.md ------------------------------------------
    doc = f"""# Context profile - Fadi

_Generated from a local Claude Code session vault ({total_sessions} sessions
across {len(projects)} projects). Used as LLM context for personalized guide
explanations. Do not expose to clients._

## Who I am

I'm Fadi, 15 years old, a 9th-grade student in Istanbul. I'm a self-taught
developer - no formal CS training - and I learn by building real things. My
main project is **Vex**, a custom Electron-based desktop browser I've been
building from scratch. I work with AI coding tools daily and ship features
fast.

## Tech stack I work in

{chr(10).join(stack_lines)}

## Active projects

{chr(10).join(active)}

## Skill level signals

I've run **{total_sessions} Claude Code sessions**, {vex_sessions} of them on
Vex alone - I use Claude Code daily as my primary way of building software.
I'm comfortable with Electron renderer/main IPC patterns, webview lifecycle
management, keyboard-shortcut and fullscreen handling, front-end UI/theming
work, and reading large codebases to plan changes. I'm familiar with
multi-agent orchestration patterns (running parallel subagents for backlinking
tasks). I'm still **building fluency in Python tooling** (argparse, unittest,
feedparser-style scripts) and in deeper systems topics like DRM/VMP signing and
build pipelines - explain those more carefully. Assume I understand JavaScript,
HTML/CSS and Git well; don't over-explain those.

## Hardware & accounts

Windows 11 only - no Mac, no iPhone, so skip macOS/iOS-specific advice. I have
JetBrains Ultimate (IDEs) and GitHub Copilot on the **Free tier**. My projects
deploy to Cloudflare Workers and GitHub Pages.

## Workflow preferences

I run **two AI assistants side by side**: Claude Code for agentic multi-file
work, and Copilot Chat for quick inline help. In Claude Code I use the
`!git push` escape to run git myself. I strongly prefer **direct, honest
feedback over hedging** - tell me when something is a bad idea, point out
tradeoffs plainly, and don't pad answers with marketing language.

## Goals

Ship features fast, but also learn good engineering practices along the way -
testing, clean structure, sensible architecture. I want my work to be
production-quality, not just working demos. When you explain something to me,
connect it to what I'm already building and be concrete about what I'd
actually do next.
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    words = len(doc.split())
    print(f"Wrote {OUT}")
    print(f"  {words} words, {len(doc)} chars")
    print(f"  sources: {total_sessions} sessions, {len(tool_slugs)} tool notes, "
          f"{len(active)} active projects")
    if not 250 <= words <= 600:
        print(f"  WARNING: word count {words} outside the 300-500 target band")


if __name__ == "__main__":
    main()

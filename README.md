# Claude Code Command Center - toolkit

Turns your local Claude Code session history into a searchable, backlinked
Obsidian vault. Based on *Claude Code Command Center* by Alex Freedman.

This repository holds the **tooling**, not the vault. Claude Code stores its
session transcripts as JSONL files under `~/.claude/projects/` on the machine
you run it on. That data never leaves your machine - you run these scripts
locally and the generated `vault/` is `.gitignore`d.

> **Why a toolkit and not a finished vault?** This repo was built in a cloud
> (web) Claude Code session, which runs in an ephemeral container with no
> access to your local `~/.claude/projects/`. The scripts are cross-platform
> (`Path.home()` resolves the right location on Windows/macOS/Linux), so you
> clone this repo on your own machine and run the stages there.

## Requirements

- Python 3.9+ (no third-party packages)
- Claude Code installed locally, with existing session history
- Claude Code CLI for the Stage 3 backlink run

## Stages

Run them in order; each is verifiable before the next.

### Stage 1 - Discovery

Report how much history you have before exporting anything.

```sh
python export.py --discover
```

Reports JSONL file count, project folders, total size, oldest/newest file.
If the corpus exceeds 5 GB it prints a warning - review before Stage 3.

### Stage 2 - Export to a markdown vault

```sh
python export.py --out vault
```

Walks `~/.claude/projects/`, parses every `.jsonl`, and writes one markdown
file per session. Sessions are grouped by their `cwd` field so worktrees of
the same project collapse together. Tool results are capped at 4000 chars and
tool calls are wrapped in collapsible `<details>` blocks. Produces:

```
vault/
├── README.md            project index
├── TOP-TOPICS.md         placeholder until Stage 3
├── projects/<name>/
│   ├── _project.md       rollup with a sortable session table
│   ├── sessions/YYYY-MM-DD_*.md
│   └── subagents/*.md    linked back to their parent session
├── topics/   tools/   entities/   (empty until Stage 3)
└── _build/reports/       (filled by Stage 3 agents)
```

### Stage 2.5 - Secret scan (do not skip)

```sh
python secret_scan.py --vault vault
```

Scans every markdown file for API keys, tokens, JWTs and PEM private keys,
replaces each with `<REDACTED:type>`, and writes `SECRETS-REDACTED.md` with
per-file counts (never the secrets themselves). Use `--dry-run` to preview.
Stop and review if it finds more than 50 matches.

### Stage 3 - Backlink with 10 parallel subagents

See [`STAGE3_BACKLINK.md`](STAGE3_BACKLINK.md) for the prompt to paste into
Claude Code. The agents extract topics, tools and entities per session and
emit JSON reports; they never write hub pages directly. Then:

```sh
python consolidate.py --vault vault
```

reads the 10 reports and atomically generates the `topics/`, `tools/` and
`entities/` hub pages plus the `TOP-TOPICS.md` leaderboard.

### Stage 4 - Install the recall skill

The `claude-brain` skill makes Claude Code auto-consult the vault *before*
responding to project work - but only when you ask for it.

**What it does.** When your message contains a recall trigger phrase, the
skill activates and Claude reads vault history before answering:

| Trigger phrase | Example |
|----------------|---------|
| `let's work on` | "let's work on Vex" |
| `last time` | "what was I doing last time on crux" |
| `continue with` | "continue with the theme system" |
| `check my brain` | "check my brain for the playwright audit" |
| `what did we do on` | "what did we do on system32" |
| `remind me about` | "remind me about the export pipeline" |

On a trigger, Claude follows a fixed read protocol: `vault/README.md` to
resolve the project -> that project's `_project.md` rollup -> the 3 most
recent session files -> any named topic/tool/entity hub pages. It is
**read-only** (never writes to the vault), **budget-capped** (~10,000 tokens
per session start), and **fails silent** - if the vault is missing or
corrupt, Claude just works normally with no error.

Without a trigger phrase, the skill stays dormant and Claude behaves as usual.

**Install.** The skill lives at `~/.claude/skills/claude-brain/SKILL.md`
(Windows: `C:\Users\<you>\.claude\skills\claude-brain\SKILL.md`). A
version-controlled copy is kept in this repo at
[`skills/claude-brain/SKILL.md`](skills/claude-brain/SKILL.md). To install or
re-install, copy that file into your `~/.claude/skills/claude-brain/`
directory and start a new Claude Code session.

The skill references the vault by absolute path. If your vault is not at
`C:\Users\USER\IdeaProjects\ClaudeCode-Brain\vault\`, edit the path in your
installed `SKILL.md`.

**Verify it is installed.**

```sh
claude /skills list
```

`claude-brain` should appear in the list. You can also confirm the file
exists at `~/.claude/skills/claude-brain/SKILL.md`.

**Manual test.** Start a new Claude Code session in any folder and type a
trigger, e.g. `let's continue with Vex`. Claude should open with a recap of
Vex's recent work (drawn from `projects/vex/_project.md` and recent sessions)
instead of asking you to re-explain the project. If the brain is not
consulted, the test fails - re-check the install and trigger wording.

**Uninstall.** Delete the skill directory and start a new session:

```sh
rm -r ~/.claude/skills/claude-brain      # macOS/Linux
Remove-Item -Recurse ~/.claude/skills/claude-brain   # PowerShell
```

The repo copy under `skills/` is just for version control - removing it is
optional and does not affect an installed skill.

### Stage 5 - Refresh the brain (manual)

Once the skill is installed, keep the vault current with one command:

```sh
python sync-vault.py
```

This runs `export.py` (re-export history), then `secret_scan.py` (redact
secrets), then `consolidate.py` (rebuild hub pages). It is a **manual
command** - deliberately not a cron job. The `consolidate.py` step only runs
if Stage 3 backlink reports exist under `vault/_build/reports/`; otherwise it
is skipped and existing hub pages are left untouched (re-run Stage 3 to
regenerate them).

## Safety

- `vault/` and `_build/` are git-ignored - your history is never committed.
- Always run Stage 2.5 before sharing or syncing the vault anywhere.

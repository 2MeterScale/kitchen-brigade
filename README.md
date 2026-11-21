# kitchen-brigade

A Claude Code skill for projects where work is handed to subagents again and again.

Spawning a fresh agent per job means every agent rediscovers the same tooling, know-how evaporates, and agents undo each other's work. This skill sets up **standing roles ("stations")**: the same kind of work always goes to the same role, each role keeps a notebook, and notebooks are **indexed and searched instead of re-read**.

The skill text is written in Japanese. It works for any kind of project (code, writing, research, design, video).

## What is in it

- `skills/kitchen-brigade/SKILL.md` — the method: role types, what files to place, how to hand off work, how to reorganise roles, how to keep agent-to-agent traffic cheap.
- `skills/kitchen-brigade/templates/` — starting files for the roster, the shared rules, a station definition and a notebook.
- `skills/kitchen-brigade/scripts/` — small tools, Python standard library only:
  - `notes.py` — notebooks as an index plus one note per topic (`recall`, `show`, `add`, `split`, `stats`). The notes folder opens as an Obsidian vault.
  - `notesplit.py`, `textrank.py` — used by `notes.py`.
  - `codemap.py` — where a declaration is and which lines it spans, so agents read a range, not a whole file (Swift out of the box; add a regular expression for other languages).

## Install

Copy the skill folder into your Claude Code skills directory.

macOS / Linux:

```sh
git clone https://github.com/<owner>/kitchen-brigade.git
cp -R kitchen-brigade/skills/kitchen-brigade ~/.claude/skills/
```

Windows (PowerShell):

```powershell
git clone https://github.com/<owner>/kitchen-brigade.git
Copy-Item -Recurse kitchen-brigade\skills\kitchen-brigade "$env:USERPROFILE\.claude\skills\"
```

Then, in a project, ask Claude Code to set up a kitchen ("厨房を組んで" / "set up stations for this project"). The skill tells it to copy the four scripts into `Tools/kitchen/` of the project.

Requires Python 3.9 or newer for the scripts. No network, no packages.

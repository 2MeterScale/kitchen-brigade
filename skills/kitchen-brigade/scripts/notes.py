#!/usr/bin/env python3
"""帳面を「索引（MEMORY.md）＋ 話題ごとの札（notes/*.md）」にして、必要な札だけ引く。標準ライブラリだけ。
  notes.py recall "<語>" [--role r | --all] [-k 5]   札を探す（小さい出力）
  notes.py show <path|slug> [--lines a-b]            札を読む
  notes.py add <role> --title T --tags a,b [--hook H] < 本文   札を足し、索引に一行足す
  notes.py split <role|--all>                         古い形の MEMORY.md や横のファイルを札にする（何度走らせてもよい）
  notes.py reindex <role>                             札から索引を作り直す
  notes.py stats                                      起動で読む量と札の量
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textrank  # noqa: E402


def find_root():
    env = os.environ.get("KITCHEN_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


ROOT = find_root()
MEM = ROOT / ".claude" / "agent-memory"
INDEX_LINE = re.compile(r"^- \[(?P<title>.*?)\]\(notes/(?P<slug>[^)]+?)\.md\)(?: — (?P<hook>.*))?$")
MAX_INDEX_LINES = 60
HOOK_LEN = 70
FIXED_LINE = "索引だけ。中身は `notes.py recall \"<語>\" --role {role}` で探し、`notes.py show <札>` で読む。書くときは `notes.py add`。"


def today():
    return datetime.date.today().isoformat()


# ---------- 札の読み書き ----------
def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta = {}
    for raw in text[4:end].split("\n"):
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if not m:
            continue
        val = m.group(3).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[m.group(2)] = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
        elif val[:1] in "\"'" and val[-1:] == val[:1] and len(val) >= 2:
            meta[m.group(2)] = val[1:-1].replace('\\"', '"')
        else:
            meta[m.group(2)] = val
    return meta, text[end + 4:].lstrip("\n")


def quote(value):
    return '"' + str(value).replace('"', '\\"') + '"'


def render_note(meta, body):
    first = ["title", "date", "tags", "status", "hook", "indexed", "source"]
    lines = ["---"]
    for k in first + [k for k in meta if k not in first]:
        v = meta.get(k)
        if v in (None, "", []):
            continue
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        elif k in ("date", "status", "indexed"):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {quote(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.strip("\n") + "\n"


def read_note(path):
    meta, body = parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    meta.setdefault("title", Path(path).stem)
    meta.setdefault("status", "current")
    return meta, body


def role_dirs():
    return sorted(p for p in MEM.iterdir() if p.is_dir()) if MEM.exists() else []


def role_notes(role):
    d = MEM / role / "notes"
    return sorted(d.glob("*.md")) if d.exists() else []


def slugify(text, taken=()):
    base = re.sub(r"[（(][^）)]*[）)]", "", text) or text
    base = re.sub(r"[\\/:*?\"<>|#^\[\]\s、。，,.]+", "-", base).strip("-")[:40].strip("-") or "note"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def first_line_hook(body):
    out = ""
    for raw in body.split("\n"):
        line = re.sub(r"[*`]", "", raw).strip()
        line = re.sub(r"^(- |\d+\. |#+ )", "", line)
        if line and line != "---":
            out = f"{out} {line}".strip()
            if len(out) >= 25:
                break
    return out[:HOOK_LEN]


# ---------- 索引 ----------
def index_text(role):
    entries = []
    for p in role_notes(role):
        meta, body = read_note(p)
        if meta.get("indexed") == "false":
            continue
        hook = meta.get("hook") or first_line_hook(body)
        entries.append((meta.get("date", ""), meta["title"], p.stem, hook, meta.get("status")))
    entries.sort(key=lambda e: (e[0], e[1]), reverse=True)
    lines = [f"# {role} の帳面（索引）", "", FIXED_LINE.format(role=role), ""]
    for _, title, slug, hook, status in entries[:MAX_INDEX_LINES]:
        mark = "（古い）" if status == "superseded" else ""
        lines.append(f"- [{title}](notes/{slug}.md){' — ' + mark + hook if hook or mark else ''}")
    if len(entries) > MAX_INDEX_LINES:
        lines.append(f"- …ほか {len(entries) - MAX_INDEX_LINES} 件は recall で探す")
    return "\n".join(lines) + "\n"


def reindex(role):
    (MEM / role).mkdir(parents=True, exist_ok=True)
    (MEM / role / "MEMORY.md").write_text(index_text(role), encoding="utf-8")


# ---------- 引く ----------
def load_corpus(roles):
    docs, info = {}, {}
    for role in roles:
        for p in role_notes(role):
            meta, body = read_note(p)
            tags = meta.get("tags", [])
            head = f"{meta['title']} {meta.get('hook', '')} {' '.join(tags) if isinstance(tags, list) else tags}"
            key = str(p)
            docs[key] = textrank.doc_tokens(head + " " + head + "\n" + body)
            info[key] = (role, meta, body)
    return docs, info


def short_path(path):
    p = Path(path)
    return f"{p.parent.parent.name}/{p.stem}"


def cmd_recall(args):
    roles = [args.role] if args.role else [d.name for d in role_dirs()]
    docs, info = load_corpus(roles)
    if not docs:
        print("札がありません。`notes.py split <role>` を先に。")
        return 1
    weights = textrank.query_weights(args.query)
    bm = textrank.Bm25(docs)
    ranked = []
    for score, key in bm.rank(weights, max(args.k * 3, 15)):
        status = info[key][1].get("status", "current")
        ranked.append((score * (0.5 if status == "superseded" else 1.0), key))
    ranked.sort(key=lambda s: -s[0])
    if not ranked:
        print("見つかりません。語を変えるか `codemap.py where` を。")
        return 0
    for _, key in ranked[: args.k]:
        _, meta, body = info[key]
        flag = " [古い]" if meta.get("status") == "superseded" else ""
        print(f"{short_path(key)} | {meta['title'][:40]} | {meta.get('date', '-')}{flag}")
        body_lines = body.split("\n")
        lines = [(textrank.line_score(ln, weights, bm.idf), i + 1, ln.strip()) for i, ln in enumerate(body_lines) if ln.strip()]
        for _s, no, ln in sorted((x for x in lines if x[0] > 0), key=lambda x: -x[0])[:2]:
            print(f"  L{no}: {ln[:60]}")
    return 0


def resolve_note(ref, role=None):
    p = Path(ref)
    if p.suffix == ".md" and p.exists():
        return p
    slug = p.stem if p.suffix == ".md" else ref
    roles = [role] if role else [d.name for d in role_dirs()]
    hits = [MEM / r / "notes" / f"{slug}.md" for r in roles if (MEM / r / "notes" / f"{slug}.md").exists()]
    if not hits and "/" in ref:
        r, _, s = ref.partition("/")
        cand = MEM / r / "notes" / f"{s.removesuffix('.md')}.md"
        hits = [cand] if cand.exists() else []
    if not hits:
        raise SystemExit(f"札が見つかりません: {ref}")
    return hits[0]


def cmd_show(args):
    path = resolve_note(args.ref, args.role)
    lines = path.read_text(encoding="utf-8").split("\n")
    if args.lines:
        a, _, b = args.lines.partition("-")
        lo, hi = int(a), int(b or a)
        print("\n".join(f"{i}: {ln}" for i, ln in enumerate(lines[lo - 1: hi], lo)))
    else:
        print("\n".join(lines))
    return 0


def cmd_add(args):
    import notesplit
    notesplit.split_role(args.role, quiet=True)
    body = sys.stdin.read().strip()
    if not body:
        raise SystemExit("本文を標準入力から渡してください。")
    d = MEM / args.role / "notes"
    d.mkdir(parents=True, exist_ok=True)
    slug = slugify(args.title, {p.stem for p in d.glob("*.md")})
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    meta = {"title": args.title, "date": args.date or today(), "tags": [args.role] + [t for t in tags if t != args.role],
            "status": "current", "hook": args.hook or first_line_hook(body)}
    (d / f"{slug}.md").write_text(render_note(meta, body), encoding="utf-8")
    for old in args.supersedes or []:
        mark_superseded(args.role, old)
    reindex(args.role)
    print(f"書きました: {args.role}/notes/{slug}.md")
    return 0


def mark_superseded(role, slug):
    p = MEM / role / "notes" / f"{slug}.md"
    meta, body = read_note(p)
    p.write_text(render_note({**meta, "status": "superseded"}, body), encoding="utf-8")


def cmd_stats(_):
    print(f"{'role':<16}{'index(B)':>9}{'notes':>6}{'notes(B)':>10}{'old files(B)':>13}")
    totals = [0, 0, 0, 0]
    for d in role_dirs():
        idx = (d / "MEMORY.md").stat().st_size if (d / "MEMORY.md").exists() else 0
        notes = role_notes(d.name)
        nb = sum(p.stat().st_size for p in notes)
        old = sum(p.stat().st_size for p in d.rglob("*.md") if p.name != "MEMORY.md" and "notes" not in p.relative_to(d).parts)
        print(f"{d.name:<16}{idx:>9}{len(notes):>6}{nb:>10}{old:>13}")
        totals = [totals[0] + idx, totals[1] + len(notes), totals[2] + nb, totals[3] + old]
    print(f"{'total':<16}{totals[0]:>9}{totals[1]:>6}{totals[2]:>10}{totals[3]:>13}")
    return 0


def cmd_split(args):
    import notesplit
    roles = [d.name for d in role_dirs()] if args.all else [args.role]
    for r in roles:
        notesplit.split_role(r)
    return 0


def cmd_reindex(args):
    reindex(args.role)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recall")
    r.add_argument("query")
    r.add_argument("--role")
    r.add_argument("--all", action="store_true")
    r.add_argument("-k", type=int, default=5)
    r.set_defaults(fn=cmd_recall)
    s = sub.add_parser("show")
    s.add_argument("ref")
    s.add_argument("--role")
    s.add_argument("--lines")
    s.set_defaults(fn=cmd_show)
    a = sub.add_parser("add")
    a.add_argument("role")
    a.add_argument("--title", required=True)
    a.add_argument("--tags", default="")
    a.add_argument("--hook")
    a.add_argument("--date")
    a.add_argument("--supersedes", nargs="*")
    a.set_defaults(fn=cmd_add)
    sp = sub.add_parser("split")
    sp.add_argument("role", nargs="?")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_split)
    ri = sub.add_parser("reindex")
    ri.add_argument("role")
    ri.set_defaults(fn=cmd_reindex)
    st = sub.add_parser("stats")
    st.set_defaults(fn=cmd_stats)
    args = ap.parse_args(argv)
    if args.cmd == "split" and not (args.role or args.all):
        ap.error("role か --all が要ります")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

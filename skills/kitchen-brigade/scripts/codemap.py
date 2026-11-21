#!/usr/bin/env python3
"""Swift のコードの地図。ファイルを丸ごと読まずに、宣言と行を探す。標準ライブラリだけ。
  codemap.py build                  地図を作り直す（Swift が新しければ find などが自動でやる）
  codemap.py find <名前> [--refs]   宣言（と使っている行）。大小文字と部分一致はゆるい
  codemap.py outline <path>         ファイルの宣言を行の範囲つきで。続きは Read の offset/limit で
  codemap.py where "<語>"           どのファイルが扱うか（日本語でも英語でも）
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textrank  # noqa: E402

CAP = 30
SKIP_DIRS = {".build", ".git", "DerivedData", "Pods", "node_modules", "worktrees", "xcuserdata", "checkouts"}
MODS = r"(?:(?:public|private|fileprivate|internal|open|static|final|override|mutating|nonmutating|lazy|indirect|class|convenience|required|nonisolated|weak|unowned|package|dynamic|prefix|postfix|distributed)\s+)*"
DECL = re.compile(rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*{MODS}(struct|class|enum|actor|protocol|extension|typealias|func|init|var|let|case|subscript|macro)\b\s*(.*)$")
NAME = re.compile(r"[A-Za-z_][\w.]*|`[^`]+`|[^\sA-Za-z_(<]+")
TYPE_KINDS = {"struct", "class", "enum", "actor", "protocol", "extension"}


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
CACHE = ROOT / ".claude" / "cache" / "codemap.json"


def swift_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        out.extend(Path(dirpath, f) for f in filenames if f.endswith(".swift"))
    return sorted(out)


def strip_noise(line, state):
    """文字列とコメントを消した行を返す（波かっこを数えるため）。state は複数行の印。"""
    out, i = [], 0
    while i < len(line):
        if state["block"]:
            j = line.find("*/", i)
            if j < 0:
                return "".join(out)
            state["block"], i = False, j + 2
        elif state["multi"]:
            j = line.find('"""', i)
            if j < 0:
                return "".join(out)
            state["multi"], i = False, j + 3
        elif line.startswith("//", i):
            break
        elif line.startswith("/*", i):
            state["block"], i = True, i + 2
        elif line.startswith('"""', i):
            state["multi"], i = True, i + 3
        elif line[i] == '"':
            j = i + 1
            while j < len(line) and line[j] != '"':
                j += 2 if line[j] == "\\" else 1
            i = j + 1
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def decl_name(kind, rest):
    if kind == "init":
        return "init"
    if kind == "subscript":
        return "subscript"
    m = NAME.match(rest.strip().lstrip("(").strip()) if kind in ("var", "let") else NAME.match(rest)
    return m.group(0).strip("`") if m else "?"


def signature(lines, idx):
    sig = lines[idx].strip()
    j = idx
    while sig.count("(") > sig.count(")") and j + 1 < len(lines) and j - idx < 6:
        j += 1
        sig += " " + lines[j].strip()
    sig = re.sub(r"\s*\{.*$", "", sig)
    return sig[:140]


def first_doc(lines):
    for raw in lines[:60]:
        s = raw.strip()
        if DECL.match(raw) and not s.startswith("//"):
            break
        m = re.match(r"^///?\s*(.*\S)", s)
        if m and not re.match(r"^(MARK|swiftlint|Created by|Copyright|swift-tools-version)", m.group(1)):
            return m.group(1)[:120]
    return ""


def scan(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    state = {"block": False, "multi": False}
    stack, decls = [], []
    pending, open_parens = None, 0
    for no, raw in enumerate(lines, 1):
        clean = strip_noise(raw, state)
        m = DECL.match(clean)
        in_body = bool(stack) and stack[-1][0] == "body"
        if m and not in_body:
            kind, rest = m.groups()
            if not (kind == "case" and not (stack and stack[-1][0] == "enum")):
                decl = {"kind": kind, "name": decl_name(kind, rest), "sig": signature(lines, no - 1), "line": no, "end": no,
                        "depth": sum(1 for s in stack if s[0] in TYPE_KINDS or s[0] == "enum")}
                decls.append(decl)
                pending, open_parens = decl, 0
        if pending is not None:
            open_parens += clean.count("(") - clean.count(")")
        for ch in clean:
            if ch == "{":
                if pending is not None:
                    stack.append(("body" if pending["kind"] not in TYPE_KINDS else pending["kind"], pending))
                    pending = None
                else:
                    stack.append(("other", None))
            elif ch == "}" and stack:
                _, d = stack.pop()
                if d is not None:
                    d["end"] = no
        if pending is not None and open_parens <= 0 and not clean.rstrip().endswith((",", "->", "where")):
            pending = None
    return {"lines": len(lines), "doc": first_doc(lines), "decls": decls}


def build(force=False):
    cache = {}
    if CACHE.exists() and not force:
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    files, fresh = {}, 0
    for p in swift_files():
        rel = p.relative_to(ROOT).as_posix()
        st = p.stat()
        stamp = [st.st_mtime_ns, st.st_size]
        old = cache.get("files", {}).get(rel)
        if old and old["stamp"] == stamp:
            files[rel] = old
            continue
        files[rel] = {"stamp": stamp, **scan(p)}
        fresh += 1
    if fresh or len(files) != len(cache.get("files", {})) or force:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"files": files}, ensure_ascii=False), encoding="utf-8")
    return files, fresh


def match_rank(query, name):
    q, n = query.lower(), name.lower()
    if q == n:
        return 0
    if n.startswith(q):
        return 1
    return 2 if q in n else None


def cmd_find(args):
    files, _ = build()
    rows = []
    for rel, f in files.items():
        for d in f["decls"]:
            r = match_rank(args.name, d["name"])
            if r is not None:
                rows.append((r, rel, d))
    rows.sort(key=lambda r: (r[0], r[1], r[2]["line"]))
    out = [f"{rel}:{d['line']}  {d['sig']}" for _, rel, d in rows]
    if args.refs:
        out += refs(args.name, files, {(rel, d["line"]) for _, rel, d in rows})
    emit(out)
    return 0


def refs(name, files, decl_lines):
    pat = re.compile(rf"\b{re.escape(name)}\b")
    out = []
    for rel in files:
        for no, line in enumerate((ROOT / rel).read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            if pat.search(line) and (rel, no) not in decl_lines:
                out.append(f"{rel}:{no}  ref  {line.strip()[:100]}")
    return out


def emit(lines):
    if not lines:
        print("見つかりません。`codemap.py where \"<語>\"` で言葉から探す。")
        return
    print("\n".join(lines[:CAP]))
    if len(lines) > CAP:
        print(f"…ほか {len(lines) - CAP} 件（名前を絞る）")


def resolve_path(files, arg):
    arg = arg.removeprefix("./")
    if arg in files:
        return arg
    hits = [r for r in files if r.endswith("/" + arg) or r.endswith(arg)]
    return hits[0] if len(hits) == 1 else (sorted(hits, key=len)[0] if hits else None)


def cmd_outline(args):
    files, _ = build()
    rel = resolve_path(files, args.path)
    if not rel:
        print(f"Swift のファイルが見つかりません: {args.path}")
        return 1
    f = files[rel]
    print(f"{rel}  {f['lines']} 行  {f['doc']}")
    shown = 0
    for d in f["decls"]:
        if d["kind"] in ("var", "let", "case") and not args.all and d["depth"] > 1:
            continue
        rng = f"{d['line']}-{d['end']}" if d["end"] > d["line"] else str(d["line"])
        print(f"{'  ' * d['depth']}L{rng}  {d['sig'][:100]}")
        shown += 1
        if shown >= 120:
            print("…ほか（--all で全部ではなく、型名で find する）")
            break
    return 0


def cmd_where(args):
    files, _ = build()
    docs = {}
    for rel, f in files.items():
        names = " ".join(d["name"] for d in f["decls"] if d["kind"] not in ("var", "let", "case"))
        docs[rel] = textrank.doc_tokens(f"{rel} {rel} {f['doc']} {f['doc']} {names}")
    weights = textrank.query_weights(args.query)
    bm = textrank.Bm25(docs, b=0.3)
    ranked = bm.rank(weights, args.k)
    if not ranked:
        print("見つかりません。語を変えるか、`notes.py recall` を。")
        return 0
    for _, rel in ranked:
        f = files[rel]
        hits = [d["name"] for d in f["decls"] if d["kind"] not in ("var", "let", "case") and textrank.line_score(d["name"], weights, bm.idf) > 0][:4]
        print(f"{rel} ({f['lines']}行) {f['doc'][:50]}" + (f"  [{', '.join(hits)}]" if hits else ""))
    return 0


def cmd_build(args):
    files, fresh = build(force=True)
    print(f"{len(files)} ファイル、{sum(len(f['decls']) for f in files.values())} 宣言 → {CACHE.relative_to(ROOT)}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    f = sub.add_parser("find")
    f.add_argument("name")
    f.add_argument("--refs", action="store_true")
    f.set_defaults(fn=cmd_find)
    o = sub.add_parser("outline")
    o.add_argument("path")
    o.add_argument("--all", action="store_true")
    o.set_defaults(fn=cmd_outline)
    w = sub.add_parser("where")
    w.add_argument("query")
    w.add_argument("-k", type=int, default=6)
    w.set_defaults(fn=cmd_where)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

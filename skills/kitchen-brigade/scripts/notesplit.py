"""古い形の帳面（`## ` の節だらけの MEMORY.md と、横にあるファイル）を札にする。何度走らせても同じ結果で、中身は一行も失わない。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notes as N  # noqa: E402

OLD_LINK = re.compile(r"^- \[(?P<title>.*?)\]\((?P<target>[^)]+\.md)\)(?:\s*[—-]+\s*(?P<hook>.*))?$")
ISO_DATE = re.compile(r"20\d\d-\d\d-\d\d")
SUPERSEDED_WORDS = ("古い", "外れていた")


def norm(text):
    return re.sub(r'[\s\\"]+', "", text)


def make_rewriter(mapping):
    """横のファイル名（`flicker.md`）を札への参照（[[flicker]]）に直す。"""
    if not mapping:
        return lambda text: text
    keys = "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True))
    link = re.compile(rf"\]\((?:\./)?({keys})\)")
    tick = re.compile(rf"`({keys})`")
    bare = re.compile(rf"(?<![\w/\[(-])({keys})")

    def rewrite(text):
        text = link.sub(lambda m: f"]({mapping[m.group(1)]}.md)", text)
        text = tick.sub(lambda m: f"[[{mapping[m.group(1)]}]]", text)
        return bare.sub(lambda m: f"[[{mapping[m.group(1)]}]]", text)
    return rewrite


def parse_memory(text, role, sibling_keys):
    """MEMORY.md -> (前書きの行, 節[(見出し, 本文の行)], 古い索引の行 {対象: (題, 一言)})。"""
    pre, sections, links, fence, current = [], [], {}, False, None
    generated = {f"# {role} の帳面（索引）", N.FIXED_LINE.format(role=role)}
    for raw in text.split("\n"):
        if raw.lstrip().startswith("```"):
            fence = not fence
        if not fence and raw.startswith("## "):
            current = (raw[3:].strip(), [])
            sections.append(current)
            continue
        if current is not None:
            current[1].append(raw)
            continue
        m = OLD_LINK.match(raw)
        target = m.group("target").removeprefix("./") if m else None
        if not raw.strip() or N.INDEX_LINE.match(raw) or raw.startswith("- …ほか") or raw in generated:
            continue
        if target in sibling_keys:
            links[target] = (m.group("title"), (m.group("hook") or "").strip())
            continue
        pre.append(raw)
    return pre, sections, links


def find_date(*texts):
    for t in texts:
        m = ISO_DATE.search(t)
        if m:
            return m.group(0)
    return N.today()


def sibling_files(d):
    return sorted(p for p in d.rglob("*.md") if p.name != "MEMORY.md" and "notes" not in p.relative_to(d).parts)


def sibling_base_slug(rel):
    parts = list(rel.parent.parts) + [rel.stem]
    return "-".join(parts).lower() if len(parts) > 1 else rel.stem


def all_text(role):
    return "".join(p.read_text(encoding="utf-8") for p in N.role_notes(role))


def split_role(role, quiet=False):
    d = N.MEM / role
    if not d.exists():
        raise SystemExit(f"持ち場の帳面がありません: {d}")
    notes_dir = d / "notes"
    notes_dir.mkdir(exist_ok=True)
    sibs = sibling_files(d)
    existing = {p.stem: N.read_note(p) for p in N.role_notes(role)}
    taken = set(existing)
    by_source = {m.get("source"): s for s, (m, _) in existing.items() if m.get("source")}

    # 横のファイルの札の名前を先に決める（本文の参照を直すため）
    slug_of, mapping = {}, {}
    for p in sibs:
        rel = p.relative_to(d)
        base = sibling_base_slug(rel)
        slug_of[rel.as_posix()] = by_source.get(rel.as_posix()) or N.slugify(base, taken)
        taken.add(slug_of[rel.as_posix()])
    basenames = [Path(k).name for k in slug_of]
    for rel, slug in slug_of.items():
        mapping[rel] = slug
        if basenames.count(Path(rel).name) == 1:
            mapping[Path(rel).name] = slug
    rewrite = make_rewriter(mapping)

    mem_path = d / "MEMORY.md"
    mem_text = mem_path.read_text(encoding="utf-8") if mem_path.exists() else ""
    pre, sections, links = parse_memory(mem_text, role, set(slug_of))
    sources = [(p.relative_to(d).as_posix(), p.read_text(encoding="utf-8")) for p in sibs]

    corpus = norm(all_text(role))
    written = {"new": 0, "skipped": 0}
    titles = {m["title"]: s for s, (m, _) in existing.items()}

    def emit(title, body, extra, base_slug, source):
        nonlocal corpus
        body = rewrite(body.strip("\n"))
        if not body.strip() or norm(body) in corpus:
            written["skipped"] += 1
            return
        if title in titles:
            old_slug = titles[title]
            old_meta, old_body = N.read_note(notes_dir / f"{old_slug}.md")
            if norm(old_body) in norm(body):
                (notes_dir / f"{old_slug}.md").write_text(N.render_note({**old_meta, "status": "superseded"}, old_body), encoding="utf-8")
            title = f"{title}（改訂）"
        slug = slug_of.get(source)
        if slug is None or slug in existing:
            slug = N.slugify(title, taken)
        taken.add(slug)
        status = "superseded" if any(w in title for w in SUPERSEDED_WORDS) else "current"
        meta = {"title": title, "date": find_date(title, body), "tags": [role], "status": status, "source": source}
        meta.update(extra)
        meta["tags"] = list(dict.fromkeys([role] + list(extra.get("tags", []))))
        (notes_dir / f"{slug}.md").write_text(N.render_note(meta, body), encoding="utf-8")
        titles[title] = slug
        corpus += norm(N.render_note(meta, body))
        written["new"] += 1

    # 前書きと節
    pre_lines = list(pre)
    for heading, lines in sections:
        if "".join(lines).strip():
            emit(heading, "\n".join(lines), {"tags": ["section"]}, heading, f"MEMORY.md#{heading}")
        else:
            pre_lines.append(f"## {heading}")
    if "".join(pre_lines).strip():
        emit("前書き", "\n".join(pre_lines), {"indexed": "false", "tags": ["preamble"]}, "preamble", "MEMORY.md#preamble")

    # 横のファイル
    for rel, text in sources:
        fm, body = N.parse_frontmatter(text)
        h1 = re.search(r"^# (.+)$", body, re.M)
        link_title, link_hook = links.get(rel, links.get(Path(rel).name, (None, "")))
        title = link_title or fm.get("title") or (h1.group(1).strip() if h1 else None) or fm.get("name") or Path(rel).stem
        in_subdir = "/" in rel
        extra = {k: v for k, v in fm.items() if k not in ("title", "date", "tags", "status", "hook", "indexed", "source") and v}
        extra["tags"] = ["file"] + ([fm["type"]] if fm.get("type") else []) + (["study"] if in_subdir else [])
        extra["hook"] = rewrite(link_hook or fm.get("description", ""))
        if fm.get("date"):
            extra["date"] = fm["date"]
        if in_subdir and Path(rel).stem != "INDEX":
            extra["indexed"] = "false"
        emit(title, body, extra, sibling_base_slug(Path(rel)), rel)

    missing = lost_lines(role, sources, pre_lines, sections, links, rewrite)
    if missing:
        print(f"[{role}] 中身が札に残っていません。何も消さずに止めます。", file=sys.stderr)
        for m in missing[:10]:
            print("  失われた行:", m[:100], file=sys.stderr)
        raise SystemExit(2)

    N.reindex(role)
    for p in sibs:
        p.unlink()
    for sub in sorted((x for x in d.rglob("*") if x.is_dir() and x != notes_dir), reverse=True):
        if not any(sub.iterdir()):
            sub.rmdir()
    if not quiet:
        print(f"{role}: 新しい札 {written['new']}、すでにあった {written['skipped']}、横のファイル {len(sibs)}")
    return written


def lost_lines(role, sources, pre_lines, sections, links, rewrite):
    """古い中身の行が、どれか一つの札にも無ければ返す。"""
    corpus = norm(all_text(role))
    checks = list(pre_lines)
    for heading, lines in sections:
        checks.append(heading)
        checks.extend(lines)
    for title, hook in links.values():
        checks.extend([title, hook])
    for _, text in sources:
        fm, body = N.parse_frontmatter(text)
        checks.extend(v for v in fm.values() if isinstance(v, str))
        checks.extend(body.split("\n"))
    missing = []
    for line in checks:
        n = norm(rewrite(line))
        if n and n not in corpus and n.lstrip("#") not in corpus:
            missing.append(line)
    return missing

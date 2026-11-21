"""小さな検索の部品。日本語は文字二つ組（bigram）、英数字は識別子ごとに数え、BM25 で順位をつける。標準ライブラリだけ。"""
import math
import re
from collections import Counter

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]+")
KANJI = re.compile(r"[㐀-䶿一-鿿]")
WORD = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9]+)?")
PARTS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
STOP_CJK_PAIRS = frozenset({"です", "ます", "する", "した", "して", "から", "こと", "れる", "ある", "いる"})


def is_identifier(word):
    return bool(re.search(r"[a-z][A-Z]|_|\.|\d", word)) and len(word) >= 3


def _parts(word):
    return PARTS.findall(word.replace("_", " ").replace(".", " "))


def ascii_tokens(text):
    out = []
    for w in WORD.findall(text):
        low = w.lower()
        out.append(low)
        for part in _parts(w):
            p = part.lower()
            if len(p) >= 2 and p != low:
                out.append(p)
    return out


def cjk_tokens(text, singles_only_if_alone):
    out = []
    for run in CJK.findall(text):
        if len(run) == 1:
            out.append(run)
            continue
        out.extend(p for p in (run[i:i + 2] for i in range(len(run) - 1)) if p not in STOP_CJK_PAIRS)
        if not singles_only_if_alone:
            out.extend(KANJI.findall(run))
    return out


def doc_tokens(text):
    return ascii_tokens(text) + cjk_tokens(text, False)


def query_weights(query):
    """検索語 -> {token: weight}。識別子の完全一致は重く数える。"""
    weights = {}
    for w in WORD.findall(query):
        low = w.lower()
        ident = is_identifier(w)
        weights[low] = max(weights.get(low, 0), 2.5 if ident else 1.0)
        for part in _parts(w):
            p = part.lower()
            if len(p) >= 2 and p != low:
                weights[p] = max(weights.get(p, 0), 0.6 if ident else 0.5)
    for tok in cjk_tokens(query, True):
        weights[tok] = max(weights.get(tok, 0), 1.0)
    return weights


class Bm25:
    def __init__(self, docs, k1=1.4, b=0.6):
        self.k1, self.b = k1, b
        self.tf = {i: Counter(toks) for i, toks in docs.items()}
        self.len = {i: max(1, len(t)) for i, t in docs.items()}
        self.avg = sum(self.len.values()) / max(1, len(self.len))
        df = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        n = max(1, len(self.tf))
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, doc_id, weights):
        tf, norm = self.tf[doc_id], 1 - self.b + self.b * self.len[doc_id] / self.avg
        total = 0.0
        for tok, w in weights.items():
            f = tf.get(tok)
            if f:
                total += w * self.idf.get(tok, 0) * f * (self.k1 + 1) / (f + self.k1 * norm)
        return total

    def rank(self, weights, limit):
        scored = [(self.score(i, weights), i) for i in self.tf]
        return sorted((s for s in scored if s[0] > 0), key=lambda s: -s[0])[:limit]


def line_score(line, weights, idf):
    toks = set(doc_tokens(line))
    return sum(w * idf.get(t, 0.5) for t, w in weights.items() if t in toks)

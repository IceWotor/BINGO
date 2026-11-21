"""Split the OCR words into term / definition entries.

Unlike terms.extract_terms (which works on a string), this keeps the Word
objects, so every definition gets its own slice of the page-level Detection.
The slice keeps the page-wide scores (surprisal z-scores, median gap, ...),
so a word is judged the same whether it is shown on the page or on a card.
"""
import re
from dataclasses import dataclass, replace

from .lm import norm_word
from .reconstruct import Detection

# "a." "B," "1." "12." at the start of a line. Any single letter, not just a-e,
# so a list with more than 5 items ('f.', 'g.', ...) is still recognized.
_MARKER = re.compile(r"^(?:[A-Za-z]|\d{1,2})[.,]$")
_DASH_CHARS = "-\u2014\u2013"

# term / definition separators, tried in order
_CUTS = (
    # "Term - definition"
    re.compile(r"^([A-Za-z0-9][A-Za-z0-9\s'\-]{2,40}?)\s+[-\u2014\u2013]+\s*(\S.*)$", re.S),
    # "Term-definition", "Term- definition"
    re.compile(r"^([A-Za-z0-9][A-Za-z0-9\s']{2,40}?)\s*[-\u2014\u2013]+\s*(\S.*)$", re.S),
    # "Term. Definition"
    re.compile(r"^([A-Z][A-Za-z0-9\s']{2,50}?)\.\s+([A-Z].*)$", re.S),
)


@dataclass
class Entry:
    term: str
    term_words: list
    def_words: list
    det: object          # Detection for the definition only (None if it is empty)


def _join(chunk):
    text, spans = "", []
    for w in chunk:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(w.text)))
        text += w.text
    return text, spans


def _find_cut(text):
    """-> (end of term, start of definition) as character offsets, or None."""
    lead = re.match(r"[^A-Za-z0-9]*", text).end()
    body = text[lead:]
    for pat in _CUTS:
        m = pat.match(body)
        if m:
            return lead + m.end(1), lead + m.start(2)
    return None


MAX_TERM_LINE_WORDS = 6   # a term-only line is a short label, not a sentence


def _line_cut(idxs, words):
    """Some books give the term its own OCR line, with the definition starting
    on the next line and no dash or period to mark the split ('Matter' / 'Matter
    is anything...'). -> index into idxs where the definition starts, or None."""
    if len(idxs) < 2:
        return None
    first_line = words[idxs[0]].line
    split = next((k for k, i in enumerate(idxs) if words[i].line != first_line), None)
    if not split or split > MAX_TERM_LINE_WORDS:
        return None
    if any(_is_sep(words[idxs[k]].text) for k in range(split)):
        return None   # a dash is already on this line; let _find_cut handle it
    return split


def _piece(wd, a, b):
    """A part of one OCR word (characters a..b), with proportional geometry."""
    n = max(len(wd.text), 1)
    return replace(wd, text=wd.text[a:b],
                   x=int(wd.x + wd.w * a / n), w=int(wd.w * (b - a) / n))


def _is_sep(t):
    return bool(t) and (not t.strip(_DASH_CHARS) or t[-1] in _DASH_CHARS)


def _entry_starts(words):
    """-> (indices of the first word of each entry, True if list markers were used)"""
    lines = {}
    for i, w in enumerate(words):
        lines.setdefault(w.line, []).append(i)
    marked = sorted(idxs[0] for idxs in lines.values()
                    if _MARKER.match(words[idxs[0]].text))
    if marked:
        return marked, True
    # no list markers: an entry starts at each line that holds a dash near its start
    dashed = sorted(idxs[0] for idxs in lines.values()
                    if any(_is_sep(words[i].text) for i in idxs[:6]))
    return dashed, False


def _sub_detection(items, det):
    """items = [(global word index, word, token)] -> Detection for just those words."""
    if not items:
        return None
    local = {gi: k for k, (gi, _, _) in enumerate(items)}
    # a gap before the first word is just the space the dash left, so skip it
    gaps = [replace(g, position=local[g.position])
            for g in det.gaps if local.get(g.position, 0) > 0]
    return Detection([it[1] for it in items], [it[2] for it in items],
                     gaps, det.stats, det.has_conf)


def _build(idxs, det):
    """-> (Entry or None, whether a term was found)"""
    if not idxs:
        return None, False
    words, toks = det.words, det.tokens
    text, spans = _join([words[i] for i in idxs])

    term_words, items, found = [], [], False

    # a short term-only OCR line is a stronger, more reliable signal than a stray
    # period inside the definition's own first sentence, so try it first
    split = _line_cut(idxs, words)
    if split is not None:
        found = True
        term_words = [words[i] for i in idxs[:split]]
        items = [(i, words[i], toks[i]) for i in idxs[split:]]
    else:
        cut = _find_cut(text)
        if cut is not None:
            found = True
            term_end, def_start = cut
            for i, (s, e) in zip(idxs, spans):
                w, t = words[i], toks[i]
                if e <= term_end:
                    term_words.append(w)
                elif s >= def_start:
                    items.append((i, w, t))
                else:
                    # the separator is glued to this word ("Term-definition", "-definition")
                    if s < term_end:
                        term_words.append(_piece(w, 0, term_end - s))
                    if def_start < e:
                        right = _piece(w, def_start - s, len(w.text))
                        # scores were computed for the glued word, so don't flag the half
                        items.append((i, right, replace(
                            t, word=right, norm=norm_word(right.text),
                            p_damage=0.0, flagged=False)))
        else:
            items = [(i, words[i], toks[i]) for i in idxs]

    term = re.sub(r"^[^A-Za-z0-9]+", "", " ".join(w.text for w in term_words)).strip()
    sub = _sub_detection(items, det)
    entry = Entry(term, term_words, [it[1] for it in items], sub)
    return entry, found


def split_entries(det):
    """Detection of the whole page -> list[Entry], in reading order."""
    words = det.words
    n = len(words)
    starts, marked = _entry_starts(words)

    if not starts:                       # nothing to split on: one entry, no term
        e, _ = _build(list(range(n)), det)
        return [e] if e else []

    entries = []
    if starts[0] > 0:                    # text before the first entry (a title?)
        e, ok = _build(list(range(starts[0])), det)
        if e and ok:                     # keep it only if it looks like term - definition
            entries.append(e)

    bounds = starts + [n]
    for s, t in zip(bounds, bounds[1:]):
        idxs = list(range(s, t))
        if marked:
            idxs = idxs[1:]              # drop the "1." / "a." marker
        e, _ = _build(idxs, det)
        if e:
            entries.append(e)
    return entries
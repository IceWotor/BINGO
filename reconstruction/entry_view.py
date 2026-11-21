"""Display logic for the Extracted Text page. Pure Python (no Kivy) so it can be tested.

An entry is shown as a term plus a definition made of "items": (text, kind) where kind is
  "plain"   normal word
  "mask"    flagged as damaged (purple pill)
  "severe"  flagged and very likely damaged (red pill), or a gap where words are missing
"""
SEVERE_AT = 0.8          # damage score at or above this is "severe" (red)


def esc(s):
    return str(s).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def term_masked(entry, det):
    """True if one of the term's words was flagged on the page-level damage check."""
    if det is None:
        return False
    for w in entry.term_words:
        i = getattr(w, "idx", -1)
        if 0 <= i < len(det.tokens) and det.words[i].text == w.text and det.tokens[i].flagged:
            return True
    return False


def definition_items(entry):
    """[(text, kind)] for the definition, with a pseudo-word where words are missing."""
    words = entry.def_words
    det = entry.det
    ok = det is not None and len(det.tokens) == len(words)
    toks = det.tokens if ok else [None] * len(words)
    gap_at = {g.position: g for g in det.gaps} if ok else {}
    items = []
    for i, w in enumerate(words):
        g = gap_at.get(i)
        if g:
            items.append(("missing %d" % g.est_words,
                          "severe" if g.p_gap >= SEVERE_AT else "mask"))
        t = toks[i]
        if t is not None and t.flagged:
            items.append((w.text, "severe" if t.p_damage >= SEVERE_AT else "mask"))
        else:
            items.append((w.text, "plain"))
    return items


def wrap_lines(items, width, measure, space, pad):
    """Greedy word wrap. -> (number of lines, width used on the last line)."""
    lines, used = 1, 0.0
    for text, kind in items:
        w = measure(text) + (pad if kind != "plain" else 0)
        if used == 0:
            used = w
        elif used + space + w > width:
            lines += 1
            used = w
        else:
            used += space + w
    return lines, used


def fit_items(items, width, measure, space, pad, max_lines, ellipsis_w):
    """Keep as many items as fit in max_lines (leaving room for '...').
    -> (items to show, True if something was cut)."""
    if wrap_lines(items, width, measure, space, pad)[0] <= max_lines:
        return items, False
    for m in range(len(items) - 1, 0, -1):
        lines, used = wrap_lines(items[:m], width, measure, space, pad)
        if lines <= max_lines and used + space + ellipsis_w <= width:
            return items[:m], True
    return items[:1], True


def markup(items, cut, color_hex):
    """-> (Kivy markup, {zone name: kind}). Flagged words sit in [ref=zN] tags; the row draws
    a pill behind each zone."""
    out, zones = [], {}
    for n, (text, kind) in enumerate(items):
        t = esc(text)
        if kind == "plain":
            out.append(t)
        else:
            name = "z%d" % n
            zones[name] = kind
            out.append("[ref=%s][color=%s]%s[/color][/ref]" % (name, color_hex, t))
    s = " ".join(out)
    return (s + " ...") if cut else s, zones

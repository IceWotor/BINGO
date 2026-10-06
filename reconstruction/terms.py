import re

MARK = re.compile(r"\{\{(\d+)\|([^}]*)\}\}")


def strip_markers(s):
    return MARK.sub(r"\2", s)


def split_into_chunks(text):
    pattern = re.compile(r'\n\s*(?:[a-eA-E][\.,]|\d{1,2}[\.,])\s+', re.MULTILINE)
    splits = [s.strip() for s in pattern.split(text) if s.strip()]
    if splits:
        first = strip_markers(splits[0])
        looks = (re.match(r'^[A-Z][A-Za-z\s]{2,50}?[-—–]', first) or
                 re.match(r'^[A-Z][A-Za-z\s]{2,50}?\.\s+[A-Z]', first))
        if not looks:
            splits = splits[1:]
    return splits or [text]


def split_term_definition(clean):
    t = re.sub(r'^[^A-Za-z]+', '', clean)
    m = re.match(r'^([A-Z][A-Za-z\s]{2,40}?)\s*[-—–]\s*(.+)$', t, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r'^([A-Z][A-Za-z\s]{2,50}?)\.\s+([A-Z].*)$', t, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def extract_terms(annotated, slots_by_id, default_conf):
    out = []
    for ch in split_into_chunks(annotated):
        ch = re.sub(r"\s*\n\s*", " ", ch)
        td = split_term_definition(strip_markers(ch))
        if not td:
            continue
        ids = [int(i) for i in re.findall(r"\{\{(\d+)\|", ch)]
        confs = [slots_by_id[i].recon_conf for i in ids if i in slots_by_id]
        conf = 100 * sum(confs) / len(confs) if confs else default_conf
        out.append({"term": td[0], "definition": td[1],
                    "confidence": int(round(conf)), "slot_ids": ids})
    return out
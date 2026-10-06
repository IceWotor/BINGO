import re
from .reconstruct import CHANNEL_W, PAGE_BONUS
from .damage import GAP_K, GAP_MID, WEIGHTS

H = "[b][color=ffbf33]{}[/color][/b]\n"


def esc(s):
    return str(s).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def build_report_blocks(r):
    B = []

    conf_line = (f"Mean word confidence: {r.ocr_mean_conf:.0f}%" if r.has_conf else
                 "This ML Kit build gave no per-word confidence, so a neutral "
                 f"{r.ocr_mean_conf:.0f}% is used for every word.")
    B.append(H.format("STEP 1 - OCR (on-device ML Kit)") +
             f"Recognized {len(r.words)} words, each with a bounding box.\n" + conf_line)

    B.append(H.format("STEP 2 - WHICH PARTS ARE DAMAGED?") +
             "Every word gets three evidence scores in 0..1:\n"
             "f_ocr = 1 - ocr_conf/100\n"
             "f_lm = sigmoid(z-score of surprisal), surprisal = -log2 P(word | previous 2 words)\n"
             "f_shape = 1 garbage (symbols, 5+ consonants...), 0.6 not in vocabulary\n"
             f"P(damaged) = sigmoid({WEIGHTS['bias']} + {WEIGHTS['ocr']}*f_ocr + "
             f"{WEIGHTS['lm']}*f_lm + {WEIGHTS['shape']}*f_shape)\n"
             "Flagged when P >= 50%.\n\n"
             f"Gaps: median gap {r.stats['med_gap']:.0f}px, median word {r.stats['med_w']:.0f}px.\n"
             "missing words = round(gap / (median word + median gap))\n"
             f"P(gap) = sigmoid({GAP_K}*(gap/median_gap - {GAP_MID}))")

    n_flag = 0
    for t in r.tokens:
        if not t.flagged:
            continue
        n_flag += 1
        bits = f"{t.bits:.1f} bits (z={t.z_lm:+.2f})" if t.bits is not None else "n/a"
        B.append(f"[b]Damaged word:[/b] '{esc(t.word.text)}'\n"
                 f"ocr conf {t.word.conf:.0f}% -> f_ocr={t.f_ocr:.2f}\n"
                 f"surprisal {bits} -> f_lm={t.f_lm:.2f}\n"
                 f"shape: {esc(t.why)} -> f_shape={t.f_shape:.2f}\n"
                 f"z = {t.z:+.2f}  ->  P(damaged) = {t.p_damage*100:.0f}%")
    for g in r.gaps:
        n_flag += 1
        B.append(f"[b]Gap before word #{g.position}:[/b] {g.gap_px:.0f}px "
                 f"(ratio {g.ratio:.1f}x median)\n"
                 f"estimated missing words = {g.est_words}\n"
                 f"P(gap) = {g.p_gap*100:.0f}%")
    if n_flag == 0:
        B.append("No damaged words or gaps detected.")

    B.append(H.format("STEP 3 - RECONSTRUCTION") +
             "Each candidate is scored\n"
             "log P(w|left) + log P(r1|left,w) + log P(r2|w,r1)\n"
             "(+ similarity to what OCR saw, + bonus if the word is used elsewhere on the page).\n"
             "Scores -> softmax -> probabilities.\n"
             "reconstruction confidence = P(top candidate) x context support.")

    for s in r.slots:
        left = " ".join(s.left) or "(start)"
        right = " ".join(s.right) or "(end)"
        kind = "damaged word" if s.kind == "token" else f"gap ({s.n_words} word(s))"
        lines = [f"[b]Slot {s.id}: {kind}[/b]",
                 f"context: ... {esc(left)} [ ? ] {esc(right)} ..."]
        for i, c in enumerate(s.candidates[:5], 1):
            lines.append(f"{i}. {esc(c.phrase)}  LM {c.ng_logp:.1f} "
                         f"ch{c.channel:+.1f} pg{c.page_bonus:+.1f}  P={c.prob*100:.0f}%")
        lines.append(f"chosen: [b]{esc(' '.join(s.chosen_words))}[/b]")
        if s.lm_note:
            lines.append(esc(s.lm_note))
        lines.append(f"damage confidence: {s.p_damage*100:.0f}%")
        lines.append(f"P(top)={s.top_prob*100:.0f}%  margin={s.margin*100:.0f}%  "
                     f"entropy={s.entropy:.2f} bits")
        lines.append(f"context support = ({len(s.left)}+{len(s.right)})/4 = {s.support:.2f}")
        lines.append(f"reconstruction confidence = P(top) x support = "
                     f"[b]{s.recon_conf*100:.0f}%[/b]")
        B.append("\n".join(lines))

    page = re.sub(r"\{\{\d+\|([^}]*)\}\}",
                  r"[color=ffbf33][b]\1[/b][/color]", esc(r.annotated))
    B.append(H.format("RECONSTRUCTED PAGE (filled parts in orange)") + page)

    terms_txt = "\n\n".join(
        f"[b]{esc(t['term'])}[/b] ({t['confidence']}%)\n{esc(t['definition'])}"
        for t in r.terms) or "No terms found."
    B.append(H.format("STEP 4 - TERMS") + terms_txt)
    return B

def build_how_blocks(r):
    B = [H.format("HOW THE WORDS WERE CHOSEN") +
         "A trigram language model guesses a word from the 2 words before it. "
         "It is trained on your corpus plus the undamaged words of this page.\n\n"
         "For every candidate word w:\n"
         "LM = log P(w|left) + log P(r1|left,w) + log P(r2|w,r1)\n"
         f"channel = {CHANNEL_W} * (1 - f_shape) * similarity(OCR text, w)\n"
         f"page = {PAGE_BONUS} for each word already used on this page\n"
         "total = LM + channel + page\n"
         "P(w) = e^total / (sum of e^total over all candidates)\n"
         "confidence = P(top) * context support, where support = (left+right words)/4"]

    if not r.slots:
        B.append("Nothing was reconstructed, because no damaged words or gaps were flagged.")

    for s in r.slots:
        left = " ".join(s.left) or "(start)"
        right = " ".join(s.right) or "(end)"
        kind = "damaged word" if s.kind == "token" else f"gap ({s.n_words} word(s))"
        lines = [f"[b]Slot {s.id}: {kind}[/b]"]
        if s.kind == "token":
            lines.append(f"OCR read: '{esc(s.observed)}'")
        lines.append(f"context: ... {esc(left)} [ ? ] {esc(right)} ...")
        lines.append(f"{s.n_cands} candidates scored, top 5:")
        for i, c in enumerate(s.candidates[:5], 1):
            lines.append(
                f"{i}. [b]{esc(c.phrase)}[/b]\n"
                f"   total = {c.ng_logp:.2f} (LM) + {c.channel:.2f} (channel) "
                f"+ {c.page_bonus:.2f} (page) = {c.total:.2f}\n"
                f"   P = e^{c.total:.2f} / e^{s.log_z:.2f} = {c.prob*100:.1f}%")
        lines.append(f"chosen: [b]{esc(' '.join(s.chosen_words))}[/b]")
        if s.lm_note:
            lines.append("LM detail: " + esc(s.lm_note))
        lines.append(f"context support = ({len(s.left)} + {len(s.right)}) / 4 = {s.support:.2f}")
        lines.append(f"confidence = {s.top_prob*100:.1f}% * {s.support:.2f} = "
                     f"[b]{s.recon_conf*100:.0f}%[/b]")
        B.append("\n".join(lines))
    return B
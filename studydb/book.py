"""Textbook extraction: per-page text, printed page labels, chapter/section from the PDF outline."""
import hashlib
import json
import re
import unicodedata

import pymupdf

BOOK_VERSION = 2


def _clean(text, strip_res):
    text = unicodedata.normalize("NFKC", text)
    for rx in strip_res:
        text = rx.sub(" ", text)
    # join words split across lines with a typographic line-break hyphen (U+2010/U+2011/soft hyphen)
    text = re.sub(r"(\w)[‐‑­][ \t]*\n[ \t]*(\w)", r"\1\2", text)
    text = text.replace("‐", "-").replace("‑", "-").replace("­", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out = []
    for ln in lines:
        if not ln:
            continue
        if ln == "|" and out:
            continue
        out.append(ln)
    return "\n".join(out)


def _chapters_from_toc(toc, npages):
    """Per page: (chapter title, section title) from the PDF outline."""
    chap_re = re.compile(r"^(chapter|part|appendix)\b|^\d+[\.\s]", re.I)
    chapters = [(lvl, title, p) for lvl, title, p in toc if re.match(r"^chapter\b", title, re.I)]
    chap_lvl = min((c[0] for c in chapters), default=1)
    if not chapters:
        chapters = [(lvl, title, p) for lvl, title, p in toc if lvl == 1]
    per_page = []
    ci = 0
    chapters = sorted(chapters, key=lambda c: c[2])
    secs = sorted([(p, lvl, title) for lvl, title, p in toc if lvl > chap_lvl and not chap_re.match(title)], key=lambda x: x[0])
    si = -1
    cur_ch = ""
    cur_sec = ""
    for n in range(1, npages + 1):
        while ci < len(chapters) and chapters[ci][2] <= n:
            cur_ch = chapters[ci][1]
            cur_sec = ""
            ci += 1
        while si + 1 < len(secs) and secs[si + 1][0] <= n:
            si += 1
            cur_sec = secs[si][2]
        per_page.append((cur_ch, cur_sec))
    return per_page


def extract_book(cfg_book, cache_dir, log=print):
    path = cfg_book["path"]
    h = hashlib.sha1(path.read_bytes()).hexdigest()[:20]
    key_extra = hashlib.sha1(json.dumps([cfg_book.get("strip_patterns"), cfg_book.get("page_offset"), BOOK_VERSION]).encode()).hexdigest()[:8]
    cf = cache_dir / f"book-{cfg_book['id']}-{h}-{key_extra}.json"
    if cf.exists():
        log(f"  {cfg_book['id']}: cached")
        return json.loads(cf.read_text(encoding="utf-8"))

    doc = pymupdf.open(path)
    strip_res = [re.compile(p) for p in cfg_book.get("strip_patterns", [])]
    toc = doc.get_toc()
    chap = _chapters_from_toc(toc, doc.page_count)

    # Printed page labels: prefer the PDF's own labels; the LAST page carrying a label wins
    # (front matter often restarts at 1), so printed p. 5 maps to the body page.
    labels = []
    for i in range(doc.page_count):
        try:
            labels.append(doc[i].get_label() or "")
        except Exception:
            labels.append("")
    off = cfg_book.get("page_offset")
    printed_to_pdf = {}
    if off is not None:
        for n in range(1, doc.page_count + 1):
            if n - off >= 1:
                printed_to_pdf[str(n - off)] = n
    else:
        for i, lab in enumerate(labels):
            if lab:
                printed_to_pdf[lab] = i + 1
    pdf_to_printed = {v: k for k, v in printed_to_pdf.items()}

    pages = []
    for i, page in enumerate(doc):
        n = i + 1
        text = _clean(page.get_text("text"), strip_res)
        ch, sec = chap[i]
        pages.append({"n": n, "label": pdf_to_printed.get(n, ""), "ch": ch, "sec": sec, "text": text})
    out = {"pages": pages, "printed_to_pdf": printed_to_pdf,
           "toc": [{"lvl": lvl, "title": t, "page": p} for lvl, t, p in toc if 1 <= p <= doc.page_count]}
    for old in cache_dir.glob(f"book-{cfg_book['id']}-*.json"):
        old.unlink()
    cf.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    log(f"  {cfg_book['id']}: {len(pages)} pages, {len(out['toc'])} outline entries")
    return out

"""Curated content: optional hand-written (or Claude-written) JSON files in <course>/curated/.

All files are optional. Slide references use "<deckid>-<slide number>" (e.g. "knn1-19").
Book references use "book_page" (printed page number) or "book_pdf_page" (PDF page), and optionally
"book" (book id; defaults to the first book in course.json). See README.md for the full schema.
"""
import json
import re
import unicodedata

FILES = ["definitions", "formulas", "people", "numbers", "figures", "book_index", "qa"]


def load(cfg, log=print):
    cur = cfg["dir"] / "curated"
    out = {}
    for name in FILES:
        p = cur / f"{name}.json"
        if p.exists():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise SystemExit(f"curated/{name}.json is not valid JSON: {e}")
        else:
            out[name] = {} if name == "figures" else []
    n = sum(len(v) for v in out.values())
    log(f"  curated items: {n} ({', '.join(f'{k} {len(v)}' for k, v in out.items() if v)})" if n else "  no curated content (search still covers slides and books)")
    return out


def book_ref(item, books, errors, where):
    """Resolve an item's book reference to {"book": id, "pdf": n, "label": printed}."""
    if not books:
        return None
    bid = item.get("book") or books[0]["id"]
    b = next((x for x in books if x["id"] == bid), None)
    if b is None:
        errors.append(f"{where}: unknown book '{bid}'")
        return None
    if item.get("book_pdf_page") is not None:
        n = int(item["book_pdf_page"])
        if not 1 <= n <= len(b["pages"]):
            errors.append(f"{where}: book_pdf_page {n} out of range")
            return None
        return {"book": bid, "pdf": n, "label": b["pages"][n - 1]["label"]}
    if item.get("book_page") is not None:
        lab = str(item["book_page"])
        n = b["printed_to_pdf"].get(lab)
        if n is None:
            errors.append(f"{where}: printed page {lab} not found in {bid}")
            return None
        return {"book": bid, "pdf": n, "label": lab}
    return None


def validate_slide_refs(cur, slide_ids):
    errors = []
    def chk(refs, where):
        for r in refs or []:
            if r not in slide_ids:
                errors.append(f"{where}: unknown slide '{r}'")
    for d in cur["definitions"]:
        chk(d.get("slides"), f"definition '{d.get('term')}'")
    for f in cur["formulas"]:
        chk(f.get("slides"), f"formula '{f.get('name')}'")
    for p in cur["people"]:
        chk(p.get("slides"), f"people '{p.get('who')}'")
    for x in cur["numbers"]:
        chk(x.get("slides"), f"numbers '{x.get('item')}'")
    for k in cur["figures"]:
        if k not in slide_ids:
            errors.append(f"figures: caption for unknown slide '{k}'")
    return errors


# ---------------------------------------------------------------- fact check (warnings for review)
def _n(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[\s’'\"“”‘’]+", " ", s)


def _checkables(text):
    out = set(re.findall(r"\b(1[89]\d\d|20[0-2]\d)\b", text))
    out |= set(re.findall(r"\b\d+(?:\.\d+)?%", text))
    out |= set(re.findall(r"(?<![A-Za-z])'([^']{6,60})'(?![A-Za-z])", text))
    out |= set(re.findall(r"\b\d+\.\d+\b", text))
    return out


def factcheck(cur, slides_by_id):
    """List years, percentages, decimals and quoted phrases in curated text that don't appear in the cited slides."""
    issues = []
    def run(label, text, refs):
        refs = [r for r in (refs or []) if r in slides_by_id]
        if not refs:
            return
        blob = _n(" ".join(slides_by_id[r]["title"] + " " + slides_by_id[r]["text"] + " " + slides_by_id[r]["ocr"] for r in refs))
        cap = _n(" ".join(cur["figures"].get(r, "") for r in refs))
        for c in _checkables(text):
            cn = _n(c).strip()
            if cn in blob:
                continue
            issues.append(("only in figure caption" if cn in cap else "not found in slides", label, c, refs))
    for d in cur["definitions"]:
        run("definition " + d["term"], d["text"], d.get("slides"))
    for p in cur["people"]:
        run("people " + p["who"], p.get("when", "") + " " + p["fact"], p.get("slides"))
    for x in cur["numbers"]:
        run("numbers " + x["item"], x["value"], x.get("slides"))
    for f in cur["formulas"]:
        run("formula " + f["name"], f.get("note", ""), f.get("slides"))
    return issues

"""Slide-deck extraction: per-slide text, title, emphasized phrases, figure flag, WebP image, optional OCR.

Results are cached per PDF (keyed by file hash + settings), so adding one deck only processes that deck.
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pymupdf
from PIL import Image

EXTRACTOR_VERSION = 3

# Glyph fixes for common PowerPoint/MathType export artifacts.
FIX = {"\u0002": "-", "\u0526": "", "\u0dd9": "", "\u0ddd": "", "\u0dd2": "", "\u0dcd": "Σ", "\u0ded": "", "\u0d7a": ""}
WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for k, v in FIX.items():
        s = s.replace(k, v)
    return re.sub(r"[ \t]+", " ", s.replace("\r", "")).strip()


def clean_lines(s):
    return [ln for ln in (norm(x) for x in s.split("\n")) if ln]


# ---------------------------------------------------------------- OCR availability
def find_tesseract():
    """Return a usable tesseract command or None (checks PATH and the default Windows install folder)."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return None
    for cand in (shutil.which("tesseract"),
                 r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if cand and Path(cand).exists():
            return cand
    return None


# ---------------------------------------------------------------- emphasis helpers
def _is_dark(c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return max(r, g, b) < 90 and max(r, g, b) - min(r, g, b) < 40


def _is_grayish(c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return max(r, g, b) - min(r, g, b) < 30


def _color_name(c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    if r > 150 and g < 100 and b < 100: return "red"
    if b > 150 and r < 120: return "blue"
    if g > 120 and r < 100 and b < 120: return "green"
    if r > 150 and g > 80 and b < 80: return "orange"
    if r > 100 and b > 100 and g < 80: return "purple"
    return "color"


def _yellow_rects(page):
    out = []
    for d in page.get_drawings():
        f = d.get("fill")
        if f and f[0] > 0.85 and f[1] > 0.85 and f[2] < 0.5:
            out.append(pymupdf.Rect(d["rect"]))
    return out


def _title_and_emphasis(page, opts):
    H = page.rect.height
    spans = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                t = norm(sp["text"])
                if t:
                    spans.append((sp, t, ln))
    font = opts.get("title_font") or ""
    title_ids = set()
    if font:
        cand = [(i, sp) for i, (sp, t, ln) in enumerate(spans)
                if font in sp["font"] and sp["size"] >= opts["title_min_size"] and sp["bbox"][1] < H * 0.3 and not t.isdigit()]
        if cand:
            mx = max(sp["size"] for _, sp in cand)
            title_ids = {i for i, sp in cand if sp["size"] >= mx - 0.6}
    if not title_ids:
        top = [(i, sp) for i, (sp, t, ln) in enumerate(spans) if sp["bbox"][1] < H * 0.3 and not t.isdigit()]
        if top:
            mx = max(sp["size"] for _, sp in top)
            title_ids = {i for i, sp in top if sp["size"] >= mx - 0.6}
    parts = sorted((spans[i][0]["bbox"][1], spans[i][0]["bbox"][0], spans[i][1]) for i in title_ids)
    title = norm(" ".join(t for _, _, t in parts))

    yr = _yellow_rects(page)
    emph = []
    for i, (sp, t, ln) in enumerate(spans):
        if i in title_ids or "http" in t or "github" in t or len(t) < 3:
            continue
        kinds = []
        if sp["flags"] & 16:
            kinds.append("bold")
        if not _is_dark(sp["color"]) and not _is_grayish(sp["color"]):
            kinds.append(_color_name(sp["color"]))
        bb = pymupdf.Rect(sp["bbox"])
        c = pymupdf.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2)
        if any(r.contains(c) for r in yr):
            kinds.append("highlight")
        if kinds:
            emph.append((round(ln["bbox"][1]), sp["bbox"][0], sp["bbox"][2], t, kinds))
    emph.sort()
    merged = []
    for y, x0, x1, t, k in emph:
        if merged and abs(merged[-1][0] - y) < 3 and x0 - merged[-1][4] < 9:
            merged[-1][2] += " " + t
            merged[-1][3] = sorted(set(merged[-1][3]) | set(k))
            merged[-1][4] = x1
        else:
            merged.append([y, x0, t, k, x1])
    out, seen = [], set()
    for y, x, t, k, _ in merged:
        if "%20" in t or "www." in t:
            continue
        t = re.sub(r"\s+", " ", t).strip(" ,.:;•")
        if len(t) < 3 or not re.search(r"[A-Za-z]{2}", t) or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append({"t": t, "k": k})
    return title, out


def _filter_ocr(ocr_lines, slide_text, vocab, speller):
    have = set(w.lower() for w in WORD.findall(slide_text))
    keep = []
    for ln in ocr_lines:
        ln = ln.strip(" |•*¢°")
        good = [w for w in WORD.findall(ln) if len(w) >= 3]
        if len(good) < 2:
            continue
        if sum(ch.isalpha() or ch in " _" for ch in ln) / max(1, len(ln)) < 0.75:
            continue
        new = [w for w in good if w.lower() not in have]
        if len(new) / len(good) < 0.5:
            continue
        real = [w for w in good if w.lower() in vocab or (speller is not None and w.lower() in speller)]
        if len(real) / len(good) < 0.75:
            continue
        keep.append(ln)
    return keep


def _fix_title(title, lines, prev):
    body = "\n".join(lines)
    if lines and len(body) < 100 and "•" not in body and len(lines) <= 5:
        return " ".join(lines)  # section-divider slide: the whole text is the title
    t = title.split(" •")[0].strip()
    if not t or t.startswith("•") or t.startswith("http") or len(t) > 80:
        return (prev + " (cont.)") if prev else (lines[0] if lines else "")
    return t


# ---------------------------------------------------------------- one deck
def _extract_deck(job):
    path, deck_id, opts, tess = job["path"], job["id"], job["opts"], job["tesseract"]
    doc = pymupdf.open(path)
    raw = []
    for i, page in enumerate(doc):
        n = i + 1
        lines = [ln for ln in clean_lines(page.get_text("text")) if ln != str(n)]
        parea = page.rect.width * page.rect.height
        img_area = 0.0
        for info in page.get_image_info():
            r = pymupdf.Rect(info["bbox"]) & page.rect
            if (r.width * r.height) / parea > 0.02:
                img_area += r.width * r.height
        zoom = opts["image_width"] / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=opts["webp_quality"], method=6)
        ocr_lines = []
        if tess:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tess
            pix2 = page.get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6))
            im2 = Image.frombytes("RGB", (pix2.width, pix2.height), pix2.samples)
            try:
                ocr_lines = clean_lines(pytesseract.image_to_string(im2, config="--psm 11"))
            except Exception:
                ocr_lines = []
        title, emph = _title_and_emphasis(page, opts)
        raw.append({"n": n, "lines": lines, "title": title, "emph": emph, "ocr": ocr_lines,
                    "fig": img_area / parea > opts["figure_threshold"],
                    "img": base64.b64encode(buf.getvalue()).decode()})
    try:
        from spellchecker import SpellChecker
        speller = SpellChecker()
    except Exception:
        speller = None
    vocab = set()
    for r in raw:
        vocab.update(w.lower() for w in WORD.findall(" ".join(r["lines"])))
    slides, images, prev = [], {}, ""
    for r in raw:
        sid = f"{deck_id}-{r['n']}"
        text = "\n".join(r["lines"])
        title = _fix_title(r["title"] or (r["lines"][0] if r["lines"] else ""), r["lines"], prev if r["n"] > 1 else "")
        prev = title.replace(" (cont.)", "")
        ocr = _filter_ocr(r["ocr"], text + " " + title, vocab, speller)
        slides.append({"id": sid, "deck": deck_id, "n": r["n"], "title": title, "text": text,
                       "ocr": "\n".join(ocr), "emph": r["emph"], "fig": r["fig"]})
        images[sid] = r["img"]
    return deck_id, {"slides": slides, "images": images, "ocr_used": bool(tess)}


def _cache_key(path, opts, tess):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    h.update(json.dumps({**opts, "ocr": bool(opts.get("ocr") and tess), "v": EXTRACTOR_VERSION}, sort_keys=True).encode())
    return h.hexdigest()[:20]


def extract_decks(cfg, log=print):
    """Return (slides list in deck order, images dict). Uses <course>/.cache/ to skip unchanged decks."""
    opts = {k: cfg["slides"][k] for k in ("title_font", "title_min_size", "ocr", "image_width", "webp_quality", "figure_threshold")}
    tess = find_tesseract() if opts["ocr"] else None
    if opts["ocr"] and not tess:
        log("  note: Tesseract not found, so text inside slide images won't be read (optional; see README).")
    cache = cfg["dir"] / ".cache"
    cache.mkdir(exist_ok=True)
    results, jobs = {}, []
    for d in cfg["decks"]:
        key = _cache_key(d["path"], opts, tess)
        cf = cache / f"deck-{d['id']}-{key}.json"
        if cf.exists():
            results[d["id"]] = json.loads(cf.read_text(encoding="utf-8"))
            log(f"  {d['id']}: cached")
        else:
            jobs.append(({"path": str(d["path"]), "id": d["id"], "opts": opts, "tesseract": tess}, cf))
    if jobs:
        log(f"  extracting {len(jobs)} deck(s){' with OCR' if tess else ''}... (OCR takes ~30 s per deck)")
        workers = max(1, min(len(jobs), (os.cpu_count() or 2)))
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for (job, cf), (deck_id, res) in zip(jobs, ex.map(_extract_deck, [j for j, _ in jobs])):
                for old in cache.glob(f"deck-{deck_id}-*.json"):
                    old.unlink()
                cf.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
                results[deck_id] = res
                log(f"  {deck_id}: {len(res['slides'])} slides")
    slides, images = [], {}
    for d in cfg["decks"]:
        r = results[d["id"]]
        slides.extend(r["slides"])
        images.update(r["images"])
    return slides, images

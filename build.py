#!/usr/bin/env python3
"""Build an offline, searchable exam reference (one HTML file) from a course folder.

  python build.py courses/ml-hasan              build dist/ml-hasan/<title>.html
  python build.py courses/new-class --init      create course.json from the PDFs in courses/new-class/sources/
  python build.py courses/ml-hasan --check      validate curated JSON and list facts to double-check
  python build.py courses/ml-hasan --sheets     write contact sheets of figure slides (for writing captions)
  python build.py --site                        build the hosted app (no course data) into docs/ for GitHub Pages

Options: --no-ocr (skip Tesseract), --out DIR (default dist/<course>), --no-embed-book (keep the PDF next to the HTML)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def init_course(course_dir):
    import pymupdf
    course_dir = Path(course_dir)
    src = course_dir / "sources"
    if not src.exists():
        src.mkdir(parents=True)
        print(f"Created {src}. Put your slide and textbook PDFs there, then run --init again.")
        return
    cfg_path = course_dir / "course.json"
    if cfg_path.exists():
        sys.exit(f"{cfg_path} already exists; edit it by hand to add files.")
    decks, books, used = [], [], set()
    pdfs = sorted(src.glob("*.pdf"), key=lambda p: p.name.lower())
    prefix = os.path.commonprefix([p.stem for p in pdfs]) if len(pdfs) > 1 else ""
    for i, p in enumerate(pdfs):
        doc = pymupdf.open(p)
        r = doc[0].rect
        base = "".join(c for c in p.stem[len(prefix):].lower() if c.isalnum())[:10] or f"f{i + 1}"
        rid, k = base, 2
        while rid in used:
            rid, k = f"{base}{k}", k + 1
        used.add(rid)
        stem = p.stem[len(prefix):] or p.stem
        short = stem if len(stem) <= 14 else stem[:6] + "…" + stem[-7:]
        entry = {"id": rid, "file": f"sources/{p.name}", "short": short,
                 "title": p.stem.replace("_", " ")}
        if r.width > r.height:
            decks.append(entry)
        else:
            books.append({**entry, "embed": True, "strip_patterns": []})
    cfg = {"title": course_dir.name.replace("-", " ").title() + " exam reference",
           "subtitle": "Lecture slides and textbook, searchable offline",
           "decks": decks, "books": books,
           "slides": {"title_font": "", "ocr": True},
           "title_overrides": {}}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (course_dir / "curated").mkdir(exist_ok=True)
    print(f"Wrote {cfg_path}: {len(decks)} deck(s), {len(books)} book(s).")
    print("Check the order, ids and short names (ids: letters/digits only), then run the build.")


def contact_sheets(cfg, slides, images, out_dir):
    import base64, io
    from PIL import Image, ImageDraw, ImageFont
    out_dir.mkdir(parents=True, exist_ok=True)
    figs = [s["id"] for s in slides if s["fig"]]
    W, H = 420, 315
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    for si in range(0, len(figs), 9):
        sheet = Image.new("RGB", (W * 3, H * 3), "white")
        dr = ImageDraw.Draw(sheet)
        for j, k in enumerate(figs[si:si + 9]):
            im = Image.open(io.BytesIO(base64.b64decode(images[k]))).convert("RGB").resize((W - 6, H - 6))
            x, y = (j % 3) * W, (j // 3) * H
            sheet.paste(im, (x + 3, y + 3))
            dr.rectangle([x + 3, y + 3, x + 150, y + 30], fill="black")
            dr.text((x + 8, y + 5), k, fill="yellow", font=font)
        sheet.save(out_dir / f"sheet{si // 9:02d}.webp", quality=80)
    print(f"Wrote {(len(figs) + 8) // 9} contact sheets of {len(figs)} figure slides to {out_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course", nargs="?", help="course folder, e.g. courses/ml-hasan")
    ap.add_argument("--site", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--no-embed-book", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.site:
        from studydb.assemble import write_site
        path = write_site(Path(a.out) if a.out else ROOT / "docs")
        print(f"Hosted app written to {path.parent} (index.html {path.stat().st_size / 1e6:.1f} MB). Commit docs/ and push.")
        return
    if not a.course:
        ap.error("give a course folder, or --site")

    if a.init:
        return init_course(a.course)

    from studydb.config import load_course, ConfigError
    from studydb import slides as S, book as B, curated as C, assemble as A
    t0 = time.time()
    try:
        cfg = load_course(a.course)
    except ConfigError as e:
        sys.exit(f"Config error: {e}")
    if a.no_ocr:
        cfg["slides"]["ocr"] = False
    if a.no_embed_book:
        for b in cfg["books"]:
            b["embed"] = False

    print(f"Course: {cfg['title']}")
    print("Slides:")
    slides, images = S.extract_decks(cfg)
    print("Books:")
    cache = cfg["dir"] / ".cache"
    cache.mkdir(exist_ok=True)
    books = {b["id"]: B.extract_book(b, cache) for b in cfg["books"]}
    print("Curated:")
    cur = C.load(cfg)
    data, errors = A.build_data(cfg, slides, books, cur)
    if errors:
        print("\nProblems in curated content (fix these):")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    if a.sheets:
        return contact_sheets(cfg, slides, images, cfg["dir"] / "work" / "sheets")
    if a.check:
        issues = C.factcheck(cur, {s["id"]: s for s in slides})
        print(f"\nCurated content is valid. {len(issues)} fact(s) to double-check by eye:")
        for kind, label, val, refs in issues:
            print(f"  [{kind}] {label}: '{val}'  slides={refs}")
        return

    out = Path(a.out) if a.out else ROOT / "dist" / cfg["dir"].name
    path = A.write_outputs(cfg, data, images, out)
    print(f"\nDone in {time.time() - t0:.0f} s: {path}  ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(slides)} slides, {sum(len(b['pages']) for b in data['books'])} book pages, "
          f"{len(data['defs'])} definitions, {len(data['formulas'])} formulas")


if __name__ == "__main__":
    main()

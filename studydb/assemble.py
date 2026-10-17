"""Combine extracted slides, books and curated content into the front-end data and one HTML file."""
import base64
import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def slugify(s):
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or "study_db"


def build_data(cfg, slides, books, cur, log=print):
    from .curated import book_ref, validate_slide_refs

    overrides = cfg.get("title_overrides", {})
    for s in slides:
        if s["id"] in overrides:
            s["title"] = overrides[s["id"]]
    slide_ids = {s["id"] for s in slides}
    errors = validate_slide_refs(cur, slide_ids)

    book_list = []
    for b in cfg["books"]:
        bx = books[b["id"]]
        book_list.append({"id": b["id"], "short": b["short"], "title": b["title"], "file": b["path"].name,
                          "embedded": bool(b["embed"]), "pages": bx["pages"], "toc": bx["toc"],
                          "printed_to_pdf": bx["printed_to_pdf"]})

    def bref(item, where):
        return book_ref(item, book_list, errors, where)

    cited = {}
    for d in cur["definitions"]:
        for r in d.get("slides", []):
            cited.setdefault(r, []).append(d["term"])

    data = {
        "meta": {"title": cfg["title"], "subtitle": cfg.get("subtitle", ""),
                 "built": datetime.date.today().isoformat(), "version": 2,
                 "synonyms": cfg.get("synonyms", {})},
        "decks": [{"id": d["id"], "short": d["short"], "title": d["title"]} for d in cfg["decks"]],
        "slides": [{**s, "cap": cur["figures"].get(s["id"], ""), "cited": cited.get(s["id"], [])} for s in slides],
        "books": book_list,
        "defs": [{"t": d["term"], "a": d.get("aliases", []), "d": d["text"], "refs": d.get("slides", []),
                  "tb": bref(d, f"definition '{d['term']}'"), "topic": d.get("topic", "")} for d in cur["definitions"]],
        "formulas": [{"g": f.get("group", ""), "name": f["name"], "tex": f["latex"], "note": f.get("note", ""),
                      "refs": f.get("slides", []), "tb": bref(f, f"formula '{f['name']}'")} for f in cur["formulas"]],
        "trivia": [{"when": p.get("when", ""), "who": p["who"], "fact": p["fact"], "refs": p.get("slides", []),
                    "tb": bref(p, f"people '{p['who']}'")} for p in cur["people"]],
        "numbers": [{"item": x["item"], "val": x["value"], "refs": x.get("slides", []),
                     "tb": bref(x, f"numbers '{x['item']}'")} for x in cur["numbers"]],
        "tb": [{"ch": t.get("chapter", ""), "sec": t["section"], "notes": t.get("notes", ""), "tags": t.get("tags", ""),
                "ref": bref(t, f"book_index '{t['section']}'")} for t in cur["book_index"]],
        "qa": [{"q": q["q"], "a": q["a"], "src": q.get("source", ""), "ref": bref(q, "qa")} for q in cur["qa"]],
    }
    return data, errors


def _vendor(fn):
    return (WEB / "vendor" / fn).read_text(encoding="utf-8")


def render_html(title, data, images, book_tags=(), head=""):
    """Fill web/template.html with the data, slide images, embedded books and bundled libraries."""
    tpl = (WEB / "template.html").read_text(encoding="utf-8")
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (tpl
            .replace("<!--__HEAD__-->", head)
            .replace("/*__DATA__*/null", js_data)
            .replace("__IMGDATA__", json.dumps(images))
            .replace("<!--__BOOKS__-->", "\n".join(book_tags))
            .replace("/*__PDFJS__*/", _vendor("pdf.min.js"))
            .replace("/*__KATEX__*/", _vendor("katex.min.js"))
            .replace("/*__ATKINSON__*/", _vendor("atkinson.css"))
            .replace("__PDFWORKER__", _vendor("pdf.worker.min.js"))
            .replace("__PAGE_TITLE__", _esc(title)))


def write_outputs(cfg, data, images, out_dir, log=print):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = cfg.get("output_name") or slugify(cfg["title"])

    book_tags = []
    for b in cfg["books"]:
        if b["embed"]:
            b64 = base64.b64encode(b["path"].read_bytes()).decode()
            book_tags.append(f'<script type="application/octet-stream" id="book-{b["id"]}">{b64}</script>')
        else:
            (out_dir / b["path"].name).write_bytes(b["path"].read_bytes())  # keep a copy next to the HTML

    html = render_html(cfg["title"], data, images, book_tags)
    html_path = out_dir / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return html_path


SITE_HEAD = """<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon.svg" type="image/svg+xml">
<link rel="icon" href="icons/icon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="theme-color" content="#1E7A4C" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#161C25" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="InfoBase">
<meta name="description" content="Search your lecture slides, textbooks and note sheets in seconds, offline. Your PDFs never leave your device.">"""


def write_site(out_dir, log=print):
    """Build the hosted app (GitHub Pages): the template with no course data, so visitors add their own PDFs.

    Writes index.html, the manifest, the icons and sw.js to out_dir. sw.js gets a VERSION that hashes
    the other files, so any change makes browsers install the new version.
    """
    out_dir = Path(out_dir)
    site = WEB / "site"
    (out_dir / "icons").mkdir(parents=True, exist_ok=True)
    # The app is called InfoBase now, but the data title stays "Class Base": the page derives the name of the
    # IndexedDB database that holds visitors' added files from it, so changing it would lose their files.
    data = {"meta": {"title": "Class Base", "subtitle": "", "version": 2,
                     "synonyms": {}, "hosted": True},
            "decks": [], "slides": [], "books": [], "defs": [], "formulas": [], "trivia": [], "numbers": [],
            "tb": [], "qa": []}
    html = render_html("InfoBase", data, {}, head=SITE_HEAD)
    (out_dir / "index.html").write_text(html, encoding="utf-8", newline="\n")  # LF on every OS: identical builds
    shutil.copyfile(site / "manifest.webmanifest", out_dir / "manifest.webmanifest")
    icons = sorted(f.name for f in (site / "icons").iterdir() if f.suffix == ".png" or f.name == "icon.svg")
    for fn in icons:
        shutil.copyfile(site / "icons" / fn, out_dir / "icons" / fn)
    precache = ["./", "index.html", "manifest.webmanifest"] + [f"icons/{fn}" for fn in icons]
    h = hashlib.sha256()
    for rel in precache[1:]:
        h.update(rel.encode() + b"\0" + (out_dir / rel).read_bytes())
    sw = ((site / "sw.js").read_text(encoding="utf-8")
          .replace("__VERSION__", h.hexdigest()[:12])
          .replace("__PRECACHE__", json.dumps(precache, indent=2)))
    (out_dir / "sw.js").write_text(sw, encoding="utf-8", newline="\n")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is, no Jekyll processing
    return out_dir / "index.html"


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

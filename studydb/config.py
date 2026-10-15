"""Load and validate a course folder's course.json."""
import json
from pathlib import Path

DEFAULT_SLIDES = {
    # Slide titles: spans in this font (substring match) at or above this size, near the top of the page.
    # Leave title_font empty to just use the largest text in the top 30% of the slide.
    "title_font": "",
    "title_min_size": 26,
    "ocr": True,            # read text inside images with Tesseract (skipped automatically if not installed)
    "image_width": 1000,    # pixel width of slide images stored in the HTML
    "webp_quality": 70,
    "figure_threshold": 0.12,  # fraction of the slide covered by raster images to count as "has figure"
}

DEFAULT_BOOK = {
    "embed": True,          # put the PDF inside the HTML (one-file exam copy). False = viewer asks you to locate it.
    "strip_patterns": [],   # regexes removed from every page's text (watermarks, running footers...)
    "page_offset": None,    # printed page + offset = PDF page. None = use the PDF's own page labels.
}


class ConfigError(Exception):
    pass


def load_course(course_dir):
    course_dir = Path(course_dir).resolve()
    cfg_path = course_dir / "course.json"
    if not cfg_path.exists():
        raise ConfigError(f"No course.json in {course_dir}. Run: python build.py {course_dir} --init")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"course.json is not valid JSON: {e}")

    cfg.setdefault("title", course_dir.name)
    cfg.setdefault("subtitle", "")
    cfg.setdefault("decks", [])
    cfg.setdefault("books", [])
    cfg.setdefault("title_overrides", {})
    cfg["slides"] = {**DEFAULT_SLIDES, **cfg.get("slides", {})}
    cfg["dir"] = course_dir

    seen = set()
    for i, d in enumerate(cfg["decks"]):
        for k in ("id", "file"):
            if k not in d:
                raise ConfigError(f"decks[{i}] is missing '{k}'")
        if not _ID_OK(d["id"]):
            raise ConfigError(f"deck id '{d['id']}' must be letters, digits, _ or . (no dashes)")
        if d["id"] in seen:
            raise ConfigError(f"duplicate deck/book id '{d['id']}'")
        seen.add(d["id"])
        d.setdefault("short", d["id"])
        d.setdefault("title", Path(d["file"]).stem)
        d["path"] = (course_dir / d["file"]).resolve()
        if not d["path"].exists():
            raise ConfigError(f"deck file not found: {d['path']}")

    for i, b in enumerate(cfg["books"]):
        for k in ("id", "file"):
            if k not in b:
                raise ConfigError(f"books[{i}] is missing '{k}'")
        if not _ID_OK(b["id"]):
            raise ConfigError(f"book id '{b['id']}' must be letters, digits, _ or . (no dashes)")
        if b["id"] in seen:
            raise ConfigError(f"duplicate deck/book id '{b['id']}'")
        seen.add(b["id"])
        for k, v in DEFAULT_BOOK.items():
            b.setdefault(k, v)
        b.setdefault("short", b["id"])
        b.setdefault("title", Path(b["file"]).stem)
        b["path"] = (course_dir / b["file"]).resolve()
        if not b["path"].exists():
            raise ConfigError(f"book file not found: {b['path']}")
    return cfg


def _ID_OK(s):
    return bool(s) and all(c.isalnum() or c in "_." for c in s)

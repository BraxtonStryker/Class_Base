# Working on Class Base (instructions for Claude)

This repo builds offline, searchable exam references from lecture slides and textbooks. The user is an EE student (strong in C, rusty in Python, on Windows) who uses the output HTML during open-book, multiple-choice exams. **The instructor pulls definitions and facts straight from the slides**, so fidelity to the slide wording matters more than elegance.

There are two products from one front end (`web/template.html`):
- **Course builds** (`python build.py courses/<course>`): one HTML file with a course's slides, book and curated notes inlined. The Python package is still called `studydb`.
- **The web app** (`python build.py --site` → `docs/`), hosted on GitHub Pages at https://braxtonstryker.github.io/Class_Base/ (repo `BraxtonStryker/Class_Base`, public). No course data; visitors add their own PDFs. `D.meta.hosted` switches on its extras (welcome card, service worker, update toast, download link).

**`courses/` is gitignored and never goes in this public repo** (the user's decision: copyrighted PDFs, and curated notes that follow the instructor's wording). The worked example `courses/ml-hasan/` exists only on the user's machine. In a cloud session without it, ask the user for the course files.

## Typical requests

**"Add these decks/chapters to <course>"** or **"make a database for <new class>"**

1. Get the PDFs the user uploaded into `courses/<course>/sources/`. Files in a Claude Project are only readable as text; ask the user to attach PDFs directly to the chat if you need the actual files.
2. For a new class, run `python build.py courses/<course> --init` and review `course.json`: deck order (match the syllabus), `id` (short, letters/digits only, e.g. `dt1`), `short`, `title`, and the course `title`/`subtitle`. Look at one slide to set `slides.title_font` if titles come out messy.
3. Run `python build.py courses/<course> --sheets`. This extracts and caches every deck, then writes contact sheets of all figure slides to `courses/<course>/work/sheets/`. **View every sheet** and every single slide where a sheet is unclear.
4. Read the extracted slide text: `courses/<course>/.cache/deck-<id>-*.json` holds each slide's `title`, `text`, `emph` (emphasized phrases) and `ocr`.
5. Write or extend the curated JSON in `courses/<course>/curated/`. The schema is in README.md; `courses/ml-hasan/curated/` is the worked example.
   - `figures.json`: one sentence or two per figure slide saying what the figure shows: labels, values, axes, the takeaway. Pictures aren't searchable otherwise.
   - `definitions.json`: one entry per testable concept. Stay close to the slide wording; include the slide's emphasized phrases; cite every slide that covers it (`"slides": ["dt1-14", ...]`). Textbook-only material goes in a clearly marked sentence with `book_page`.
   - `formulas.json`: every equation on the slides, in LaTeX (rendered by KaTeX in the browser).
   - `people.json`: names, years, books, quotes and anecdotes from the slides (instructors love these for MCQs).
   - `numbers.json`: defaults, ratios, counts, table values and example numbers.
   - `book_index.json` and `qa.json`: map syllabus topics to textbook sections and pages; short answers to end-of-chapter exercises (paraphrased).
   - Never invent facts. If a figure's numbers are hard to read, say so rather than guess.
6. `python build.py courses/<course> --check`. Fix every error, then review each listed "not found in slides" item against the slide image.
7. `python build.py courses/<course>`, then `python tests/smoke_test.py dist/<course>/<name>.html` (needs `pip install playwright` and its Chromium; in Claude's cloud sandbox Chromium is preinstalled). Also try 10 or more exam-style queries for the new material and confirm the right definition or slide ranks first or second.
8. Send the user the HTML. Never commit anything under `courses/` or `dist/` (enforced by .gitignore).

## Code map

- `build.py`: CLI (`--init`, `--check`, `--sheets`, `--no-ocr`, `--no-embed-book`, `--out`).
- `studydb/slides.py`: per-slide text, title, emphasis (bold/colored/yellow-highlight spans), figure flag, WebP image, OCR. Cached per PDF hash + settings; bump `EXTRACTOR_VERSION` when changing extraction.
- `studydb/book.py`: per-page text, printed page labels (the PDF's own labels; the last page with a given label wins), chapter/section from the PDF outline. Bump `BOOK_VERSION` when changing it.
- `studydb/curated.py`: loads and validates curated JSON, resolves book page references, runs the fact check.
- `studydb/assemble.py`: builds the data object and the single HTML (data, images and book PDFs inlined; PDF.js, its worker and KaTeX inlined from `web/vendor/`).
- `web/template.html`: all front-end code. It runs BM25 search with prefix and fuzzy matching and the `synonyms` from course.json, uses PDF.js for the book viewer and dropped-in files, and keeps dropped files in IndexedDB. It must keep working from `file://` with no network: no external URLs, no `fetch()` of local files.
- `studydb/assemble.py` `write_site()` + `web/site/` (manifest, `sw.js` template, icons): the web app. `sw.js` gets `VERSION` (a hash of the precached files) and `PRECACHE` filled in at build time. Its cache names start with `classBase-` because every GitHub Pages project of this user shares one origin (Quiz Qrusher uses `quizQrusher-`); the same goes for IndexedDB (`studydb-Class_Base`) and localStorage (`studydb-theme`) names.

## Releasing the web app

After changing `web/` or `studydb/assemble.py`, run `python build.py --site` and commit `docs/` with the change; GitHub Pages serves `main:/docs`. The build is byte-identical across runs and OSes (LF endings), so an unchanged front end produces no diff. Test it served over http (`python -m http.server 8000 -d docs`): add a slide PDF and a book PDF, search, reload (files restore from IndexedDB), then reload offline.

## Conventions

- Slide ids are `<deckid>-<n>` (1-based); book references use printed `book_page` or `book_pdf_page`.
- Keep the page usable on Windows Chrome/Edge from `file://`; test with the network blocked (the smoke test does this).
- The user prefers concise, scannable explanations and wants to learn the pattern rather than receive magic. When changing the code, explain what changed and why in plain terms.

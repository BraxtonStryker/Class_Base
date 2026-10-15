# Class Base

Search a class's lecture slides and textbook (PDFs) in seconds during an open-book exam. Paste the key words of a question and jump straight to the slide or book page that answers it.

**Use it:** https://braxtonstryker.github.io/Class_Base/

There are two ways to use it:

- **The web app** (link above): add your slides, textbooks and practice questions as PDFs, organized by class, and they're indexed in your browser. Nothing is uploaded, files are remembered on your device, and after the first visit it works offline. It can be installed as an app, or a class can be downloaded as one HTML file.
- **The builder** (`studydb`, this repo's Python code) builds a course into **one offline HTML file**, with everything the browser can't do on its own: OCR of text inside slide images, the phrases the instructor emphasized, figure descriptions, and curated definitions, formulas, names and numbers. Nothing to install or run on exam day: open the file in Chrome, Edge or Firefox.

What the built HTML gives you:

- **Search** across every slide, every textbook page and any curated notes (definitions, formulas, names and dates…), ranked so definitions and slides come first. Typos and plurals are tolerated; `"quotes"` force an exact phrase.
- **Slide viewer**: full-size slide plus its text, a description of any figure, and the phrases the instructor emphasized (red, blue, bold or highlighted).
- **Book viewer**: click any textbook page, page chip or table-of-contents entry and the real book opens at that page; scroll, zoom, type a printed page number, or switch to a text view.
- **Add files** tab: drop more PDFs (slides or a book) into the page and they're indexed live in the browser. This is handy between builds, and it's what the web app runs on.

## Folder layout

```
build.py                 the one command you run
build.bat                Windows shortcut:  build.bat ml-hasan
requirements.txt
studydb/                 the builder (slides, books, curated content, HTML assembly)
web/template.html        the front end (search, viewers, drop-in files), shared by the builds and the web app
web/vendor/              PDF.js and KaTeX, bundled so the page works offline
web/site/                the web app's extras: manifest, service worker, icons
docs/                    the built web app that GitHub Pages serves (generated: python build.py --site)
courses/                 your courses (kept local, not in git; see below)
  ml-hasan/
    course.json          which decks and books, in what order, plus a few settings
    curated/*.json       optional hand- or Claude-written notes (see "Curated content")
    sources/             your PDFs go here
tests/smoke_test.py      optional headless-browser check of a built file
CLAUDE.md                instructions for Claude when you ask it to extend a course
```

**`courses/` is not in the repo.** The repo is public (GitHub Pages needs that on a free account), and slides, textbooks and notes that follow an instructor's wording shouldn't be. Your courses live only on your computer; back them up separately (or keep them in a private repo).

## Setup on Windows (once)

1. Install **Python 3.10+** from python.org. On the first installer screen, tick **"Add python.exe to PATH"**.
2. Open **Command Prompt** in this folder (in File Explorer, type `cmd` in the address bar and press Enter).
3. Install the two libraries:
   ```
   py -m pip install -r requirements.txt
   ```
4. Optional: install **Tesseract OCR** so text inside slide pictures becomes searchable. Use the Windows installer from the UB Mannheim build (search "tesseract ub mannheim") and accept the default install folder. Without it, everything else still works.

## Build a course

Put the PDFs listed in `course.json` into that course's `sources/` folder, then run:

```
build.bat ml-hasan
```
or, equivalently, `py build.py courses\ml-hasan`.

The result is `dist\ml-hasan\ML_Exam_Reference.html`, plus `data.json` (the same database without images, for a future webapp). The first build reads every slide, which takes about 30 seconds per deck with OCR. After that, builds take a second or two, because unchanged PDFs are cached in `courses\<course>\.cache\`.

**Before an exam:** copy the HTML to the laptop you'll use, open it once with Wi-Fi off, search for something, and open a book page.

## Add a lecture deck to an existing course

1. Copy the PDF into `courses\<course>\sources\`.
2. Add an entry to `"decks"` in `course.json`, in lecture order:
   ```json
   {"id": "dt1", "file": "sources/Decision_Trees-1.pdf", "short": "DT-1", "title": "Decision Trees I"}
   ```
   The `id` (letters, digits, `_`) becomes part of every slide reference: slide 14 of this deck is `dt1-14`.
3. Run the build. The new deck is fully searchable right away; curated notes for it are optional (see below).

## Start a new class

```
py build.py courses\new-class --init
```
The first run creates `courses\new-class\sources\`. Put the PDFs there and run `--init` again. It writes a `course.json`, treating landscape PDFs as slide decks and portrait ones as books. Check the deck order, ids, short names and title, then build.

Settings you may want in `course.json`:

| Key | What it does |
|---|---|
| `title`, `subtitle`, `output_name` | Page heading and the HTML file name. |
| `slides.title_font` | Font the instructor uses for slide titles (e.g. `"Calibri"`), for cleaner titles. Leave empty to use the largest text near the top. |
| `slides.ocr` | `false` skips OCR. |
| `title_overrides` | `{"knn2-15": "Better title"}` for slides whose title came out wrong. |
| `books[].embed` | `true` puts the PDF inside the HTML (one file to carry). `false` keeps it next to the HTML; the page asks you to locate it once. |
| `books[].strip_patterns` | Regexes removed from book text (watermarks, repeated headers). |
| `books[].page_offset` | Only needed if the PDF lacks page labels: printed page + offset = PDF page. |
| `synonyms` | `{"sgd": ["stochastic"]}` so abbreviations also find the long form. |

## Curated content (optional, but where the value is)

The automatic part already makes every slide and page searchable. The files in `curated/` add what an instructor tests on: definitions phrased the way the slides phrase them, every formula, people and dates, key numbers, and descriptions of figures (so a chart's content is searchable). All files are optional JSON lists.

| File | Each entry |
|---|---|
| `definitions.json` | `term`, `aliases` [], `topic`, `text`, `slides` ["deck-n", …], `book_page` |
| `formulas.json` | `group`, `name`, `latex`, `note`, `slides`, `book_page` |
| `people.json` | `when`, `who`, `fact`, `slides`, `book_page` |
| `numbers.json` | `item`, `value`, `slides`, `book_page` |
| `figures.json` | `{ "deck-n": "what the figure on that slide shows" }` |
| `book_index.json` | `chapter`, `section`, `book_page`, `notes`, `tags` |
| `qa.json` | `q`, `a`, `source`, `book_page` |

`book_page` is the printed page number. Use `book_pdf_page` instead for unnumbered front matter, and add `"book": "<id>"` if the course has more than one book.

Check your edits with:
```
py build.py courses\<course> --check
```
It reports broken slide references and lists years, numbers and quoted phrases that don't appear on the cited slides, so you can double-check them.

**The easy way:** open a Claude session with this repo attached, upload the new PDFs, and ask it to "add these decks to the <course> course and write the curated notes". `CLAUDE.md` tells it exactly how.

## The web app

The hosted app is `web/template.html` built with **no course data**: each visitor adds their own PDFs, which PDF.js reads in the browser and IndexedDB keeps on their device. Nothing is uploaded, so the site never holds anyone's copyrighted material.

```
py build.py --site
```
writes it to `docs/`: `index.html` (one self-contained file with PDF.js and KaTeX inlined), the manifest and icons, and `sw.js`, the service worker that makes it work offline. `sw.js` gets a version hash of the other files, so any change makes browsers pick up the new version (they show a "new version is ready" bar). **Run it after changing anything in `web/`, then commit `docs/`.** GitHub Pages serves the `docs/` folder of `main`.

To try it locally: `py -m http.server 8000 -d docs`, then open http://localhost:8000/ (the service worker needs http, not `file://`).

What it does:

- **Classes**: tabs above the search box. Each class has its own files; **+ New class** adds one, and the Add files tab renames or deletes it. Only the open class's PDFs are loaded into memory.
- **Download for offline** (top bar) saves the app *plus the open class's PDFs* as one HTML file (`<class> - Class Base.html`). It opens from disk on any computer with no internet, so it's a good way to put a class on an exam laptop.
- **Emphasized on slides**: for slide decks, bold text (from the font) and red, blue or green text (from the drawing color) are picked up in the browser. Styles that cover most of a slide count as its normal text. Yellow highlighter boxes are still builder-only.
- **Question sets**: a third kind of file next to slides and books, for practice exams and question lists. It understands numbered questions (`1.` `1)` `(1)` `Q1` `Q.1` `Question 1:` `Problem 1`), `Q:`/`A:` pairs, unnumbered questions ending in `?`, lettered options (`A.` `a)` `(a)`, on separate lines or inline, even when they wrap), numbered options in a different style from the questions, answers (`Answer: B`, `Ans - c`, `Correct answer is (d)`, `Solution: ...`, a `*` or `✓` on the right option) and answer keys (`1. B 2. D`, after an "Answer key" heading or as a run of lines). Questions are searchable, and the **Practice questions** tab shows each one with hidden answers and the slides and book pages that best match it.

What the web app still can't do, and the builder can: OCR, highlighter detection, figure captions and curated notes. A next step: import a course built with `studydb` (its `data.json` plus images) into the web app, so curated notes work there too.

## Troubleshooting

- **`py` is not recognized:** reinstall Python with "Add to PATH" ticked, or use `python` instead of `py`.
- **"deck file not found":** the file names in `course.json` must match `sources\` exactly.
- **The book opens as text instead of pages:** the PDF isn't embedded (`embed: false`). Click "Locate …" once to pick the PDF.
- **Check a build automatically** (optional): `py -m pip install playwright`, then `py -m playwright install chromium`, then `py tests\smoke_test.py dist\ml-hasan\ML_Exam_Reference.html`.

Bundled libraries: PDF.js 3.11.174 (Apache-2.0) and KaTeX 0.16.11 (MIT); licenses are in `web/vendor/`.

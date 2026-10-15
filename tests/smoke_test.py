"""Headless browser test of a built HTML file, with all network access blocked.

  python tests/smoke_test.py dist/ml-hasan/ML_Exam_Reference.html [shots_dir]

Needs: pip install playwright && python -m playwright install chromium
Checks: page loads offline without errors, search works, the book viewer opens at the right page and
renders it, slide viewer works, formulas render, and a dropped-in PDF becomes searchable (and survives reload).
"""
import os
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

HTML = os.path.abspath(sys.argv[1])
SHOTS = sys.argv[2] if len(sys.argv) > 2 else None
QUERIES = sys.argv[3].split("|") if len(sys.argv) > 3 else []
fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def shot(pg, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, name + ".png"))


def make_test_pdf(path, landscape, words):
    import pymupdf
    doc = pymupdf.open()
    for i, w in enumerate(words):
        page = doc.new_page(width=720 if landscape else 504, height=540 if landscape else 661)
        page.insert_text((60, 80), f"Test title {i + 1}", fontsize=28)
        page.insert_text((60, 150), f"This page talks about {w} in detail.", fontsize=14)
    doc.save(path)


with sync_playwright() as p:
    tmp = tempfile.mkdtemp()
    ctx = p.chromium.launch_persistent_context(tmp, viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs, reqs = [], []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))

    def route(r):
        if r.request.url.startswith(("file://", "blob:", "data:")):
            r.continue_()
        else:
            reqs.append(r.request.url)
            r.abort()
    ctx.route("**/*", route)

    t0 = time.time()
    pg.goto("file://" + HTML)
    pg.wait_for_function("window.__studydb && window.__studydb.docs() > 0", timeout=60000)
    print(f"loaded in {time.time() - t0:.2f}s, {pg.evaluate('window.__studydb.docs()')} searchable items")

    def search(q, wait=300):
        pg.fill("#q", q)
        pg.wait_for_timeout(wait)
        return pg.eval_on_selector_all("#res .r", "els => els.slice(0,4).map(e => (e.querySelector('.badge')?.textContent||'') + ' | ' + e.querySelector('h3').textContent.slice(0,70))")

    for q in QUERIES:
        print(f"Q: {q}\n   " + "\n   ".join(search(q)))

    top = search("lasso feature selection")
    check(top and "Lasso" in top[0], "search ranks the Lasso definition first")
    shot(pg, "search")

    # book chip on the first result -> book viewer at the right page
    btn = pg.locator("#res .r").first.locator("[data-book]").first
    want = int(btn.get_attribute("data-page"))
    btn.click()
    pg.wait_for_selector("#bv.on", timeout=10000)
    pg.wait_for_function(f"document.querySelector('#bv-scroll .bv-page[data-n=\"{want}\"] canvas')", timeout=20000)
    cur = pg.evaluate("window.__studydb.BVS.page")
    check(cur == want, f"book viewer opened at PDF page {want} (now {cur}) and rendered it")
    shot(pg, "book_viewer")
    pg.fill("#bv-page", "139")
    pg.press("#bv-page", "Enter")
    pg.wait_for_timeout(400)
    check(pg.evaluate("window.__studydb.BVS.page") == 165, "typing printed page 139 jumps to PDF page 165")
    pg.click("#bv-mode")
    pg.wait_for_timeout(500)
    check(pg.locator("#bv-scroll .bv-page.text").count() > 100, "text view shows the book as text")
    pg.click("#bv-mode")
    pg.wait_for_timeout(300)
    pg.keyboard.press("Escape")
    check(not pg.is_visible("#bv"), "Esc closes the book viewer")

    # book-only content (outside the lecture slides)
    top = search("Gaussian RBF kernel similarity features")
    check(any("Book page" in t for t in top), "book pages appear for textbook-only topics")
    pg.locator("#res .r").filter(has_text="Book page").first.click()
    pg.wait_for_timeout(1500)
    check(pg.locator("#proj img[data-openbook]").count() == 1, "side panel shows the book page")
    shot(pg, "book_result")

    # slide viewer
    search("Mahalanobis Tagore")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(500)
    check(pg.is_visible("#ov") and "Covariance" in (pg.text_content("#ov-t") or ""), "Enter opens the slide viewer")
    pg.keyboard.press("Escape")

    # tabs
    for v in ["tb", "formulas", "trivia", "numbers", "emph", "browse"]:
        if pg.locator(f".tab[data-v='{v}']").is_visible():
            pg.click(f".tab[data-v='{v}']")
            pg.wait_for_timeout(500)
            shot(pg, "tab_" + v)
    check(pg.locator(".katex-error").count() == 0, "no formula rendering errors")
    pg.click(".tab[data-v='tb']")
    pg.locator("#v-tb .toc details").nth(5).locator("summary").click()
    pg.locator("#v-tb .toc details").nth(5).locator("li button").nth(1).click()
    pg.wait_for_selector("#bv.on")
    check(True, "table of contents opens the book")
    pg.keyboard.press("Escape")

    # drop-in files
    pg.click(".tab[data-v='add']")
    d = tempfile.mkdtemp()
    sp = os.path.join(d, "Week8_Decision_Trees.pdf")
    bp = os.path.join(d, "Other_Book.pdf")
    make_test_pdf(sp, True, ["zygomorphic entropy splits", "gini impurity", "pruning"])
    make_test_pdf(bp, False, ["quokkatron theorem", "bagging", "boosting", "stacking"])
    pg.set_input_files("#fileinp", [sp, bp])
    pg.wait_for_function("document.querySelectorAll('#flist .frow').length===2 && [...document.querySelectorAll('#flist .st')].every(e=>/indexed/.test(e.textContent))", timeout=30000)
    shot(pg, "add_files")
    pg.click(".tab[data-v='search']")
    top = search("zygomorphic")
    check(any("Slide" in t for t in top), "dropped slide deck is searchable")
    pg.keyboard.press("Enter")
    pg.wait_for_function("document.querySelector('#ov-img').src.startsWith('blob:')", timeout=15000)
    check(True, "dropped slide renders in the slide viewer")
    pg.keyboard.press("Escape")
    top = search("quokkatron")
    check(any("Book page" in t for t in top), "dropped book is searchable")
    pg.reload()
    pg.wait_for_function("window.__studydb && window.__studydb.docs() > 0")
    pg.wait_for_timeout(1500)
    top = search("quokkatron")
    check(any("Book page" in t for t in top), "dropped files are restored after reload")

    pg.set_viewport_size({"width": 390, "height": 844})
    search("gaussian kernel bandwidth")
    shot(pg, "mobile")

    real_errs = [e for e in errs if "Failed to load resource" not in e]
    check(not real_errs, f"no console errors {real_errs[:3]}")
    check(not reqs, f"no network requests {reqs[:3]}")
    ctx.close()

print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)

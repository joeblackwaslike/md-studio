# md-studio: design

Size: a project, delivered as stacked PRs (see "Delivery"). One spec and one plan cover slice 1; the spec is the first commit on the first branch.

## Intent

A CLI (`md-studio`) and importable library that converts documents into Markdown built for agents. The output is one file with YAML front matter that lists every chapter's `start_line`, `end_line`, `start_byte` and `end_byte`, so an agent can jump into a large document (a whole book) without reading it. Joe built this for EPUBs inside `~/github/joeblackwaslike/safaribooks` (`src/safaribooks/core/markdown/`, about 2,400 lines). This project extracts that code into its own package so safaribooks can later depend on it as a library, then adds the inputs, fixes, QA and outputs below.

The motivating case: convert an arXiv paper, given as a PDF, into rich Markdown an agent can navigate. The Hitchhiker's Guide to Agentic AI (arXiv 2606.24937) is the first target.

## Goals (slice 1)

1. Extract the safaribooks Markdown pipeline into `md_studio.core`, with its tests, passing lint, mypy strict and pytest.
2. Inputs by format: **EPUB** (parity with safaribooks), **HTML** (saved file or URL) and **PDF** (local file or URL).
3. Site-specific logic lives outside the readers, in an **extractor layer**. Slice 1 ships the arXiv extractor: for an arXiv paper it prefers the paper's LaTeXML HTML (real headings, original LaTeX math) and falls back to the PDF.
4. **Fix extensions** restore semantics a source lost (CSS-styled headings and similar), with an audit report, and are easy to add.
5. **QA**: deterministic audit, then an LLM review through the Claude subscription, then an optional human checkpoint that gates writing the output.
6. Outputs: a plain `.md` file, or a note written into Joe's Obsidian vault with the relevant file properties set.
7. **Semantic fidelity.** The Markdown is as rich as the source: links that resolve inside the file, correct heading hierarchy, bold, italic and strikethrough, monospaced code blocks with a language, images, tables, footnotes, math as LaTeX, and a table of contents whose links work.

## Later phases (designed for now, not built in slice 1)

- **Phase 2:** generic web pages through [Defuddle](https://github.com/kepano/defuddle) (the extractor behind the Obsidian Web Clipper), run as a Node subprocess, plus site-specific extractors added on top. Joe wants this as the next phase after slice 1.
- **Skill output:** a book saved as an agent skill. It splits the single Markdown file into per-chapter reference pages under `references/`, and the top-level skill links out to them.
- **EPUB output:** Markdown or Document to EPUB (Joe wants this for the arXiv paper too). safaribooks already has an EPUB writer in `core/epub` worth reusing.
- Live EPUB fetching by URL; safaribooks switching to this library.

## Anti-goals

- A CLI-only tool with no library boundary. If safaribooks can't import `md_studio.core` without pulling in the CLI, the project has failed at its main structural goal.
- A second, parallel plugin framework. The extension system that exists in safaribooks is the one mechanism for fixes; slice 1 extends it.
- Output that is merely valid Markdown. The offsets must be right: for every chapter, the `start_byte`/`end_byte` slice of the file starts at that chapter's `##` heading.
- Site logic buried in a reader. If a rule only applies to arXiv, or to one publisher, it belongs in an extractor.
- Catching structure bugs by hand each time. QA exists so Joe doesn't have to notice a missing heading hierarchy himself.

## Constraints

- Python 3.12+, uv, ruff, mypy strict, wemake-python-styleguide, pytest, `just`. These match safaribooks, so the extracted code keeps its complexity budgets. Start from `uvx spinup-py`, then fit the repo's existing files.
- Code style: type hints everywhere including private functions, `X | None`, `list[x]`, `Protocol` over ABC, no `Any`. Numpy-style docstrings on public APIs without repeating type info. No inline comments, no banner comments, no commented-out code.
- Untrusted input: downloaded HTML and PDFs are parsed with lxml or the PDF engine only, never executed, and never committed. Large fixtures stay out of the repo; tests use small hand-built fixtures.
- arXiv etiquette (verified against [robots.txt](https://arxiv.org/robots.txt) and the [terms of use](https://info.arxiv.org/help/api/tou.html)): only `/html/` and `/abs/` and `/pdf/` are fetched, never `/e-print` or `/src`; at least 15 seconds between requests to arxiv.org; a descriptive User-Agent; no bulk scraping.
- Conventional commits. Joe's JS/TS rules apply to the Node side later (pnpm for deps, Bun as runtime).

## Approaches considered

- **A. One distribution with a hard internal boundary (chosen by Joe).** `md_studio.core` has no CLI dependencies; `md_studio.cli` is the typer app. One pyproject, one release stream.
- B. Two distributions in a uv workspace. Rejected for now; A can split into B later without changing imports.
- C. Copy as an internal module with no boundary. Rejected; it defeats the library goal.

Slice scope was also chosen: build a thin vertical slice over the seams, then add inputs and outputs. Joe's later comments moved PDF, the extractor layer, fix extensions and QA into slice 1 and left generic web, skill output and EPUB output for later phases.

## Architecture

```
src/md_studio/
  core/        Document model, ir, extract, assemble, extensions, render, frontmatter, exceptions
  readers/     epub.py, html.py, pdf.py        format only, no site knowledge; each returns a Document
  extractors/  arxiv.py                         site/publisher logic; picks a source and cleans it
  qa/          audit.py, llm_review.py, gate.py
  sinks/       file.py, obsidian.py
  cli/         typer app
```

- **Document.** The neutral result of a reader: metadata, ordered chapters whose content is an lxml element, an optional stylesheet, and flags such as `has_math`. safaribooks' `EpubDocument`/`EpubMetadata`/`EpubChapter` are renamed `Document`/`DocumentMetadata`/`SourceChapter`. My call.
- **Pipeline (unchanged in behavior).** `assemble.assemble()`, then source-level fixes, then IR extensions, then `Renderer().render()`, then `frontmatter.build()` (two-pass, fixed-width offsets).
- **Reader.** A `Protocol` with one method that turns a source (path or URL) into a `Document`. Readers know formats: EPUB container and spine, HTML trees, PDF structure.
- **Extractor.** A `Protocol` with `matches(source) -> bool` and `resolve(source) -> ExtractionPlan`. The plan says which reader to use, on which concrete source, plus the source-level fixes and metadata overrides for it. Extractors are tried in order and the first match wins; with no match the CLI picks a reader by file type.
- **Sink.** Decides where the text goes and which properties wrap it.
- **Extractor and Defuddle seam.** Defuddle becomes an extractor-like backend in phase 2, so the protocol must allow an extractor that returns cleaned HTML instead of choosing a reader. Defuddle has no plugin API for new site extractors (checked: it keeps a static registry in its own repo), so site extractors written here run as Python steps around it.

### Readers

- **EPUB (`readers/epub.py`).** Extracted from safaribooks `markdown/reader/` as-is. Populates `Document.stylesheet` from the EPUB's CSS (see fix extensions).
- **HTML (`readers/html.py`).** Takes a saved file or an `https://` URL, parses with lxml, and returns one `Document`. It splits chapters only when told how; the generic HTML reader treats the page as one chapter and relies on the extractor to supply a chapter splitter. Fetching uses httpx with a size cap and timeout.
- **PDF (`readers/pdf.py`).** Default engine **Docling** (MIT, local, active, per-block page numbers and boxes), behind a small `PdfEngine` Protocol so Marker or MinerU can be added later. The reader exports the converted document as HTML with math as LaTeX and images written to a folder, loads it into lxml, and splits chapters from the PDF outline when present, otherwise from top-level headings. Per-chapter `start_page`/`end_page` are added to the front matter. A first task benchmarks Docling against Marker on three or four of Joe's PDFs, including the Hitchhiker's Guide PDF, before the engine is locked in; Docling's formula enrichment is opt-in and untested on these papers. Marker's weights license and MinerU's extra terms are why they are not the default.

### arXiv extractor

Given an `arxiv.org/abs|pdf|html/<id>` URL, a bare arXiv id, or a local PDF that carries an arXiv id (`--arxiv-id` otherwise), it resolves to the best source in order: LaTeXML HTML at `arxiv.org/html/<id>` (if it exists), then the PDF. It then applies the LaTeXML rules below when the HTML wins. Metadata (title, authors, year) comes from the page; the LaTeXML `<title>` glues the subtitle on with no space, so the title is built from the document title element.

LaTeXML 0.7.6 facts for the Hitchhiker's Guide (https://arxiv.org/html/2606.24937v3, about 17 MB), from the earlier handoff, to be re-verified by the builder by downloading the page into a scratch directory and reading it with lxml and one `doc.iter()` pass (descendant XPath over the whole tree times out):

1. **Chapter splitting.** `section.ltx_chapter` (7 top-level, 31 nested in 6 `section.ltx_part`), plus `section.ltx_appendix` and `section.ltx_bibliography`, which must be included. Expect about 40 entries; confirm. Skip `nav.ltx_TOC`. A paper with no `ltx_chapter` (an article) is split at its top-level `ltx_section` elements instead (plus any appendix and bibliography), so every rule below still applies; heading levels are then taken relative to the section entry (subsection to h2, subsubsection to h3). A page with neither is left unchanged with a warning.
2. **Parts.** Drop `ltx_part` as entries; prefix chapter titles with the part, e.g. `Part II · Chapter 12 <title>`. Default; change on request.
3. **Pre-pass** rewrites LaTeXML idioms into shapes the extractor already understands:
   - Headings are mapped by title class, relative to the entry: `ltx_title_section` to h2, `ltx_title_subsection` to h3, `ltx_title_subsubsection` to h4 (in this book that is h4, h5 and h6 on the page); in a chapterless paper the section is the entry, so subsections become h2 and subsubsections h3. A heading with none of those classes (theorem, acknowledgements) falls back to the tag: h4/h5/h6 to h2/h3/h4 in a book, and one level up (h3 to h6 drop by one) in a chapterless paper; delete the chapter's own h3 title; `h6.ltx_title_paragraph` becomes a bold lead-in paragraph. The renderer shifts every heading down one level (h1 renders as `##`, the chapter heading's own depth), so h4 to h1 would put sections level with their chapter. With h2/h3/h4 they render as `###`, `####` and `#####`.
   - `div.ltx_listing` and `span.ltx_listing` become `<pre><code class="language-<lang>">` from `ltx_listingline`; drop `ltx_listing_data` (`data:` URI download link). The page has 132 div and 72 span listings (a naive count of the class doubles it, because `ltx_listing` appears twice in the class attribute).
   - List labels (`span.ltx_tag_item`, the bullet or number) are dropped, since the list renderer adds its own.
   - `span.ltx_note.ltx_role_footnote` becomes a noteref anchor plus a footnote definition in the shapes `extract/epub_types.py` detects (14 footnotes).
   - `img src` becomes absolute against `https://arxiv.org/html/` (a source that starts with the paper id, such as `2606.24937v3/figures/a.png`, joins there; a bare name joins against `https://arxiv.org/html/<id>/`); replace "Refer to caption" alt text with the figcaption text; drop `data:` images. The renderer writes an image as its alt text only, so `Document.embed_images` (set by this fix, false otherwise) makes it write `![alt](src)` with a safe source: no `data:` or `javascript:` scheme, and spaces, parentheses and angle brackets percent-encoded.
4. **Math.** `ir.Math(tex)` (inline, `$tex$`) and `ir.MathBlock(tex)` (`$$\n...\n$$`) from `<math alttext>` (never the MathML text). Intercept `table.ltx_equation` and `ltx_equationgroup` (the page also has 61 equations written as `span.ltx_equation.ltx_eqn_table`) before the generic table branch; inspect an equation group before deciding how to join rows; drop equation numbers. Math bypasses `render/escaping.py`. A literal `$` in prose is escaped only for documents flagged `has_math`, so EPUB output stays byte-identical to safaribooks. Fallback if this gets hairy: code spans and fenced ```latex blocks with no IR changes.
5. **Cross-references** (`a.ltx_ref` with `#Ch28.S4.SS3.p1.1`-style hrefs) must resolve across chapters; check how `assemble/rewrite.py` and `fix_broken_links` handle them.

### Fix extensions (restoring lost semantics)

Joe's `scripts/fix_epub_headings.py` (497 lines) handles the Mastering Behavioral Interviews EPUB, where headings were CSS-styled `div`s: it parses the CSS with cssutils, ranks heading classes by font-size, weight and text-transform, converts the divs to h1-h6, and writes an audit. This becomes a first-class fix.

What exists (verified by reading it): safaribooks already has an IR-stage extension system. `MarkdownExtension` has `transform_chapter` and `transform_book`; `ExtCtx` carries `book`, `anchors` and `stylesheet`; discovery merges four built-ins (`fix-headings`, `remove-footnotes`, `fix-broken-links`, `reformat-toc`) with entry points; reserved built-in names cannot be shadowed. Its `fix-headings` only reads inline `font-size` and a class-name regex, and **`ExtCtx.stylesheet` is never populated**, so real CSS is never consulted.

Slice 1:
- Populate `ExtCtx.stylesheet` from `Document.stylesheet` (EPUB CSS; HTML `<style>` and linked sheets; PDFs have none).
- Port the CSS heading classifier into `fix-headings`; keep the inline-size rule as a fallback.
- Port the audit: every promotion is recorded (chapter, text, old tag and classes, new level) and written to a report.
- Add a source-level fix stage that runs on the lxml tree before extraction, so fixes like the arXiv pre-pass have a home. Extensions enable by name on the CLI (`--ext fix-headings,...`); adding one is one small class plus one registry line or an entry point.
- Fixture: a small hand-built EPUB reproducing CSS-styled headings (not the full book). `scripts/fix_epub_headings.py` is deleted once the port passes its tests (my call). `scripts/epub_to_html.py` stays in `scripts/` and is out of scope.

### QA (Joe's requirement)

Runs after conversion; `--qa` is on by default, `--no-qa` skips it.

1. **Deterministic audit** (no LLM, always runs): offsets valid (each slice starts at its `##`); every internal link resolves to a heading or anchor; heading counts by level match the source; the outline has no skipped levels and a plausible density (a 300-page book with three headings is flagged: this is the missed-headings failure); no leftover site markup (`ltx_`, `data:` URIs); images exist; no empty chapters; no heading over a length cap.
2. **LLM review.** A bounded sample of chapters (first, last, and a few chosen by outline anomalies) is sent to Claude with the matching source excerpt (HTML text, or the PDF page text and page images for those pages) and the audit results. It returns a structured verdict `pass | warn | escalate` with findings (chapter, evidence, suggested fix extension). It runs through the Claude Code CLI on Joe's subscription: `claude -p` with `--setting-sources ""`, `--no-session-persistence`, `--strict-mcp-config`, `--system-prompt`, `--output-format json` and a named model, so it never inherits hooks or creates ghost sessions. `--no-llm-qa` disables it. Document text leaves the machine only to Claude, and the CLI says so.
3. **Human checkpoint.** On `escalate`, or with `--review always`, the CLI stops before any sink write, writes `<output>.qa.md` (verdict, findings, heading outline before and after fixes), and asks for approval interactively. Non-interactive runs exit with code 3. The Obsidian sink writes only after `pass` or approval. The file sink always writes (the file is the artifact under review).
4. QA findings suggest fix extensions by name where one applies.

### Sinks

- **File:** writes the Markdown as produced.
- **Obsidian:** vault path from configuration (environment variable or flag). Properties and folder convention come from Joe's vault; the builder reads the `personal-agent-skills:obsidian-vault` skill and inspects the vault before choosing, and states what it chose. Baseline: title, authors, source, type, created, tags. `frontmatter.build()` takes `extra: Mapping[str, str | list[str]]` and includes it in the first pass, so offsets stay right; sinks never edit front matter afterwards. Check on a real vault note whether Obsidian tolerates the fixed-width numbers and the nested `chapters:` list; if not, namespace the offsets under one key.

### CLI

`md-studio convert <source> [--sink file|obsidian] [-o PATH] [--vault PATH] [--ext NAMES] [--qa/--no-qa] [--review always|on-escalate] [--no-llm-qa] [--arxiv-id ID]`. Reader and extractor are chosen by source: extractors first, then file type (`.epub`, `.html`, `.pdf`), otherwise a clear error until generic web exists. The builder shows where the entry point lives before wiring it.

## Naming and hosting (Joe's answers)

Command `md-studio`; distribution `md-studio`; import package `md_studio`; folder `~/github/joeblackwaslike/md-studio`; public GitHub repo `joeblackwaslike/md-studio`, created under that name (it does not exist yet, so nothing upstream is renamed). First implementation step, from outside the repo before any worktree: `mv markdown-studio md-studio`, rename `markdown-studio.code-workspace` to `md-studio.code-workspace` (update its path), then in the first commit rename `src/markdown_studio` to `src/md_studio`. Build sessions resume from the new path. Before the first push, check the history for anything that shouldn't be public (`fixed-audit.md`, any committed EPUB; `.clawhip/` stays untracked), then `gh repo create joeblackwaslike/md-studio --public`.

## Delivery

Stacked PRs, each under about 400 hand-written lines (the extraction PR is mostly copied code and is the exception); spec and plan in the first PR.

1. Rename, scaffold from spinup-py, extract core plus EPUB reader plus file sink with tests and the safaribooks parity check.
2. Obsidian sink and `frontmatter.build(extra=...)`.
3. Fix extensions: stylesheet plumbing, CSS heading classifier, audit, source-level stage, strikethrough node.
4. HTML reader, arXiv extractor, math IR.
5. PDF reader (Docling), benchmark, arXiv PDF-to-HTML resolver.
6. QA: deterministic audit, LLM review, human gate.

## My calls (flag any you disagree with)

- Extraction baseline is safaribooks `main` at `4211efe`, clean apart from a staged `.gitignore`. A parity check converts one EPUB with that commit and with this package and diffs the Markdown byte for byte. Tests come from `safaribooks/tests/core/markdown/` (assemble, convert, extensions, extract, frontmatter, offsets, reader, render, plus the `_epub.py` helper).
- Clean copy with an origin note in the README (`git filter-repo` for blame is a follow-up if wanted). Core depends only on what the extracted code imports (lxml, html5lib, httpx); typer and rich sit behind a `cli` extra, so the console script needs `md-studio[cli]`. `EpubReadError` becomes `ReadError`; `convert_epub()` becomes `convert()`; the one outside import (`safaribooks.core.exceptions`) becomes a local `exceptions.py`.
- Strikethrough: add a `Strikethrough` IR node and render `~~text~~` (safaribooks has none; `sup`/`sub` handling needs checking).
- Saved HTML without a source URL: derive the arXiv id from the canonical link or `<base>`; if absent, leave image `src` relative and warn.
- Real-paper checks assert structure (every slice starts at a `##`) and print the chapter count (about 40); the exact count is pinned only on the hand-built fixture.
- PDF-to-HTML intermediate keeps `data-page` attributes so front matter can carry `start_page`/`end_page`; builder confirms Docling exposes what is needed.

## Done when

- Converting the Hitchhiker's Guide from its arXiv id, PDF URL and local PDF produces a file whose chapter slices all start at `##` headings; the HTML route gives about 40 chapters, correct LaTeX for the `Ch1.E1` softmax equation, intact `$k$`, a sane `Chx6.T1` table, 14 footnotes, absolute image links, and no `data:` URIs, `ltx_` names, `⬇` or "Refer to caption". The PDF route produces a sensible heading outline, fenced code and math, and per-chapter page ranges.
- Converting a local EPUB gives the same Markdown and offsets as safaribooks at `4211efe`.
- On the CSS-styled-heading fixture, `fix-headings` promotes the right headings and writes an audit; Mastering Behavioral Interviews converts with its heading outline recovered (compare against `scripts/fix_epub_headings.py` on the same file).
- A new fix is one small class plus one registry line, enabled by name, shown by a test.
- QA: the audit catches a book with missing headings and a broken internal link in tests; the LLM review runs through `claude -p` with isolated flags and returns the structured verdict (tested with the CLI call stubbed, plus one real run); an `escalate` verdict blocks the Obsidian write and exits 3 non-interactively.
- The Obsidian sink writes a note into a test vault directory with the intended properties, and the front matter parses with a standard YAML parser and has the expected property types.
- Fidelity audit: every internal link resolves, heading level counts match the source, and strikethrough, code blocks, images and the TOC survive, on the EPUB and arXiv outputs.
- Unit tests for math rendering and escaping, listing normalization, footnote rewrite, heading demotion, chapter splitting (part-nested chapters, appendix, bibliography), offsets on a small fixture, extractor selection, sinks, and the QA stages. `just` lint, type-check and test targets pass.

## Left to the builder

Exact core dependency list; the Docling-versus-Marker benchmark and final default; Obsidian property names and folder convention; whether Obsidian needs namespaced offsets; QA sampling size and thresholds; fixture contents; README wording.

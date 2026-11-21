# md-studio Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the safaribooks EPUB-to-Markdown pipeline into `md_studio`, then add HTML, PDF, arXiv, fix extensions, QA and Obsidian output.

**Architecture:** One distribution, hard boundary: `md_studio.core` imports nothing from `cli`, `sinks`, `qa`. Readers return a neutral `Document`; extractors pick source and reader; sinks decide where text goes. Fixes extend the existing IR extension system.

**Tech Stack:** Python 3.12+, uv, ruff, mypy strict, wemake-python-styleguide, pytest, just, lxml, html5lib, httpx; typer and rich behind a `cli` extra; Docling behind a `pdf` extra.

**Spec:** `docs/superpowers/specs/2026-11-21-md-studio-design.md`

## Global Constraints

- Python 3.12+, uv, ruff, mypy strict, wemake-python-styleguide, pytest, `just`; scaffold from `uvx spinup-py`, then fit existing files.
- Type hints everywhere including private functions, `X | None`, `list[x]`, `Protocol` over ABC, no `Any`. Numpy-style docstrings on public APIs without repeating type info. No inline comments, banner comments or commented-out code.
- Downloaded HTML and PDFs are parsed with lxml or the PDF engine only, never executed, never committed; tests use small hand-built fixtures.
- arXiv: fetch only `/html/`, `/abs/`, `/pdf/`, never `/e-print` or `/src`; at least 15 seconds between requests to arxiv.org; descriptive User-Agent; no bulk scraping.
- Conventional commits. Each PR under about 400 hand-written lines (task 2 is the extraction exception).
- Baseline for extraction: `~/github/joeblackwaslike/safaribooks` at `4211efe`, `src/safaribooks/core/markdown/` (2,376 lines) and `tests/core/markdown/`.
- For every chapter, the `start_byte`/`end_byte` slice of the output starts at that chapter's `##` heading.
- Core depends only on lxml, html5lib, httpx. `EpubReadError` becomes `ReadError`; `convert_epub()` becomes `convert()`; `safaribooks.core.exceptions` becomes local `md_studio/core/exceptions.py`.

## Review Focus

1. A source with zero chapters or one empty chapter: converts or raises `ReadError`, never writes a file with broken offsets.
2. Non-ASCII titles and text: byte offsets count UTF-8 bytes, not characters.
3. A literal `$` in prose on a math document is escaped; on an EPUB it is not (output stays byte-identical to safaribooks).
4. arXiv id with a version suffix (`2606.24937v3`) and without; old-style ids (`hep-th/9901001`).
5. Obsidian vault path missing or unwritable: clear error, no partial note.

## File Structure

```
pyproject.toml, justfile, README.md           (task 1)
src/md_studio/core/                           document model, ir, extract, assemble, extensions, render, frontmatter, exceptions
src/md_studio/readers/{epub,html,pdf}.py
src/md_studio/extractors/arxiv.py
src/md_studio/qa/{audit,llm_review,gate}.py
src/md_studio/sinks/{file,obsidian}.py
src/md_studio/cli/                            typer app
tests/                                        mirrors src
```

---

## PR 1: scaffold, extraction, EPUB reader, file sink

### Task 1: Scaffold

**Files:** Create `pyproject.toml`, `justfile`, `README.md` (with origin note), `tests/__init__.py`, `src/md_studio/__init__.py` (exists, empty).

**Interfaces:** Produces `just lint`, `just typecheck`, `just test`; console script `md-studio` under extra `cli`.

- [ ] **Step 1:** In a scratch dir run `uvx spinup-py scratch-md-studio`; copy its tooling config (ruff, mypy strict, wemake, pytest, just targets) into the repo. Set `name = "md-studio"`, package `md_studio`, extras `cli = [typer, rich]`, `pdf = [docling]`.
- [ ] **Step 2:** Run `just lint && just typecheck && just test`. Expected: pass on the empty package (pytest with no tests exits 5; add `tests/test_import.py::test_package_imports` asserting `import md_studio`).
- [ ] **Step 3:** Commit `chore: scaffold tooling from spinup-py`.

### Task 2: Extract core and EPUB reader

**Files:**
- Create: everything under `src/md_studio/core/` copied from `safaribooks/core/markdown/` (assemble, extensions, extract, frontmatter, ir, render, `headings.py`, `transform.py`), `src/md_studio/readers/epub.py` (from `markdown/reader/`), `src/md_studio/core/exceptions.py`, `src/md_studio/core/document.py`.
- Test: copy `tests/core/markdown/*` to `tests/core/` and `tests/readers/`, including the `_epub.py` helper.

**Interfaces:**
- Produces in `core/document.py`: `DocumentMetadata`, `SourceChapter(title: str, element: object)`, `Document(metadata: DocumentMetadata, chapters: tuple[SourceChapter, ...], stylesheet: str = "", has_math: bool = False)`. These are `EpubMetadata`/`EpubChapter`/`EpubDocument` renamed, with the two new `Document` fields.
- Produces `core.convert.convert(document: Document, *, extensions: list[str] | None = None, extra: Mapping[str, str | list[str]] | None = None) -> RenderedMarkdown` where `RenderedMarkdown` is a frozen dataclass `(text: str, front_matter: str, body: str, chapters: list[ChapterRange])`. It does no file I/O; `convert_epub`'s write moves to the file sink.
- Produces `readers.epub.read_epub(path: Path) -> Document`.
- Produces `core.exceptions`: `ReadError`, `OffsetOverflowError`, `UnknownExtensionError`.

- [ ] **Step 1:** Copy files, rewrite imports `safaribooks.core.markdown` to `md_studio.core`, rename types and exceptions as above. Delete nothing else.
- [ ] **Step 2:** Port tests with the same renames. Run `just test`. Expected: all copied tests pass.
- [ ] **Step 3:** Write `tests/core/test_boundary.py::test_core_imports_nothing_outside_core`: walk `md_studio/core/*.py` ASTs and assert no import of `md_studio.cli`, `md_studio.sinks`, `md_studio.qa`, `typer`, `rich`.
- [ ] **Step 4:** Write `tests/core/test_offsets_utf8.py::test_offsets_count_utf8_bytes` using a chapter titled `Café ☕` and assert `body.encode()[start_byte:end_byte]` starts with `## Café ☕`.
- [ ] **Step 5:** Add `Document.has_math` to `Renderer` input only as a pass-through flag (consumed in PR 4). Run `just lint typecheck test`. Commit `feat: extract safaribooks markdown pipeline into md_studio.core`.

### Task 3: File sink and parity check

**Files:** Create `src/md_studio/sinks/file.py`, `src/md_studio/cli/__init__.py`, `src/md_studio/cli/app.py`; Test `tests/sinks/test_file.py`, `tests/test_parity.py`.

**Interfaces:**
- Consumes: `convert`, `read_epub`.
- Produces `Sink` Protocol in `sinks/__init__.py`: `def write(self, rendered: RenderedMarkdown, *, name: str) -> Path`. `FileSink(dest: Path, *, force: bool = False)` implements it; refuses to overwrite without `force` (`FileExistsError`).
- Produces CLI `md-studio convert <source> [-o PATH] [--ext NAMES]`. Show the user where the typer entry point lives before wiring.

- [ ] **Step 1:** Tests: `test_file_sink_writes_front_matter_then_body`, `test_file_sink_refuses_overwrite_without_force`, `test_cli_converts_epub_fixture` (typer `CliRunner`, exit 0, output file exists).
- [ ] **Step 2:** Implement sink and CLI; `convert` command picks the reader by suffix (`.epub` only for now, otherwise a clear error naming the supported types).
- [ ] **Step 3:** `tests/test_parity.py::test_output_matches_safaribooks_baseline`: skipped unless env `SAFARIBOOKS_BASELINE` points at a checkout at `4211efe`; converts the helper EPUB with both and asserts byte equality. Run it once locally with the env set and record the result in the PR body.
- [ ] **Step 4:** `just lint typecheck test`; commit `feat: file sink and convert command`. Open PR 1 (spec, plan and code in this one branch).

---

## PR 2: Obsidian sink and `frontmatter.build(extra=...)`

### Task 4: Front matter extras

**Files:** Modify `src/md_studio/core/frontmatter/document.py`; Test `tests/core/test_frontmatter_extra.py`.

**Interfaces:** `frontmatter.build(meta, titles, offsets, body, *, extra: Mapping[str, str | list[str]] | None = None)`; extras are emitted before `chapters:` and included in the first pass so offsets stay correct.

- [ ] **Step 1:** Tests: `test_extra_properties_appear_before_chapters`; `test_offsets_remain_valid_with_extra` (slice at `start_byte` begins with `##` after adding a multi-line list extra); `test_front_matter_parses_with_yaml` using `yaml.safe_load` (dev dependency) and asserting types.
- [ ] **Step 2:** Implement; run tests; commit `feat: front matter extra properties`.

### Task 5: Obsidian sink

**Files:** Create `src/md_studio/sinks/obsidian.py`; Test `tests/sinks/test_obsidian.py`; CLI flags `--sink obsidian`, `--vault PATH` (env `MD_STUDIO_VAULT`).

**Interfaces:** `ObsidianSink(vault: Path, *, folder: str)` implements `Sink`; adds properties via `extra` (baseline: title, authors, source, type, created, tags). Raises `SinkError` (defined in `sinks/__init__.py`) when the vault is missing or unwritable, before writing anything.

- [ ] **Step 1:** Read the `personal-agent-skills:obsidian-vault` skill and inspect the real vault read-only; choose folder and property names; state the choice in the PR. Check on one real note whether Obsidian tolerates fixed-width offsets and nested `chapters:`; if not, namespace under one key.
- [ ] **Step 2:** Tests: `test_note_written_with_properties` (tmp vault, parse note with YAML), `test_missing_vault_raises_before_writing`.
- [ ] **Step 3:** Implement, commit `feat: obsidian sink`.

---

## PR 3: Fix extensions

### Task 6: Stylesheet plumbing, CSS heading classifier, audit, source-level stage

**Files:** Modify `core/convert.py`, `core/extensions/fix_headings.py`, `core/extensions/base.py`; Create `core/extensions/css_headings.py`, `core/extensions/audit.py`, `core/extensions/source_fix.py`, `tests/fixtures/css_headings.epub` builder in `tests/core/_epub.py`; Delete `scripts/fix_epub_headings.py` once tests pass.

**Interfaces:**
- `ExtCtx.stylesheet` is populated from `Document.stylesheet` in `convert`.
- `css_headings.classify(stylesheet: str) -> dict[str, int]` maps class name to heading level (1-6) by font-size, weight, text-transform ranking, ported from `scripts/fix_epub_headings.py` (uses cssutils; add as dependency).
- `PromotionRecord(chapter: str, text: str, old_tag: str, old_classes: tuple[str, ...], level: int)` and `ExtCtx`-side collector; `audit.render(records) -> str`.
- `SourceFix` Protocol: `name: ClassVar[str]`, `def apply(self, document: Document) -> Document`; registered in the same registry/entry-point mechanism as `MarkdownExtension`; run before extraction. `--ext` enables both kinds by name.

- [ ] **Step 1:** Tests: `test_stylesheet_reaches_extensions`; `test_css_styled_div_promoted_to_heading_level` on the hand-built fixture asserting exact levels; `test_audit_lists_every_promotion`; `test_inline_size_fallback_still_works`; `test_new_fix_is_one_class_plus_registry_line` (defines a toy `SourceFix` and enables it by name).
- [ ] **Step 2:** Implement against those tests. Run once against `mastering-behavioral-interviews-fixed.epub` and compare the heading outline with `scripts/fix_epub_headings.py` output before deleting it.
- [ ] **Step 3:** Add `ir.Strikethrough` and render `~~text~~`; test `test_strikethrough_renders_tildes`, and check `sup`/`sub` handling, adding a test for whatever it does today.
- [ ] **Step 4:** Commit `feat: css heading classifier, audit, source-level fixes, strikethrough`.

---

## PR 4: HTML reader, arXiv extractor, math

### Task 7: HTML reader and extractor protocol

**Files:** Create `readers/html.py`, `extractors/__init__.py`; Test `tests/readers/test_html.py`.

**Interfaces:**
- `readers.html.read_html(source: Path | str, *, splitter: ChapterSplitter | None = None) -> Document`; `https://` sources fetched with httpx (size cap 50 MB, 30 s timeout); single chapter unless a splitter is given. `ChapterSplitter = Callable[[etree._Element], list[SourceChapter]]`.
- `Extractor` Protocol: `def matches(self, source: str) -> bool`, `def resolve(self, source: str) -> ExtractionPlan`; `ExtractionPlan(reader: Reader, source: str, source_fixes: tuple[str, ...], metadata_overrides: Mapping[str, str])`.

- [ ] **Step 1:** Tests: `test_local_html_becomes_single_chapter`, `test_oversized_response_rejected` (httpx `MockTransport`), `test_first_matching_extractor_wins`.
- [ ] **Step 2:** Implement; commit `feat: html reader and extractor protocol`.

### Task 8: Math IR

**Files:** Modify `core/ir/inline.py`, `core/ir/block.py`, `core/render/inlines.py`, `core/render/blocks.py`, `core/render/escaping.py`; Test `tests/core/test_math.py`.

**Interfaces:** `ir.Math(tex: str)` inline renders `$tex$`; `ir.MathBlock(tex: str)` renders `$$\n{tex}\n$$`; math bypasses escaping; `$` in prose is escaped only when `Document.has_math`.

- [ ] **Step 1:** Tests: `test_inline_math_renders_dollars`, `test_block_math_renders_fenced_dollars`, `test_math_content_not_escaped`, `test_dollar_in_prose_escaped_only_with_has_math`, `test_epub_output_unchanged_without_math`.
- [ ] **Step 2:** Implement; commit `feat: math nodes`. If extraction of equations gets hairy later, fall back to code spans per the spec.

### Task 9: arXiv extractor (LaTeXML route)

**Files:** Create `extractors/arxiv.py`, `extractors/arxiv_latexml.py` (source fix), `tests/fixtures/latexml_mini.html` (hand-built); Test `tests/extractors/test_arxiv.py`.

**Interfaces:**
- `ArxivExtractor` implements `Extractor`; `parse_arxiv_id(source: str) -> str | None` accepts abs/pdf/html URLs, bare ids, versions, old-style ids.
- A rate limiter `ArxivClient(min_interval: float = 15.0)` in `extractors/arxiv.py` wrapping httpx with the descriptive User-Agent and the allowed-path check (raises `ValueError` for `/e-print`, `/src`).
- LaTeXML source fix `LatexmlFix` implements the spec's pre-pass: chapter splitting (`ltx_chapter`, `ltx_appendix`, `ltx_bibliography`, skipping `nav.ltx_TOC`), part-prefixed titles, heading demotion, listings to `<pre><code class="language-..">`, footnote rewrite, absolute image URLs, math from `alttext`, equation tables intercepted before the generic table branch.

- [ ] **Step 1:** Re-verify the spec's LaTeXML facts: download `https://arxiv.org/html/2606.24937v3` once into the scratch dir (respect the delay) and read it with lxml via a single `iter()` pass; correct the spec if counts differ.
- [ ] **Step 2:** Tests on the mini fixture: `test_parse_arxiv_id_forms` (incl. `2606.24937v3`, `hep-th/9901001`), `test_forbidden_paths_rejected`, `test_requests_spaced_by_min_interval` (fake clock), `test_chapters_include_appendix_and_bibliography`, `test_part_prefix_in_titles`, `test_headings_demoted`, `test_listing_becomes_fenced_code_with_language`, `test_footnotes_rewritten`, `test_images_absolute_and_caption_alt`, `test_equation_group_becomes_math_block`, `test_cross_chapter_refs_resolve`, `test_no_ltx_or_data_uri_remains`.
- [ ] **Step 3:** Implement; wire `ArxivExtractor` first in the CLI's extractor list; add `--arxiv-id`. Run the real paper once; assert every slice starts at `##` and print the chapter count.
- [ ] **Step 4:** Commit `feat: arxiv extractor with latexml fixes`.

---

## PR 5: PDF reader

### Task 10: Engine benchmark

**Files:** Create `docs/benchmarks/pdf-engines.md`.

- [ ] **Step 1:** In a scratch venv, run Docling (with formula enrichment on and off) and Marker on the Hitchhiker's Guide PDF and three of Joe's PDFs from `~/Downloads` or `~/Documents`; record heading outline quality, math, code blocks, runtime on this machine.
- [ ] **Step 2:** Write the result and the chosen default to the doc; commit `docs: pdf engine benchmark`. Docling stays default unless it clearly loses.

### Task 11: PDF reader and arXiv fallback

**Files:** Create `readers/pdf.py`, `readers/pdf_engines.py`; Modify `extractors/arxiv.py`; Test `tests/readers/test_pdf.py`.

**Interfaces:**
- `PdfEngine` Protocol: `def to_html(self, path: Path, images_dir: Path) -> str` (HTML with `data-page` attributes, math as LaTeX).
- `DoclingEngine` implements it. `read_pdf(source: Path | str, *, engine: PdfEngine | None = None) -> Document`; chapters from the PDF outline, else top-level headings; per-chapter `start_page`/`end_page` added to `ChapterRange` and the front matter.
- `ArxivExtractor.resolve` falls back to the PDF when `/html/<id>` returns 404.

- [ ] **Step 1:** Tests with a stub engine returning fixed HTML: `test_chapters_split_from_headings`, `test_page_ranges_in_front_matter`, `test_arxiv_falls_back_to_pdf_on_html_404`.
- [ ] **Step 2:** Implement; confirm Docling exposes page numbers per block, report if not. Run the real PDF once; assert slices start at `##`.
- [ ] **Step 3:** Commit `feat: pdf reader via docling`.

---

## PR 6: QA

### Task 12: Deterministic audit

**Files:** Create `qa/audit.py`; Test `tests/qa/test_audit.py`.

**Interfaces:** `audit(rendered: RenderedMarkdown, document: Document) -> AuditReport`; `AuditReport(findings: tuple[Finding, ...])`; `Finding(code: str, chapter: str | None, message: str, suggested_fix: str | None)`. Checks per the spec: offsets, internal links, heading counts versus source, skipped levels and density, leftover `ltx_`/`data:`, images exist, empty chapters, heading length cap.

- [ ] **Step 1:** One test per check, each with a minimal failing input (`test_flags_book_with_missing_headings`, `test_flags_broken_internal_link`, `test_flags_skipped_heading_level`, ...) plus `test_clean_document_has_no_findings`.
- [ ] **Step 2:** Implement; commit `feat: deterministic qa audit`.

### Task 13: LLM review and human gate

**Files:** Create `qa/llm_review.py`, `qa/gate.py`; Test `tests/qa/test_llm_review.py`, `tests/qa/test_gate.py`; CLI flags `--qa/--no-qa`, `--review always|on-escalate`, `--no-llm-qa`.

**Interfaces:**
- `Verdict = Literal["pass", "warn", "escalate"]`; `ReviewResult(verdict: Verdict, findings: tuple[Finding, ...])`; `review(sample: ReviewSample, runner: Callable[[list[str], str], str] = run_claude) -> ReviewResult`. `run_claude` shells out to `claude -p` with `--setting-sources ""`, `--no-session-persistence`, `--strict-mcp-config`, `--system-prompt`, `--output-format json` and a named model.
- `gate.decide(result, *, interactive: bool, review: str) -> GateDecision`; non-interactive `escalate` exits code 3; writes `<output>.qa.md`. The file sink always writes; the Obsidian sink writes only after `pass` or approval.

- [ ] **Step 1:** Tests: `test_claude_invoked_with_isolated_flags` (stub runner captures argv and asserts every flag), `test_malformed_verdict_json_is_escalate`, `test_escalate_non_interactive_exits_3_and_skips_obsidian_write`, `test_pass_writes_obsidian`, `test_qa_report_file_written`, `test_cli_says_text_goes_to_claude`.
- [ ] **Step 2:** Implement; run one real review on the fixture and record the verdict in the PR.
- [ ] **Step 3:** Commit `feat: llm qa review and human gate`.

## Self-review notes

- Spec coverage: goals 1-7 map to tasks 2-3 (1), 3/7/11 (2), 7/9 (3), 6 (4), 12-13 (5), 3/5 (6), 8/9/6 (7). Later phases are intentionally unplanned.
- The spec's "Done when" real-paper checks live in tasks 9 and 11 (structure assertions, printed counts).

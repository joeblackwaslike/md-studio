# md-studio

Convert EPUB, HTML, PDF and arXiv sources to Markdown.

## Install

```bash
uv sync --extra cli
```

Extras: `cli` (typer, rich) and `pdf` (docling).

## Usage

```bash
md-studio convert BOOK.epub [-o PATH] [--ext NAMES] [--force] [--sink file|obsidian] [--vault PATH]
md-studio convert <arxiv url|id> [--arxiv-id ID] [-o PATH]
```

The output defaults to `BOOK.md` next to the source. `--ext` takes comma-separated names, enabled in the order given (see [Extensions](#extensions)). An existing destination is refused unless you pass `--force`, and the source file itself is never overwritten.

### Extensions

Nothing runs unless you name it with `--ext`. Built-ins: `fix-headings`, `remove-footnotes`, `fix-broken-links`, `reformat-toc`.

- `fix-headings` promotes paragraphs that act as headings. It reads the EPUB's stylesheet (at most 1 MiB, each sheet scanned on its own) and merges the declarations of each plain `.class` rule, alone or in a comma list, later rules winning. A class at 1.3rem or larger (or 1.1rem and bold: `bold`, `semibold`, 600-900) becomes a heading, ranked into levels 1-6 by size; sizes within 0.1rem share a level. `em` and `%` are treated as relative to the root font size (a simplification), `px` and `pt` are converted at 16px and 12pt per rem. An element with several heading classes takes the most prominent (lowest) level. Rules inside `@media` or other at-rules, and compound selectors such as `p.title`, are ignored, so a heading class defined only there stays a paragraph. Without a matching class it falls back to an inline `font-size` or a heading-like class name.
- With `fix-headings` the command prints `Promoted N headings` (N may be 0), and one `warning:` line on stderr for each piece of CSS it could not use (a skipped, cut or corrupt stylesheet member, an unclosed comment or block, oversize rules). A default conversion never prints those warnings.
- Every promotion is listed in `<output stem>.audit.md` (columns: chapter, text, original tag, original classes, level) next to the output, written only when something was promoted and only with the file sink (`--sink obsidian` writes no audit and says so). The Level column is the source heading level (1 means `h1`), the same numbering the old `fix_epub_headings.py` audit used; the Markdown output shifts every heading one level down under the chapter `##`. Each text cell is an inline code span with control characters, bidi marks and backticks removed, backslashes shown as the fullwidth lookalike `＼` (so no parser can read a pipe as escaped by the text) and pipes escaped, so untrusted EPUB text cannot become a link, emphasis or HTML. The report is written with the same atomic, symlink-refusing logic as the Markdown; an existing one is refused unless you pass `--force`, and that is checked before the `.md` is written.

Extensions come in two kinds that share one name list. A Markdown extension subclasses `md_studio.core.extensions.MarkdownExtension` and transforms chapters. A source fix has a `name` and `apply(document) -> Document` (the `SourceFix` protocol) and runs before extraction, in listed order. To add either, write the class and register it in the `md_studio.extensions` entry-point group, or add it to `BUILTINS` in `md_studio/core/extensions/discovery.py`. Names are unique across both kinds: the first registration of a name wins (built-ins first), a later entry-point reusing it is ignored with a log warning, and an entry-point that fails to load or registers something unusable is reported only if you ask for its name.

### arXiv papers

`md-studio convert 2606.24937`, `md-studio convert https://arxiv.org/abs/2606.24937v3` and the `/pdf/` and `/html/` URLs all read the paper's HTML version at `https://arxiv.org/html/<id>`. Old-style ids such as `hep-th/9901001` work too. The output is `arxiv-<id>.md` in the current directory unless you pass `-o`.

- `--arxiv-id ID` treats the source as that paper and ignores the source argument. It takes an id or an arXiv URL.
- A path that exists on disk is never taken for an arXiv id.
- The HTML route splits the paper into one chapter per chapter, appendix and the bibliography, with part names in the titles. Math comes from the original TeX (`$...$` and `$$...$$`), figures are embedded as `![caption](absolute url)`, and listings become fenced code with their language. This runs the `arxiv-latexml` source fix, which the extractor enables on its own, so you do not pass `--ext` for it.
- A paper without chapters (an article) is split at its top-level sections instead, with the same rules for math, listings, footnotes, images and links. A page with neither chapters nor sections is left as it is, with a warning.
- If arXiv has no HTML version the command fails with a clear error. The PDF fallback is not built yet.

arXiv's access rules are built in. Only `/html/`, `/abs/` and `/pdf/` are fetched, never `/e-print` or `/src`. Requests within one run are spaced at least 15 seconds apart, redirect hops included, and carry a descriptive User-Agent. The spacing is kept per process, so it does not span separate `md-studio` invocations; do not script several runs back to back. Convert one paper at a time; there is no bulk mode.

### Obsidian sink

`--sink obsidian` writes the converted Markdown as a note into an Obsidian vault instead of a file next to the source. The vault comes from `--vault PATH` or the `MD_STUDIO_VAULT` environment variable (the flag wins; `~` is expanded). With `--sink file` (the default) both are ignored.

- The note is `<vault>/Book Notes/<name>.md`, where `<name>` is the source file's stem with characters Obsidian or filesystems reject replaced by spaces. The folder is created if missing.
- Besides the usual front matter, the note gets `source` (the source file name), `type: book-note`, `status: draft`, `created` (ISO date), `tags: [book-notes]` and, when the source has authors, `author` (a list).
- An existing note is never overwritten, and `-o` and `--force` are rejected with `--sink obsidian`.
- A missing, non-directory or unwritable vault fails before the source is read, with one `Error:` line and nothing written.

The `chapters:` byte offsets describe the file as written. Editing properties in Obsidian's Properties UI re-serializes the front matter, which invalidates those offsets.

The `md-studio` console script needs the `md-studio[cli]` extra. The library (`md_studio.core`, `md_studio.readers`) has no CLI dependencies.

Exit codes: `0` on success, `1` on any conversion error (printed as one `Error: ...` line), `2` on usage errors (bad or missing arguments).

## Development

```bash
just lint
just typecheck
just test
```

The committed goldens in `tests/fixtures/parity` pin the output to the safaribooks baseline. To also compare against a live checkout of that baseline (commit `4211efe`), point `SAFARIBOOKS_BASELINE` at it:

```bash
SAFARIBOOKS_BASELINE=~/github/joeblackwaslike/safaribooks just test
```

## Origin

The Markdown pipeline was extracted from [safaribooks](https://github.com/joeblackwaslike/safaribooks) at `4211efe`.

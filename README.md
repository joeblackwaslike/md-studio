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
```

The output defaults to `BOOK.md` next to the source. `--ext` takes comma-separated extension names in pipeline order (`fix-headings,remove-footnotes,fix-broken-links,reformat-toc`). An existing destination is refused unless you pass `--force`, and the source file itself is never overwritten.

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

# md-studio

Convert EPUB, HTML, PDF and arXiv sources to Markdown.

## Install

```bash
uv sync --extra cli
```

Extras: `cli` (typer, rich) and `pdf` (docling).

## Usage

```bash
md-studio convert BOOK.epub [-o PATH] [--ext NAMES] [--force]
```

The output defaults to `BOOK.md` next to the source. `--ext` takes comma-separated extension names in pipeline order (`fix-headings,remove-footnotes,fix-broken-links,reformat-toc`). An existing destination is refused unless you pass `--force`, and the source file itself is never overwritten.

The `md-studio` console script needs the `md-studio[cli]` extra. The library (`md_studio.core`, `md_studio.readers`) has no CLI dependencies.

Exit codes: `0` on success, `1` on any error (printed as one `Error: ...` line).

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

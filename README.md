# md-studio

Convert EPUB, HTML, PDF and arXiv sources to Markdown.

## Install

```bash
uv sync --extra cli
```

Extras: `cli` (typer, rich) and `pdf` (docling).

## Development

```bash
just lint
just typecheck
just test
```

## Origin

The Markdown pipeline was extracted from [safaribooks](https://github.com/joeblackwaslike/safaribooks) at `4211efe`.

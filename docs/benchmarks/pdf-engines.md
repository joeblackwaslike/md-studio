# PDF engine benchmark

Date: 2026-11-22. Task 10 of slice 1. Decision: Docling stays the default PDF engine.

## Environment

- macOS 26.5.2, Apple M1 Max, 64 GB RAM, no CUDA. Python 3.12.15.
- docling 2.151.1 (docling-core 2.108.0, docling-ibm-models 4.0.4, docling-parse 7.27.0), torch 2.15.0, transformers 5.24.0.
- marker-pdf 2.2.0, onnxruntime 1.32.0.
- Docling with `AcceleratorOptions(device="auto")` resolves to MPS on this machine. Marker 2.2.0 picks its `fast` mode on Apple Silicon (ONNX layout and OCR, no VLM server), and that is the mode measured. Its `balanced` and `vllm` modes need a Surya VLM server and were not run.
- Package metadata licenses: docling MIT, marker-pdf Apache-2.0. Model weight licenses were not checked.
- Runs were sequential, warm (models already downloaded), one run per cell. Runtime is wall clock from `/usr/bin/time -l`, peak memory is its maximum resident set size.

## Inputs

1. The Hitchhiker's Guide to Agentic AI (arXiv 2606.24937), a 733 page, 7.4 MB book with an outline. Pages 51 to 100 only (Part I start: equations, Python listings, bullet lists, figures).
2. A research paper heavy on equations, 54 pages, 2.0 MB, with an outline and result tables. It has only 4 display equations, so it is a light test for math.
3. A product manual, 41 pages, 3.7 MB, with a 2 level outline and many screenshots.
4. A technical guide with tables and code listings, 40 pages, 0.3 MB, with a 3 level outline.

Inputs 2 to 4 are personal documents and are described by kind only.

## Results

Runtime in seconds, peak memory in MB.

| Config | Input | Runtime | Peak MB |
|---|---|---|---|
| Docling, formulas off | 1 | 29.7 | 2485 |
| Docling, formulas off | 2 | 67.3 | 3200 |
| Docling, formulas off | 3 | 70.9 | 3268 |
| Docling, formulas off | 4 | 15.7 | 1783 |
| Docling, formulas on | 1 | 2422 | 2901 |
| Docling, formulas on | 2 | 277.4 | 3461 |
| Docling, formulas on | 3 | 62.6 | 3790 |
| Docling, formulas on | 4 | 15.4 | 2117 |
| Marker, fast | 1 | 34.6 | 1647 |
| Marker, fast | 2 | 26.1 | 1866 |
| Marker, fast | 3 | 19.4 | 1475 |
| Marker, fast | 4 | 19.7 | 1276 |

Quality, same order of inputs (1, 2, 3, 4):

| Criterion | Docling | Marker (fast) |
|---|---|---|
| Headings emitted | 161, 51, 418, 107 | 175, 57, 360, 112 |
| Outline titles found among headings (substring match) | 71/71, 23/23, 65/66, 93/93 | 58/71, 23/23, 59/66, 89/93 |
| Heading levels | Always one level (`##`) | One or two levels, not matching the outline depth |
| Headings repeated 3 or more times (running headers) | 0, 0, 25, 20 | 0, 0, 25, 4 |
| Math | Off: every formula is a `<!-- formula-not-decoded -->` placeholder (51 on input 1). On: 51/51 and 4/4 decoded as LaTeX | LaTeX emitted without enrichment, but 3 of the 4 equations in input 2 are missing, and page numbers appear as `$$5 2$$` blocks (13 in input 1, 11 in input 2). Numbers in table cells are wrapped as inline math |
| Code blocks | 17, 2, 0, 16 fenced blocks, correctly classified. Line breaks and indentation are collapsed to one line | None detected. Code appears as headings or paragraphs, also with line breaks lost |
| Tables | 20, 17, 16, 6. Clean on data tables. A table of contents page was turned into a dot-leader table | Clean on the simple tables checked. Cell numbers get math noise (`$5 8 . 5 5 \%$`) |
| Reading order | Not scored in depth. No problems in the sampled sections | Same |
| Images | 11, 10, 99, 0 pictures, written to files with `generate_picture_images=True` | No image files in the default run, nor with `--extract_images true` |
| Block page numbers | Every block, 100% | Every block in JSON output |
| Failures | Formula enrichment on input 1 hit the 40 minute limit on the first attempt; a rerun with an 80 minute limit finished. No crashes or garbage output otherwise | None |

Math spot check, Docling with enrichment on (inputs 1 and 2, 9 checked): attention, MLA latent projection, Adam moment update, LoRA weight merge, F1 and regression equations all decoded correctly. The decoded text is letter spaced (`P r o b`) but valid LaTeX. A custom macro (`\sink`) and one `\tt` leaked through. Marker, 6 equations checked in input 1: 5 correct (the cross attention one has a misread subscript), plus noise blocks.

Heading outline: neither engine reproduces the PDF outline hierarchy. Both emit nearly flat headings, so chapter splitting and heading levels must come from the PDF outline (pypdf or pdfium), not from the converter.

## Per block page numbers

Docling: every item from `document.iterate_items()` has `item.prov[0].page_no` (1 based, the original PDF page even with `page_range`) and `item.prov[0].bbox`. The HTML export carries no page information, so the reader must walk the document model and write `data-page` itself. Pictures and tables have `prov` as well. In these runs, 100% of text, table and picture items had provenance.

Marker: use `--output_format json`. Each block has an id of the form `/page/<n>/<BlockType>/<k>`, where n is the 0 based page index in the original PDF, plus `bbox`, `polygon` and `section_hierarchy`. Markdown output has only occasional `<span id="page-N-M">` anchors, so JSON is the source for pages.

## Choice

Docling stays the default. It does not clearly lose.

1. It fences code, extracts images, and recovers every outline title as a heading. Marker detected no code blocks and extracted no images here.
2. Page numbers are available on every block with a stable, documented API.
3. MIT license and a typed document model.

Marker used less memory, was much faster than Docling with formulas on, faster with formulas off on inputs 2 and 3 (26 and 19 s against 67 and 71 s) and slightly slower on inputs 1 and 4, and handled simple tables slightly cleaner. Its math is usable but unreliable (missed equations, page numbers as math).

Settings for the Docling reader:

- Formula enrichment off by default. It cost about 47 seconds per formula on this machine (2417 s extra for 51 formulas on 50 pages), so it needs an opt-in flag and a progress message. With it off, formulas are lost as placeholders.
- Header and footer removal is not done by Docling in markdown or HTML, but items are labelled `page_header` and `page_footer`, and the reader should drop them to avoid the repeated false headings seen in inputs 3 and 4.
- Code blocks lose their line breaks, so the reader should not promise indentation preservation for PDFs.

Not tested: Marker `balanced` mode with a VLM server (likely better math), Docling hierarchical heading post processing, scanned PDFs.

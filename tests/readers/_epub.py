"""Shared helpers for the Markdown-export tests: minimal EPUB builders."""

import zipfile
from dataclasses import dataclass
from pathlib import Path

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CHAPTER_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{title}</title></head>
  <body><div id="sbo-rt-content">{body}</div></body>
</html>
"""


@dataclass(frozen=True)
class ChapterSpec:
    """A chapter to embed in a generated EPUB."""

    title: str
    body: str


def _manifest_item(chapter_index: int) -> str:
    """Render a single content.opf manifest ``<item>`` entry."""
    return (
        f'    <item id="ch{chapter_index}" href="ch{chapter_index}.xhtml" '
        'media-type="application/xhtml+xml"/>'
    )


def _itemref(chapter_index: int) -> str:
    """Render a single content.opf spine ``<itemref>`` entry."""
    return f'    <itemref idref="ch{chapter_index}"/>'


def _css_item(index: int) -> str:
    """Render a content.opf manifest ``<item>`` entry for stylesheet *index*."""
    return f'    <item id="css{index}" href="css/s{index}.css" media-type="text/css"/>'


def _content_opf(
    title: str, isbn: str, specs: list[ChapterSpec], stylesheets: tuple[str, ...] = ()
) -> str:
    """Render a minimal content.opf with metadata, manifest, and spine."""
    indices = range(len(specs))
    manifest_entries = [_manifest_item(index) for index in indices]
    manifest_entries.extend(_css_item(index) for index in range(len(stylesheets)))
    manifest_items = "\n".join(manifest_entries)
    itemrefs = [_itemref(index) for index in indices]
    refs = "\n".join(itemrefs)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>Ada Lovelace</dc:creator>
    <dc:publisher>O'Reilly Media, Inc.</dc:publisher>
    <dc:date>2024-01-02</dc:date>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">{isbn}</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{manifest_items}
  </manifest>
  <spine toc="ncx">
{refs}
  </spine>
</package>
"""


def _navpoint(chapter_index: int, spec: ChapterSpec) -> str:
    """Render a single toc.ncx ``<navPoint>`` block for one chapter."""
    nav_id = f"n{chapter_index}"
    play_order = chapter_index + 1
    content_src = f"ch{chapter_index}.xhtml"
    return f"""    <navPoint id="{nav_id}" playOrder="{play_order}">
      <navLabel><text>{spec.title}</text></navLabel>
      <content src="{content_src}"/>
    </navPoint>"""


def _toc_ncx(specs: list[ChapterSpec], *, labelled: bool = True) -> str:
    """Render a minimal toc.ncx mapping chapter files to nav labels."""
    navpoints = [_navpoint(index, spec) for index, spec in enumerate(specs)] if labelled else []
    points = "\n".join(navpoints)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
{points}
  </navMap>
</ncx>
"""


def build_epub(
    path: Path,
    title: str,
    specs: list[ChapterSpec],
    *,
    isbn: str = "9781234567890",
    stylesheets: tuple[str, ...] = (),
    labelled: bool = True,
) -> Path:
    """Write a minimal but valid EPUB to *path* and return it.

    Each entry of *stylesheets* becomes a ``text/css`` manifest item, in order. With
    ``labelled=False`` the NCX has no entries, so the reader falls back to file-stem titles.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _content_opf(title, isbn, specs, stylesheets))
        zf.writestr("OEBPS/toc.ncx", _toc_ncx(specs, labelled=labelled))
        for index, sheet in enumerate(stylesheets):
            zf.writestr(f"OEBPS/css/s{index}.css", sheet)
        for index, spec in enumerate(specs):
            xhtml = _CHAPTER_TEMPLATE.format(title=spec.title, body=spec.body)
            zf.writestr(f"OEBPS/ch{index}.xhtml", xhtml)
    return path


CSS_HEADINGS_STYLESHEET = """
.class-part { font-size: 2.333rem; font-weight: bold; }
.class-section { font-size: 1.667rem; }
.class-sub { font-size: 1.2rem; font-weight: 700; text-transform: uppercase; }
.class-body { font-size: 1rem; }
"""

CSS_HEADINGS_BODY = (
    '<div class="class-part">Part One</div>'
    '<div class="class-body">Plain body text.</div>'
    '<div class="class-section">Section A</div>'
    '<div class="class-body">More body text.</div>'
    '<div class="class-sub">Sub A1</div>'
)


def build_css_headings_epub(path: Path) -> Path:
    """Write an EPUB whose headings are CSS-styled ``div`` classes, not ``<hN>`` tags."""
    specs = [ChapterSpec("Chapter One", CSS_HEADINGS_BODY)]
    return build_epub(path, "Styled", specs, stylesheets=(CSS_HEADINGS_STYLESHEET,))


def corrupt_first_stylesheet(source: Path, dest: Path) -> Path:
    """Copy the EPUB at *source* to *dest* with the first CSS member's deflate data damaged."""
    with zipfile.ZipFile(source) as archive:
        member = archive.getinfo("OEBPS/css/s0.css")
        data_start = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    raw = source.read_bytes()
    dest.write_bytes(raw[:data_start] + b"\xff" * 4 + raw[data_start + 4 :])
    return dest

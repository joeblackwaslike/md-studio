#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["lxml"]
# ///

"""
epub_to_html.py — Convert an EPUB to a single self-contained HTML file.

All CSS is inlined into a single <style> block.
All images are embedded as base64 data URIs.
Chapters are concatenated in spine order with a generated TOC.

Usage:
    python epub_to_html.py <input.epub> [output.html]

Dependencies (all stdlib except lxml):
    lxml  — fast XML/HTML parsing
    (base64, mimetypes, zipfile, pathlib, re, etc. are all stdlib)

Install:
    uv add lxml
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

from lxml import etree

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EPUB namespace constants
# ---------------------------------------------------------------------------
NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class ManifestItem(NamedTuple):
    item_id: str
    href: str  # relative to OPF directory
    media_type: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ns(tag: str, namespace: str) -> str:
    """Build Clark-notation tag: {namespace}tag"""
    return f"{{{namespace}}}{tag}"


def _find_container_opf(epub_zip: zipfile.ZipFile) -> str:
    """
    Parse META-INF/container.xml and return the rootfile path
    (the .opf file path inside the ZIP).
    """
    with epub_zip.open("META-INF/container.xml") as f:
        tree = etree.parse(f)
    root = tree.getroot()
    rootfile = root.find(f".//{_ns('rootfile', NS_CONTAINER)}")
    if rootfile is None:
        raise ValueError("Cannot find rootfile in META-INF/container.xml")
    return rootfile.get("full-path")  # type: ignore[return-value]


def _parse_opf(
    epub_zip: zipfile.ZipFile, opf_path: str
) -> tuple[str, dict[str, ManifestItem], list[str]]:
    """
    Parse the OPF file.

    Returns:
        opf_dir     — directory prefix inside the zip (e.g. "OEBPS/")
        manifest    — {item_id: ManifestItem}
        spine_ids   — ordered list of manifest item ids from <spine>
    """
    opf_dir = str(Path(opf_path).parent)
    if opf_dir == ".":
        opf_dir = ""
    else:
        opf_dir = opf_dir + "/"

    with epub_zip.open(opf_path) as f:
        tree = etree.parse(f)
    root = tree.getroot()

    # Manifest
    manifest: dict[str, ManifestItem] = {}
    for item in root.findall(f".//{_ns('item', NS_OPF)}"):
        item_id = item.get("id", "")
        href = item.get("href", "")
        media_type = item.get("media-type", "")
        manifest[item_id] = ManifestItem(item_id, href, media_type)

    # Spine (reading order)
    spine_ids: list[str] = []
    spine_el = root.find(_ns("spine", NS_OPF))
    if spine_el is not None:
        for itemref in spine_el.findall(_ns("itemref", NS_OPF)):
            idref = itemref.get("idref", "")
            if idref:
                spine_ids.append(idref)

    return opf_dir, manifest, spine_ids


def _zip_read_text(epub_zip: zipfile.ZipFile, zip_path: str) -> str:
    """Read a text file from the ZIP, trying UTF-8 then latin-1."""
    data = epub_zip.read(zip_path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _zip_read_bytes(epub_zip: zipfile.ZipFile, zip_path: str) -> bytes:
    return epub_zip.read(zip_path)


def _normalize_zip_path(base_dir: str, relative_href: str) -> str:
    """
    Resolve a relative href against a base directory to a normalised
    zip-internal path (no leading slash, no ./ prefix, .. collapsed).

    Args:
        base_dir:      Directory prefix ending in "/" (e.g. "OEBPS/" or
                       "OEBPS/xhtml/"), OR empty string for root.
        relative_href: The href value, possibly containing "../" segments.
                       Fragment (#...) is stripped before resolution.
    """
    import os

    # Strip fragment
    href = relative_href.split("#")[0]
    # os.path.normpath handles .. collapse correctly without touching the FS
    full = os.path.normpath(base_dir + href).replace("\\", "/")
    # normpath may produce a leading "./" — strip it
    if full.startswith("./"):
        full = full[2:]
    return full


def _image_to_data_uri(data: bytes, media_type: str) -> str:
    """Encode raw image bytes as a base64 data URI."""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{b64}"


# ---------------------------------------------------------------------------
# TOC enhancement - convert existing epub TOC to nested semantic structure
# ---------------------------------------------------------------------------


def _enhance_toc_chapter(body: etree._Element, chapter_id: str) -> bool:
    """
    Enhance the TOC chapter (typically xhtml-0-3) in place by converting
    its flat divs with CSS classes into a nested semantic <nav><ol> structure.

    Returns True if this was detected as a TOC chapter and enhanced.
    """
    # Heuristic: TOC chapters typically have many <a> links and divs with
    # class patterns like class-0-90, class-0-91, class-0-93, etc.
    # Elements may be namespaced, so search with wildcard namespace
    links = body.findall(".//{*}a")  # namespace-agnostic
    if len(links) < 20:  # arbitrary threshold
        return False

    # Check for the telltale class patterns
    divs_with_classes = [
        div
        for div in body.findall(".//{*}div")
        if div.get("class", "").startswith("class-0-")
    ]
    if len(divs_with_classes) < 20:
        return False

    # Looks like a TOC — extract entries
    entries: list[tuple[str, str, str]] = []  # (class, href, text)
    for a in links:
        parent = a.getparent()
        if parent is None:
            continue
        cls = parent.get("class", "").strip()
        href = a.get("href", "").strip()
        text = "".join(a.itertext()).strip()
        if href and text and cls.startswith("class-0-"):
            entries.append((cls, href, text))

    if not entries:
        return False

    # Map CSS classes to nesting levels
    CLASS_TO_LEVEL = {
        "class-0-91": 1,  # Part 0 header
        "class-0-115": 1,  # Part headers
        "class-0-311": 1,  # Appendix sections
        "class-0-93": 2,  # Chapters
        "class-0-95": 3,  # Subsections
        "class-0-101": 4,  # Sub-subsections
        "class-0-107": 4,  # Deep subsections
    }

    # Build nested structure
    root_ol = etree.Element("ol")
    stack: list[tuple[int, etree._Element]] = [(0, root_ol)]

    for cls, href, text in entries:
        level = CLASS_TO_LEVEL.get(cls, 3)

        # Pop stack to find parent
        while stack and stack[-1][0] >= level:
            stack.pop()
        if not stack:
            stack.append((0, root_ol))

        parent_level, parent_ol = stack[-1]

        # Create <li> and <a>
        li = etree.SubElement(parent_ol, "li")
        a = etree.SubElement(li, "a")
        a.set("href", href)
        a.text = text

        # Prepare sub-<ol> for potential children
        sub_ol = etree.SubElement(li, "ol")
        stack.append((level, sub_ol))

    # Remove empty <ol> elements
    def _remove_empty_ols(element: etree._Element) -> None:
        for child in list(element):
            if child.tag == "ol" and len(child) == 0:
                element.remove(child)
            else:
                _remove_empty_ols(child)

    _remove_empty_ols(root_ol)

    # Replace body contents with semantic TOC
    # Keep first element if it's a heading/title
    first_el = body[0] if len(body) > 0 else None
    keep_first = first_el is not None and (
        etree.QName(first_el.tag).localname in ("h1", "h2", "div")
        and "Contents" in "".join(first_el.itertext())
    )

    # Clear body and rebuild
    for child in list(body):
        body.remove(child)

    if keep_first and first_el is not None:
        body.append(first_el)

    # Wrap in <nav>
    nav = etree.SubElement(body, "nav")
    nav.append(root_ol)

    return True


# ---------------------------------------------------------------------------
# NCX / NAV title map
# ---------------------------------------------------------------------------


def _build_title_map(
    epub_zip: zipfile.ZipFile,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
) -> dict[str, str]:
    """
    Build a mapping of zip_path -> chapter title from the NCX or NAV document.

    Keys are normalised zip paths (e.g. "OEBPS/xhtml/chapter1.xhtml").
    The fragment portion of the src/href is stripped for the key lookup,
    so a navPoint with src="xhtml/ch1.xhtml#aid_123" maps to
    "OEBPS/xhtml/ch1.xhtml".

    Returns an empty dict if neither NCX nor NAV is found.
    """
    title_map: dict[str, str] = {}

    ncx_item = next(
        (
            item
            for item in manifest.values()
            if item.media_type == "application/x-dtbncx+xml"
        ),
        None,
    )
    nav_item = next(
        (
            item
            for item in manifest.values()
            if "nav" in item.item_id.lower() or item.href.endswith("nav.xhtml")
        ),
        None,
    )

    # --- NCX (epub2) ---
    if ncx_item is not None:
        zip_path = _normalize_zip_path(opf_dir, ncx_item.href)
        try:
            with epub_zip.open(zip_path) as f:
                tree = etree.parse(f)
            NS_NCX = "http://www.daisy.org/z3986/2005/ncx/"
            for nav_point in tree.findall(f".//{_ns('navPoint', NS_NCX)}"):
                label = nav_point.find(f".//{_ns('text', NS_NCX)}")
                content = nav_point.find(_ns("content", NS_NCX))
                if label is None or content is None:
                    continue
                text = (label.text or "").strip()
                src = content.get("src", "")
                if text and src:
                    resolved = _normalize_zip_path(opf_dir, src.split("#")[0])
                    title_map[resolved] = text
        except (KeyError, etree.XMLSyntaxError) as e:
            log.warning("Could not parse NCX: %s", e)

    # --- NAV (epub3) — fill gaps not covered by NCX ---
    if nav_item is not None:
        zip_path = _normalize_zip_path(opf_dir, nav_item.href)
        try:
            with epub_zip.open(zip_path) as f:
                tree = etree.parse(f)
            nav_dir = str(Path(zip_path).parent.as_posix())
            nav_dir = "" if nav_dir == "." else nav_dir + "/"
            for a in tree.findall(f".//{_ns('a', NS_XHTML)}"):
                text = "".join(a.itertext()).strip()
                href = a.get("href", "")
                if text and href and not href.startswith("http"):
                    resolved = _normalize_zip_path(nav_dir, href.split("#")[0])
                    if resolved not in title_map:  # NCX takes priority
                        title_map[resolved] = text
        except (KeyError, etree.XMLSyntaxError) as e:
            log.warning("Could not parse NAV: %s", e)

    return title_map


def _first_body_text(body: etree._Element) -> str:
    """
    Return the first non-trivial text string found in the body.
    Skips pure-digit strings (page numbers) and very short strings.
    """
    for el in body.iter():
        text = (el.text or "").strip()
        if text and len(text) > 3 and not text.isdigit():
            return text[:80]
    return ""


# ---------------------------------------------------------------------------
# CSS collection
# ---------------------------------------------------------------------------


def _collect_css(
    epub_zip: zipfile.ZipFile,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
) -> str:
    """
    Concatenate all CSS files from the manifest into a single string.
    Relative url() references inside CSS are rewritten to data URIs
    so they still resolve inside the single-file output.
    """
    css_items = [
        item
        for item in manifest.values()
        if item.media_type in ("text/css", "application/css")
    ]

    parts: list[str] = []
    for item in css_items:
        zip_path = _normalize_zip_path(opf_dir, item.href)
        try:
            css_text = _zip_read_text(epub_zip, zip_path)
        except KeyError:
            log.warning("CSS file not found in zip: %s", zip_path)
            continue

        css_dir = str(Path(zip_path).parent)
        if css_dir == ".":
            css_dir = ""
        else:
            css_dir = css_dir + "/"

        # Rewrite url(...) references inside the CSS to data URIs
        def _rewrite_url(m: re.Match) -> str:
            raw = m.group(1).strip().strip("'\"")
            if raw.startswith("data:") or raw.startswith("http"):
                return m.group(0)
            asset_path = str(Path(css_dir + raw).as_posix())
            try:
                asset_bytes = _zip_read_bytes(epub_zip, asset_path)
                guessed_type, _ = mimetypes.guess_type(asset_path)
                mt = guessed_type or "application/octet-stream"
                return f"url({_image_to_data_uri(asset_bytes, mt)})"
            except KeyError:
                log.warning("CSS asset not found: %s", asset_path)
                return m.group(0)

        css_text = re.sub(r"url\(([^)]+)\)", _rewrite_url, css_text)
        parts.append(f"/* === {item.href} === */\n{css_text}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Image map
# ---------------------------------------------------------------------------


def _build_image_map(
    epub_zip: zipfile.ZipFile,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
) -> dict[str, str]:
    """
    Pre-build a mapping of every image in the manifest:
        zip_internal_path  →  data:image/...;base64,...

    We key by the normalised zip path so XHTML src= rewrites are fast.
    """
    image_map: dict[str, str] = {}
    image_types = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/svg+xml",
        "image/webp",
        "image/bmp",
    }
    for item in manifest.values():
        if item.media_type in image_types:
            zip_path = _normalize_zip_path(opf_dir, item.href)
            try:
                data = _zip_read_bytes(epub_zip, zip_path)
                image_map[zip_path] = _image_to_data_uri(data, item.media_type)
            except KeyError:
                log.warning("Image not found in zip: %s", zip_path)
    return image_map


# ---------------------------------------------------------------------------
# Per-chapter XHTML processing
# ---------------------------------------------------------------------------

_XHTML_PARSER = etree.XMLParser(
    recover=True,
    remove_comments=False,
    no_network=True,
    resolve_entities=False,
)


def _chapter_zip_dir(zip_path: str) -> str:
    """Return the directory prefix of a zip path (with trailing slash)."""
    parent = str(Path(zip_path).parent.as_posix())
    return "" if parent == "." else parent + "/"


def _rewrite_fragment_id(chapter_zip_path: str, fragment: str) -> str:
    """
    Convert a fragment id from a chapter into a globally unique anchor id.
    We use __ as separator because - and _ appear in real ids.
    """
    base = chapter_zip_path.replace("/", "_").replace(".", "_")
    return f"{base}__{fragment}" if fragment else base


def _process_chapter(
    epub_zip: zipfile.ZipFile,
    zip_path: str,
    image_map: dict[str, str],
    all_zip_paths: set[str],
    chapter_index: int,
    title_map: dict[str, str],
) -> tuple[str, str]:
    """
    Parse one XHTML chapter, rewrite its internals, and return:
        (chapter_title, body_inner_html)

    Title resolution priority:
        1. NCX/NAV title map (authoritative)
        2. First substantive text in <body> (covers chapters not in nav)
        3. <title> element (usually the book title — last resort)
        4. "Chapter N" fallback

    Transformations applied:
    - <link rel="stylesheet"> tags removed (CSS already embedded globally)
    - <img src="..."> rewritten to data URIs
    - id="foo" on any element gets a namespace prefix so it's globally unique
    - href="#foo"          -> href="#<namespaced-id>"
    - href="other.xhtml"  -> href="#<namespaced-anchor-for-other-file>"
    - href="other.xhtml#bar" -> href="#<namespaced-id-in-other-file>"
    - External href (http/https/mailto) -- left unchanged
    """
    chap_dir = _chapter_zip_dir(zip_path)
    id_prefix = zip_path.replace("/", "_").replace(".", "_")

    try:
        raw = _zip_read_bytes(epub_zip, zip_path)
    except KeyError:
        log.error("Chapter not found in zip: %s", zip_path)
        return ("Missing chapter", "")

    tree = etree.fromstring(raw, parser=_XHTML_PARSER)

    # Title resolution: NCX/NAV > first body text > <title> tag > fallback
    nav_title = title_map.get(zip_path)

    body = tree.find(f".//{_ns('body', NS_XHTML)}")
    if body is None:
        body = tree.find(".//body")

    if nav_title:
        chapter_title = nav_title
    elif body is not None:
        first_text = _first_body_text(body)
        if first_text:
            chapter_title = first_text
        else:
            title_el = tree.find(f".//{_ns('title', NS_XHTML)}")
            if title_el is None:
                title_el = tree.find(".//title")
            chapter_title = (
                (title_el.text or "").strip()
                if title_el is not None
                else f"Chapter {chapter_index + 1}"
            )
    else:
        title_el = tree.find(f".//{_ns('title', NS_XHTML)}")
        if title_el is None:
            title_el = tree.find(".//title")
        chapter_title = (
            (title_el.text or "").strip()
            if title_el is not None
            else f"Chapter {chapter_index + 1}"
        )
    if body is None:
        log.warning("No <body> found in %s", zip_path)
        return (chapter_title, "")

    # -----------------------------------------------------------------------
    # Special handling: enhance TOC chapter BEFORE rewrites
    # This clears and rebuilds the body, then the element walk below will
    # rewrite the new structure's hrefs/IDs
    # -----------------------------------------------------------------------
    is_toc_chapter = _enhance_toc_chapter(body, zip_path)

    # -----------------------------------------------------------------------
    # Walk every element in the body (including newly enhanced TOC if applicable)
    # -----------------------------------------------------------------------
    for el in body.iter():
        tag = etree.QName(el.tag).localname if isinstance(el.tag, str) else None
        if tag is None:
            continue

        # --- Namespace all id= attributes so they're globally unique --------
        el_id = el.get("id")
        if el_id:
            el.set("id", _rewrite_fragment_id(zip_path, el_id))

        # --- <link> tags: strip stylesheet references -----------------------
        if tag == "link" and el.get("rel") == "stylesheet":
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
            continue

        # --- <img>: rewrite src to data URI ---------------------------------
        if tag == "img":
            src = el.get("src", "")
            if src and not src.startswith("data:"):
                abs_src = _normalize_zip_path(chap_dir, src)
                data_uri = image_map.get(abs_src)
                if data_uri:
                    el.set("src", data_uri)
                else:
                    log.warning("Image not in map: %s (resolved from %s)", abs_src, src)

        # --- <a href>: rewrite internal links --------------------------------
        href = el.get("href", "")
        if href and not href.startswith(("http://", "https://", "mailto:")):
            if href.startswith("#"):
                # Same-document fragment → namespace it
                fragment = href[1:]
                el.set("href", "#" + _rewrite_fragment_id(zip_path, fragment))
            else:
                # Cross-document link: "other.xhtml" or "other.xhtml#id"
                parts = href.split("#", 1)
                target_file = parts[0]
                target_frag = parts[1] if len(parts) > 1 else ""

                # Resolve relative to this chapter's directory
                abs_target = _normalize_zip_path(chap_dir, target_file)

                if abs_target in all_zip_paths:
                    new_frag = _rewrite_fragment_id(abs_target, target_frag)
                    el.set("href", "#" + new_frag)
                else:
                    # Target not in this epub — leave as-is (external or asset)
                    pass

    # Serialise body contents (children only, not the <body> tag itself)
    # Special case: if body was enhanced (e.g. TOC chapter), serialize it differently
    parts: list[str] = []
    if body.text:
        parts.append(body.text)
    for child in body:
        parts.append(etree.tostring(child, encoding="unicode", method="html"))

    body_html = "\n".join(parts)
    return (chapter_title, body_html)


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    /* ===== epub_to_html.py baseline reset ===== */
    body {{
      max-width: 80ch;
      margin: 2rem auto;
      padding: 0 1.5rem;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1rem;
      line-height: 1.7;
      color: #1a1a1a;
      background: #fafaf8;
    }}
    h1, h2, h3, h4, h5, h6 {{
      font-family: system-ui, sans-serif;
      line-height: 1.3;
      margin-top: 2.5rem;
    }}
    /* Enhanced TOC styling for the Contents chapter */
    section.toc-chapter {{
      border: 1px solid #ddd;
      background: #f5f5f0;
      padding: 1.25rem 1.75rem;
      margin: 3rem 0;
      border-radius: 4px;
    }}
    section.toc-chapter nav ol {{ 
      margin: 0; 
      padding-left: 1.5rem;
      list-style: none;
    }}
    section.toc-chapter nav > ol {{ padding-left: 0; }}
    section.toc-chapter nav li {{ margin: 0.25rem 0; }}
    section.toc-chapter nav ol ol {{ 
      margin-top: 0.25rem;
      padding-left: 1.5rem;
    }}
    section.toc-chapter nav a {{ 
      text-decoration: none; 
      color: #1a6fa8;
    }}
    section.toc-chapter nav a:hover {{ text-decoration: underline; }}
    .epub-chapter {{
      border-top: 2px solid #ddd;
      padding-top: 2rem;
      margin-top: 3rem;
    }}
    img {{ max-width: 100%; height: auto; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1.5rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem 0.75rem; }}
    pre, code {{ font-family: 'Courier New', monospace; font-size: 0.9em; }}
    pre {{ background: #f0f0ec; padding: 1rem; overflow-x: auto; border-radius: 3px; }}
    blockquote {{ border-left: 3px solid #aaa; margin: 1rem 0; padding: 0.5rem 1rem; color: #555; }}
    a {{ color: #1a6fa8; }}
    /* ===== EPUB original CSS ===== */
{epub_css}
  </style>
</head>
<body>
{chapters}
</body>
</html>
"""


def convert_epub_to_html(epub_path: Path, output_path: Path) -> None:
    """
    Main entry point: convert epub_path to a single self-contained HTML file
    at output_path.
    """
    print(f"📦 Opening EPUB: {epub_path.name}")

    with zipfile.ZipFile(epub_path, "r") as epub_zip:
        # ---- Parse OPF -----------------------------------------------------
        opf_path = _find_container_opf(epub_zip)
        print(f"📄 OPF: {opf_path}")
        opf_dir, manifest, spine_ids = _parse_opf(epub_zip, opf_path)
        print(f"   {len(manifest)} manifest items · {len(spine_ids)} spine items")

        # ---- Book title from OPF dc:title ----------------------------------
        with epub_zip.open(opf_path) as f:
            opf_tree = etree.parse(f)
        title_el = opf_tree.find(f".//{_ns('title', NS_DC)}")
        book_title = (
            (title_el.text or "EPUB").strip() if title_el is not None else "EPUB"
        )
        print(f"📚 Title: {book_title}")

        # ---- Collect CSS ---------------------------------------------------
        print("🎨 Collecting CSS...")
        epub_css = _collect_css(epub_zip, opf_dir, manifest)
        # Indent each line for embedding inside <style>
        epub_css_indented = "\n".join("    " + line for line in epub_css.splitlines())
        print(f"   {len(epub_css):,} chars of CSS")

        # ---- Build image map -----------------------------------------------
        print("🖼  Encoding images as data URIs...")
        image_map = _build_image_map(epub_zip, opf_dir, manifest)
        print(f"   {len(image_map)} images encoded")

        # ---- Build title map from NCX/NAV ----------------------------------
        print("📋 Building title map from NCX/NAV...")
        title_map = _build_title_map(epub_zip, opf_dir, manifest)
        print(f"   {len(title_map)} titled entries found")

        # ---- Compute set of all xhtml zip paths for cross-link resolution --
        all_xhtml_zip_paths: set[str] = {
            _normalize_zip_path(opf_dir, item.href)
            for item in manifest.values()
            if "xhtml" in item.media_type or item.href.endswith(".xhtml")
        }

        # ---- Process each spine chapter ------------------------------------
        print(f"📝 Processing {len(spine_ids)} chapters...")
        toc_entries: list[tuple[str, str]] = []  # (anchor_id, title)
        chapter_html_parts: list[str] = []

        for idx, spine_id in enumerate(spine_ids):
            item = manifest.get(spine_id)
            if item is None:
                log.warning("Spine item not found in manifest: %s", spine_id)
                continue

            # Only process XHTML documents
            if not (
                "xhtml" in item.media_type
                or "html" in item.media_type
                or item.href.endswith((".xhtml", ".html", ".htm"))
            ):
                continue

            zip_path = _normalize_zip_path(opf_dir, item.href)
            chapter_anchor = _rewrite_fragment_id(zip_path, "")

            title, body_html = _process_chapter(
                epub_zip, zip_path, image_map, all_xhtml_zip_paths, idx, title_map
            )

            if not body_html.strip():
                continue  # skip blank chapters

            toc_entries.append((chapter_anchor, title))

            # Check if this is the TOC chapter (heuristic: contains <nav> element)
            is_toc = "<nav>" in body_html or "nav>" in body_html
            section_class = (
                'class="epub-chapter toc-chapter"' if is_toc else 'class="epub-chapter"'
            )

            chapter_html_parts.append(
                f'<section id="{chapter_anchor}" {section_class}>\n'
                f"{body_html}\n"
                f"</section>"
            )

            if (idx + 1) % 10 == 0 or (idx + 1) == len(spine_ids):
                print(f"   {idx + 1}/{len(spine_ids)} chapters processed")

    # ---- Assemble final HTML -----------------------------------------------
    print("🔗 Assembling single-file HTML...")

    chapters_html = "\n\n".join(chapter_html_parts)

    html_output = _HTML_TEMPLATE.format(
        title=book_title,
        epub_css=epub_css_indented,
        chapters=chapters_html,
    )

    output_path.write_text(html_output, encoding="utf-8")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Output: {output_path}")
    print(
        f"   {size_mb:.1f} MB · {len(toc_entries)} chapters · {len(image_map)} images embedded"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python epub_to_html.py <input.epub> [output.html]")
        sys.exit(1)

    epub_path = Path(sys.argv[1])
    if not epub_path.exists():
        print(f"Error: file not found: {epub_path}")
        sys.exit(1)

    output_path = (
        Path(sys.argv[2]) if len(sys.argv) > 2 else epub_path.with_suffix(".html")
    )

    convert_epub_to_html(epub_path, output_path)


if __name__ == "__main__":
    main()

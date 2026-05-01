#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["lxml", "cssutils"]
# ///

"""
EPUB Heading Fixer - Converts CSS-styled divs to semantic HTML headings

This script:
1. Extracts an EPUB file
2. Analyzes CSS to identify heading classes by font-size
3. Converts div elements with heading classes to proper h1-h6 tags
4. Generates an audit report showing all conversions
5. Creates a fixed EPUB with semantic HTML
"""

import re
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import shutil
from lxml import etree
from dataclasses import dataclass
import cssutils
import logging

# Suppress cssutils warnings
cssutils.log.setLevel(logging.ERROR)


@dataclass
class HeadingClass:
    """Represents a CSS class that styles a heading"""

    class_name: str
    font_size: float  # in rem
    font_weight: str
    text_transform: str
    heading_level: int  # h1, h2, h3, etc.


class EPUBHeadingFixer:
    """Fixes EPUB files by converting CSS-styled headings to semantic HTML"""

    def __init__(self, epub_path: str):
        self.epub_path = Path(epub_path)
        self.extract_dir = Path("/tmp/epub_fix_work")
        self.heading_classes: Dict[str, HeadingClass] = {}
        self.conversions: List[Tuple[str, str, str]] = []  # (file, old, new)

    def extract_epub(self) -> Path:
        """Extract EPUB to working directory"""
        if self.extract_dir.exists():
            shutil.rmtree(self.extract_dir)
        self.extract_dir.mkdir(parents=True)

        print(f"📦 Extracting EPUB: {self.epub_path.name}")
        with zipfile.ZipFile(self.epub_path, "r") as zip_ref:
            zip_ref.extractall(self.extract_dir)

        return self.extract_dir

    def find_oebps_dir(self) -> Path:
        """Find the OEBPS directory (content directory)"""
        # Common locations
        for candidate in [
            self.extract_dir / "OEBPS",
            self.extract_dir / "OPS",
            self.extract_dir / "EPUB",
        ]:
            if candidate.exists():
                return candidate

        # Fallback: find any directory with xhtml files
        for path in self.extract_dir.rglob("*.xhtml"):
            return path.parent.parent

        raise ValueError("Could not find OEBPS/content directory")

    def analyze_css_files(self, oebps_dir: Path) -> None:
        """Analyze all CSS files to identify heading classes"""
        css_dir = oebps_dir / "css"
        if not css_dir.exists():
            print("⚠️  No CSS directory found")
            return

        print(f"\n🎨 Analyzing CSS files in {css_dir}")

        # Collect all heading-like classes
        heading_candidates: Dict[str, Dict] = {}

        for css_file in sorted(css_dir.glob("*.css")):
            sheet = cssutils.parseFile(str(css_file))

            for rule in sheet:
                if rule.type == rule.STYLE_RULE:
                    # Get class name
                    selector = rule.selectorText
                    if not selector.startswith(".class-"):
                        continue

                    class_name = selector[1:]  # Remove leading dot

                    # Extract relevant properties
                    font_size_str = rule.style.getPropertyValue("font-size")
                    font_weight = rule.style.getPropertyValue("font-weight")
                    text_transform = rule.style.getPropertyValue("text-transform")

                    # Parse font-size (e.g., "1.667rem")
                    if "rem" in font_size_str:
                        try:
                            font_size = float(font_size_str.replace("rem", "").strip())

                            # Consider it a heading if:
                            # 1. font-size >= 1.3rem OR
                            # 2. font-weight is bold/semibold and size >= 1.1rem
                            is_bold = font_weight in [
                                "bold",
                                "semibold",
                                "600",
                                "700",
                                "800",
                                "900",
                            ]
                            is_uppercase = text_transform == "uppercase"

                            if font_size >= 1.3 or (is_bold and font_size >= 1.1):
                                heading_candidates[class_name] = {
                                    "font_size": font_size,
                                    "font_weight": font_weight,
                                    "text_transform": text_transform,
                                    "is_bold": is_bold,
                                    "is_uppercase": is_uppercase,
                                }
                        except ValueError:
                            pass

        # Sort by font size (descending) and assign heading levels
        sorted_classes = sorted(
            heading_candidates.items(),
            key=lambda x: (x[1]["font_size"], x[1]["is_uppercase"]),
            reverse=True,
        )

        # Assign heading levels
        # Group by font size ranges
        size_groups = []
        current_size = None
        current_group = []

        for class_name, props in sorted_classes:
            size = props["font_size"]
            if current_size is None or abs(size - current_size) < 0.1:
                current_group.append((class_name, props))
                current_size = size
            else:
                if current_group:
                    size_groups.append(current_group)
                current_group = [(class_name, props)]
                current_size = size

        if current_group:
            size_groups.append(current_group)

        # Assign levels based on groups
        for level, group in enumerate(size_groups, start=1):
            if level > 6:
                level = 6  # Max h6

            for class_name, props in group:
                self.heading_classes[class_name] = HeadingClass(
                    class_name=class_name,
                    font_size=props["font_size"],
                    font_weight=props["font_weight"],
                    text_transform=props["text_transform"],
                    heading_level=level,
                )

        print(f"✅ Found {len(self.heading_classes)} heading classes:")
        for hc in sorted(
            self.heading_classes.values(), key=lambda x: x.font_size, reverse=True
        ):
            print(f"   {hc.class_name} → h{hc.heading_level} (size: {hc.font_size}rem)")

    def fix_xhtml_file(self, xhtml_file: Path) -> int:
        """Fix a single XHTML file, return number of conversions"""
        conversions_made = 0

        # Parse with lxml to handle XML namespaces properly
        try:
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(str(xhtml_file), parser)
            root = tree.getroot()

            # Get namespace
            nsmap = root.nsmap
            ns = nsmap[None] if None in nsmap else "http://www.w3.org/1999/xhtml"

            # Find all div elements with heading classes
            for div in root.xpath(".//xhtml:div", namespaces={"xhtml": ns}):
                class_attr = div.get("class")
                if not class_attr:
                    continue

                # Check if this class is a heading
                if class_attr in self.heading_classes:
                    hc = self.heading_classes[class_attr]

                    # Convert to heading tag
                    heading_tag = f"{{{ns}}}h{hc.heading_level}"

                    # Get the text content and attributes
                    text = div.text or ""
                    tail = div.tail
                    attribs = dict(div.attrib)
                    children = list(div)

                    # Remove the class attribute since it's for div styling, not heading styling
                    if "class" in attribs:
                        del attribs["class"]

                    # Create new heading element
                    new_heading = etree.Element(heading_tag, attribs)
                    new_heading.text = text
                    new_heading.tail = tail

                    # Copy children
                    for child in children:
                        new_heading.append(child)

                    # Replace in parent
                    parent = div.getparent()
                    if parent is not None:
                        index = list(parent).index(div)
                        parent.remove(div)
                        parent.insert(index, new_heading)

                        # Track conversion
                        heading_text = "".join(new_heading.itertext()).strip()[:60]
                        self.conversions.append(
                            (xhtml_file.name, f"h{hc.heading_level}", heading_text)
                        )
                        conversions_made += 1

            # Write back
            tree.write(
                str(xhtml_file),
                encoding="utf-8",
                xml_declaration=True,
                pretty_print=False,
            )

        except Exception as e:
            print(f"⚠️  Error processing {xhtml_file.name}: {e}")

        return conversions_made

    def fix_all_xhtml_files(self, oebps_dir: Path) -> None:
        """Fix all XHTML files in the EPUB"""
        xhtml_files = list(oebps_dir.rglob("*.xhtml"))
        print(f"\n🔧 Processing {len(xhtml_files)} XHTML files...")

        total_conversions = 0
        for xhtml_file in sorted(xhtml_files):
            conversions = self.fix_xhtml_file(xhtml_file)
            if conversions > 0:
                print(f"   ✓ {xhtml_file.name}: {conversions} headings converted")
                total_conversions += conversions

        print(f"\n✅ Total conversions: {total_conversions}")

    def remove_css_files(self, oebps_dir: Path) -> None:
        """Remove CSS files and references to prevent markitdown from converting them"""
        print("\n🧹 Cleaning up CSS files...")

        # Remove CSS directory
        css_dir = oebps_dir / "css"
        if css_dir.exists():
            shutil.rmtree(css_dir)
            print("   ✓ Removed CSS directory")

            # Remove CSS link references from XHTML files
            print("   🔗 Removing CSS link tags from XHTML files...")
            xhtml_files = list(oebps_dir.rglob("*.xhtml"))

            ns = {"xhtml": "http://www.w3.org/1999/xhtml"}
            for xhtml_file in xhtml_files:
                try:
                    tree = etree.parse(str(xhtml_file))
                    root = tree.getroot()

                    # Find and remove <link> tags that reference CSS
                    links_removed = 0
                    for link in root.xpath(
                        '//xhtml:link[@rel="stylesheet"]', namespaces=ns
                    ):
                        link.getparent().remove(link)
                        links_removed += 1

                    if links_removed > 0:
                        # Write back the modified file
                        tree.write(
                            str(xhtml_file),
                            encoding="utf-8",
                            xml_declaration=True,
                            pretty_print=False,
                        )
                except Exception as e:
                    print(f"      ⚠️  Error removing CSS refs in {xhtml_file.name}: {e}")

            print(f"   ✓ Removed CSS references from {len(xhtml_files)} files")
        else:
            print("   ℹ  No CSS directory found")

    def create_audit_report(self, output_file: Path) -> None:
        """Create a detailed audit report of all conversions"""
        print(f"\n📊 Creating audit report: {output_file}")

        # Group by file
        by_file = defaultdict(list)
        by_level = defaultdict(int)

        for file, level, text in self.conversions:
            by_file[file].append((level, text))
            by_level[level] += 1

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# EPUB Heading Conversion Audit Report\n\n")
            f.write(f"**Source EPUB:** {self.epub_path.name}\n\n")
            f.write(f"**Total Conversions:** {len(self.conversions)}\n\n")

            # Summary by heading level
            f.write("## Summary by Heading Level\n\n")
            for level in sorted(by_level.keys(), key=lambda x: int(x[1])):
                f.write(f"- **{level}**: {by_level[level]} occurrences\n")

            # CSS Classes identified
            f.write("\n## CSS Classes Converted\n\n")
            f.write("| Class Name | Font Size | Heading Level |\n")
            f.write("|------------|-----------|---------------|\n")
            for hc in sorted(
                self.heading_classes.values(), key=lambda x: x.font_size, reverse=True
            ):
                f.write(
                    f"| {hc.class_name} | {hc.font_size}rem | h{hc.heading_level} |\n"
                )

            # Detailed conversion log by file
            f.write("\n## Detailed Conversion Log\n\n")
            for file in sorted(by_file.keys()):
                f.write(f"### {file}\n\n")
                for level, text in by_file[file]:
                    # Escape markdown special chars
                    text = text.replace("|", "\\|").replace("\n", " ")
                    f.write(f"- **{level}**: {text}\n")
                f.write("\n")

        print("✅ Audit report created")

    def create_fixed_epub(self, output_path: Path) -> None:
        """Create a new EPUB from the fixed content"""
        print(f"\n📚 Creating fixed EPUB: {output_path.name}")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as epub_zip:
            # First, add mimetype (uncompressed, first file)
            mimetype_file = self.extract_dir / "mimetype"
            if mimetype_file.exists():
                epub_zip.write(
                    mimetype_file, "mimetype", compress_type=zipfile.ZIP_STORED
                )

            # Add all other files
            for file_path in sorted(self.extract_dir.rglob("*")):
                if file_path.is_file() and file_path.name != "mimetype":
                    arcname = str(file_path.relative_to(self.extract_dir))
                    epub_zip.write(file_path, arcname)

        print(f"✅ Fixed EPUB created: {output_path}")

    def convert_to_markdown(self, epub_path: Path, output_md: Path) -> int:
        """
        Convert EPUB to markdown via markitdown, then remove dangling inline
        footnote citations of the form [[N]](xhtml-*.xhtml#aid_*).

        These are intra-EPUB cross-reference anchors that become broken links
        in plain markdown.  They are distinguished from the real footnote
        definition lines (which use single brackets: [N] followed by text)
        by the double-bracket syntax [[N]] directly adjoining the link target.

        Returns the number of citations removed.
        """
        try:
            import markitdown as _md_module
        except ImportError:
            print("\n⚠️  markitdown not installed — skipping markdown conversion.")
            print("    Install with: pip install markitdown")
            return 0

        print("\n📝 Converting EPUB to markdown...")
        md_converter = _md_module.MarkItDown()
        result = md_converter.convert(str(epub_path))
        text = result.text_content

        # Remove inline citation anchors: [[N]](xhtml-*.xhtml#aid_*)
        # Double-bracket [[N]] is ONLY used for inline citations — the footnote
        # definition sections use single brackets [N] followed by content text,
        # so this pattern has zero false positives.
        cleaned, count = re.subn(r"\[\[\d+\]\]\(xhtml-[^)]+\)", "", text)

        output_md.write_text(cleaned, encoding="utf-8")

        lines = len(cleaned.splitlines())
        headings = sum(1 for l in cleaned.splitlines() if l.startswith("#"))
        print(f"   ✓ Removed {count} inline footnote citation(s)")
        print(f"   ✓ Markdown saved: {output_md.name}")
        print(f"   📊 {lines:,} lines · {headings} headings · {len(cleaned):,} chars")
        return count

    def run(
        self, output_epub: Path, audit_report: Path, output_md: Path | None = None
    ) -> None:
        """Main execution flow"""
        print("=" * 70)
        print("EPUB HEADING FIXER")
        print("=" * 70)

        # Extract
        self.extract_epub()
        oebps_dir = self.find_oebps_dir()
        print(f"📁 Content directory: {oebps_dir}")

        # Analyze CSS
        self.analyze_css_files(oebps_dir)

        if not self.heading_classes:
            print("\n⚠️  No heading classes found! EPUB may already use semantic HTML.")
            return

        # Fix XHTML files
        self.fix_all_xhtml_files(oebps_dir)

        # Remove CSS files (prevents markitdown from converting them to markdown)
        self.remove_css_files(oebps_dir)

        # Create outputs
        self.create_audit_report(audit_report)
        self.create_fixed_epub(output_epub)

        # Optionally convert to clean markdown
        if output_md is not None:
            self.convert_to_markdown(output_epub, output_md)

        print("\n" + "=" * 70)
        print("✅ CONVERSION COMPLETE")
        print("=" * 70)
        print(f"\n📚 Fixed EPUB:   {output_epub}")
        print(f"📊 Audit Report: {audit_report}")
        if output_md is not None:
            print(f"📄 Markdown:     {output_md}")
        else:
            print("\n💡 Tip: pass a 4th argument to also generate clean markdown.")


def main():
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python fix_epub_headings.py <input.epub> [output.epub] [audit_report.md] [output.md]"
        )
        sys.exit(1)

    input_epub = Path(sys.argv[1])
    output_epub = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else input_epub.parent / f"{input_epub.stem}_fixed.epub"
    )
    audit_report = (
        Path(sys.argv[3])
        if len(sys.argv) > 3
        else input_epub.parent / f"{input_epub.stem}_audit.md"
    )
    output_md = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    if not input_epub.exists():
        print(f"Error: File not found: {input_epub}")
        sys.exit(1)

    fixer = EPUBHeadingFixer(str(input_epub))
    fixer.run(output_epub, audit_report, output_md)


if __name__ == "__main__":
    main()

"""Choose how a ``convert`` source is read: by an extractor's plan, or as a local file."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from md_studio.core.document import Document
from md_studio.core.exceptions import ReadError
from md_studio.core.extensions import pipeline
from md_studio.extractors import ExtractionPlan, Extractor, resolve_extractor
from md_studio.extractors.arxiv import ArxivExtractor
from md_studio.readers.epub import read_epub
from md_studio.readers.urls import display_url

_READERS = MappingProxyType({".epub": read_epub})


@dataclass(frozen=True, slots=True)
class Job:
    """One resolved ``convert`` source.

    ``origin`` stands in for the source when naming outputs, and ``extensions`` holds the
    plan's source fixes followed by the names given with ``--ext`` (``None`` when empty).
    """

    plan: ExtractionPlan | None
    origin: Path
    extensions: list[str] | None

    def document(self) -> Document:
        """Read the source through the plan's reader, or as a local file without a plan.

        Raises
        ------
        ReadError
            When the source cannot be read, or a local file has an unsupported type.
        """
        if self.plan is not None:
            return self.plan.reader(self.plan.source)
        reader = _READERS.get(self.origin.suffix.lower())
        if reader is None:
            kind, supported = self.origin.suffix, ", ".join(sorted(_READERS))
            raise ReadError(f"Unsupported source type {kind!r}; supported: {supported}")
        return reader(self.origin)


def build_extractors() -> tuple[Extractor, ...]:
    """Return the extractors consulted before the file-type readers, in priority order."""
    return (ArxivExtractor(),)


def _detect(source: str, arxiv_id: str | None) -> ExtractionPlan | None:
    """Return the first matching extractor's plan, honouring ``--arxiv-id`` and local files."""
    extractors = build_extractors()
    if arxiv_id is None:
        return None if Path(source).exists() else resolve_extractor(source, extractors)
    plan = resolve_extractor(arxiv_id, extractors)
    if plan is None:
        raise ReadError(f"--arxiv-id {display_url(arxiv_id)!r} is not an arXiv id")
    return plan


def _origin(source: str, plan: ExtractionPlan | None) -> Path:
    if plan is None:
        return Path(source)
    paper = (plan.metadata_overrides or {}).get("arxiv_id", "paper")
    return Path(f"arxiv-{paper.replace('/', '_')}.md")


def prepare(source: str, arxiv_id: str | None, named: list[str] | None) -> Job:
    """Resolve *source* into a :class:`Job` without reading or fetching anything.

    Parameters
    ----------
    source
        Path, URL or id given on the command line.
    arxiv_id
        The ``--arxiv-id`` value; when set it replaces detection and *source* is ignored.
    named
        Extension names from ``--ext``.

    Raises
    ------
    ReadError
        When *arxiv_id* is not an arXiv id.
    UnknownExtensionError
        When the plan names a source fix that is not registered; raised before any
        request is made.
    ExtensionLoadError
        When a named source fix is registered but fails to load.
    """
    plan = _detect(source, arxiv_id)
    fixes = [] if plan is None else list(plan.source_fixes)
    pipeline.resolve(fixes)
    names = [*fixes, *(named or [])]
    return Job(plan, _origin(source, plan), names or None)

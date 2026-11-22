"""Site-specific extractors that choose how a source is read and fixed up."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from md_studio.readers import Reader


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    """How to read one source: the reader, the source to feed it, and adjustments."""

    reader: Reader
    source: str
    source_fixes: tuple[str, ...] = ()
    metadata_overrides: Mapping[str, str] | None = None


class Extractor(Protocol):
    """Claims sources it knows how to read and plans their extraction."""

    def matches(self, source: str) -> bool:
        """Return whether this extractor handles *source*."""

    def resolve(self, source: str) -> ExtractionPlan:
        """Return the extraction plan for a matching *source*."""


def resolve_extractor(source: str, extractors: Iterable[Extractor]) -> ExtractionPlan | None:
    """Return the plan from the first extractor matching *source*, or ``None``.

    Parameters
    ----------
    source
        Path or URL being converted.
    extractors
        Candidates in priority order.
    """
    for extractor in extractors:
        if extractor.matches(source):
            return extractor.resolve(source)
    return None

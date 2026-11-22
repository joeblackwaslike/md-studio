"""The arXiv extractor: reads a paper's LaTeXML HTML through a polite client."""

from md_studio.core.exceptions import ReadError
from md_studio.extractors import ExtractionPlan
from md_studio.extractors.arxiv_client import ArxivClient
from md_studio.extractors.arxiv_id import parse_arxiv_id
from md_studio.readers.urls import display_url

SOURCE_FIX = "arxiv-latexml"


class ArxivExtractor:
    """Claims arXiv ids and URLs and plans a read of the paper's HTML version."""

    def __init__(self, client: ArxivClient | None = None) -> None:
        """Use *client* for fetching, or a default client with arXiv's 15 second spacing."""
        self._client = client or ArxivClient()

    def matches(self, source: str) -> bool:
        """Return whether *source* is an arXiv id or an arxiv.org abs, pdf or html URL."""
        return parse_arxiv_id(source) is not None

    def resolve(self, source: str) -> ExtractionPlan:
        """Plan reading ``https://arxiv.org/html/<id>`` without fetching anything.

        Raises
        ------
        ReadError
            When *source* is not an arXiv id or URL.
        """
        paper = parse_arxiv_id(source)
        if paper is None:
            raise ReadError(f"{display_url(source)} is not an arXiv id or URL")
        return ExtractionPlan(
            reader=self._client.read,
            source=f"https://arxiv.org/html/{paper}",
            source_fixes=(SOURCE_FIX,),
            metadata_overrides={"arxiv_id": paper},
        )

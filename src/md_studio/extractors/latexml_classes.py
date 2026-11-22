"""Class names of a node, tolerating the comments and processing instructions lxml keeps."""

from md_studio.readers.html import HtmlElement

_CLASS = "class"


def classes_of(node: HtmlElement) -> list[str]:
    """Return the class names of *node*, or an empty list for a comment or instruction."""
    if not isinstance(node.tag, str):
        return []
    return str(node.get(_CLASS, "")).split()

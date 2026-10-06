import re
from collections.abc import Iterable


def verify_citations(
    response_text: str,
    valid_citation_ids: Iterable[str] | None,
) -> tuple[bool, list[str]]:
    """Inspects response_text for citations matching [Sn] pattern.

    Performs a deterministic existence check: checks whether each cited [Sn]
    id in the text actually exists among the retrieved chunks for that race.

    Returns:
        (citations_valid, invalid_citations)
        - citations_valid: True if there are zero invalid citations.
        - invalid_citations: Sorted list of cited IDs that do NOT exist in valid_citation_ids.
    """
    if not response_text:
        return True, []

    valid_set = set(valid_citation_ids) if valid_citation_ids is not None else set()

    # Match bracketed source IDs such as [S1], [S2], [S10]
    pattern = r"\[(S\d+)\]"
    found = re.findall(pattern, response_text)

    if not found:
        return True, []

    unique_found = set(found)
    invalid = sorted(unique_found - valid_set)

    return len(invalid) == 0, invalid

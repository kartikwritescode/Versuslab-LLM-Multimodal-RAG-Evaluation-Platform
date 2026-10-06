import json
import re
from typing import Any


def exact_match(
    answer: str,
    expected: str,
    strip_whitespace: bool = True,
    ignore_case: bool = False,
) -> float:
    """Evaluates whether answer matches expected string exactly.

    Returns 1.0 for a match, 0.0 otherwise.
    """
    ans = answer.strip() if strip_whitespace else answer
    exp = expected.strip() if strip_whitespace else expected

    if ignore_case:
        ans = ans.lower()
        exp = exp.lower()

    return 1.0 if ans == exp else 0.0


def regex_match(answer: str, pattern: str) -> float:
    """Evaluates whether answer matches a regex pattern.

    Returns 1.0 if a match is found, 0.0 otherwise.
    """
    try:
        match = re.search(pattern, answer)
        return 1.0 if match is not None else 0.0
    except re.error:
        return 0.0


def _validate_schema(data: Any, schema: dict[str, Any]) -> bool:
    """Lightweight JSON Schema validator supporting 'type', 'required', and 'properties'."""
    expected_type = schema.get("type")
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    if expected_type and expected_type in type_map:
        # Note: In Python, bool is a subclass of int, so handle boolean carefully
        if expected_type in ("number", "integer") and isinstance(data, bool):
            return False
        if not isinstance(data, type_map[expected_type]):
            return False

    if isinstance(data, dict):
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                return False

        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in data and not _validate_schema(data[prop_name], prop_schema):
                return False

    elif isinstance(data, list) and "items" in schema:
        item_schema = schema["items"]
        for item in data:
            if not _validate_schema(item, item_schema):
                return False

    return True


def json_schema_validity(answer: str, schema: dict[str, Any] | None = None) -> float:
    """Evaluates whether answer parses as valid JSON and conforms to an optional JSON schema.

    Returns 1.0 if valid, 0.0 otherwise.
    """
    if not answer or not answer.strip():
        return 0.0

    # Strip potential markdown code fences e.g. ```json ... ```
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1 and cleaned.endswith("```"):
            cleaned = cleaned[first_newline + 1 : -3].strip()

    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return 0.0

    if schema is not None:
        return 1.0 if _validate_schema(parsed, schema) else 0.0

    return 1.0

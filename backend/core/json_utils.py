"""Robust JSON extraction from LLM responses.

Provides three strategies for both JSON objects and arrays:
1. Markdown code fence (```json ... ```)
2. Brace/bracket-counted extraction with truncation repair
3. Regex fallback — pick the largest valid match
"""

import json
import logging
import re

logger = logging.getLogger(__name__)


def repair_json(text: str) -> str | None:
    """Remove trailing commas before ] or } — the most common LLM mistake."""
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    if repaired != text:
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            pass
    return None


def repair_truncated(text: str, closers: list[str]) -> str | None:
    """Repair truncated JSON by appending missing closing braces/brackets."""
    suffix = "".join(closers)
    repaired = text + suffix
    repaired = re.sub(r",\s*$", "", repaired)
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass
    return None


def _extract_balanced(content: str, open_char: str, close_char: str) -> str | None:
    """Extract the outermost balanced delimiter-pair via counting.

    Handles nested braces/brackets inside strings and tracks ``{``/``}``
    and ``[``/``]`` simultaneously so embedded objects/arrays don't confuse
    the delimiter count.  Returns the raw JSON substring or None.
    """
    pos = 0
    while True:
        start = content.find(open_char, pos)
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        closer_stack: list[str] = []
        for i in range(start, len(content)):
            ch = content[i]
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_char:
                depth += 1
                closer_stack.append(close_char)
            elif ch == close_char:
                depth -= 1
                if closer_stack and closer_stack[-1] == close_char:
                    closer_stack.pop()
            elif ch == "{":
                closer_stack.append("}")
            elif ch == "}":
                if closer_stack and closer_stack[-1] == "}":
                    closer_stack.pop()
            elif ch == "[":
                closer_stack.append("]")
            elif ch == "]":
                if closer_stack and closer_stack[-1] == "]":
                    closer_stack.pop()

            if depth == 0:
                candidate = content[start:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    repaired = repair_json(candidate)
                    if repaired is not None:
                        return repaired
                    if len(candidate) > 500:
                        return None
                break
        else:
            # Reached end of content at depth > 0 — likely truncated
            if closer_stack:
                repaired = repair_truncated(content[start:], closer_stack)
                if repaired is not None:
                    return repaired
        pos = start + 1


def extract_json_block(content: str) -> dict | None:
    """Extract the outermost JSON object (``{...}``) from LLM output.

    Strategies (tried in order):
    1. Markdown code fence
    2. Brace-counted outermost ``{``…``}`` (with repair for trailing commas & truncation)
    3. All regex-matched JSON objects, pick the largest
    """
    if not content:
        return None

    # Strategy 1: code fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 2: balanced braces
    result = _extract_balanced(content, "{", "}")
    if result is not None:
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass

    # Strategy 3: regex all objects, pick largest
    candidates = re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
    best = None
    for m in candidates:
        try:
            obj = json.loads(m.group())
            if best is None or len(json.dumps(obj)) > len(json.dumps(best)):
                best = obj
        except json.JSONDecodeError:
            pass
    return best


def extract_json_array(content: str) -> list | None:
    """Extract the outermost JSON array (``[...]``) from LLM output.

    Strategies (tried in order):
    1. Markdown code fence
    2. Bracket-counted outermost ``[``…``]`` (with repair for trailing commas & truncation)
    3. All regex-matched JSON arrays, pick the largest
    """
    if not content:
        return None

    # Strategy 1: code fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 2: balanced brackets
    result = _extract_balanced(content, "[", "]")
    if result is not None:
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass

    # Strategy 3: regex all arrays, pick largest
    candidates = re.finditer(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]", content, re.DOTALL)
    best = None
    for m in candidates:
        try:
            obj = json.loads(m.group())
            if best is None or len(json.dumps(obj)) > len(json.dumps(best)):
                best = obj
        except json.JSONDecodeError:
            pass
    return best


def parse_llm_json(content: str, fallback_key: str | None = None) -> dict:
    """Extract a JSON object from LLM output with logging and structured fallback.

    Uses the multi-strategy ``extract_json_block`` and returns a dict on failure
    instead of ``None``, so callers never receive a raw None.

    Args:
        content: Raw LLM response text.
        fallback_key: If set and extraction fails, returns
            ``{"status": "complete", fallback_key: {"raw": content}}``.
            If None, returns ``{"status": "error", "raw": content[:500]}``.

    Returns:
        Parsed JSON dict, or a structured fallback dict (never None).
    """
    if not content:
        logger.warning("parse_llm_json received empty content")
        return {"status": "error", "raw": ""}

    result = extract_json_block(content)
    if result is not None:
        return result

    logger.warning(
        "Failed to extract JSON from LLM response (len=%d, fallback_key=%s)",
        len(content), fallback_key,
    )
    if fallback_key:
        return {"status": "complete", fallback_key: {"raw": content}}
    return {"status": "error", "raw": content[:500]}


def parse_llm_json_array(content: str) -> list:
    """Extract a JSON array from LLM output with logging and safe fallback.

    Uses the multi-strategy ``extract_json_array`` and returns an empty list
    on failure instead of ``None``.

    Returns:
        Parsed JSON list, or ``[]`` on failure (never None).
    """
    if not content:
        logger.warning("parse_llm_json_array received empty content")
        return []

    result = extract_json_array(content)
    if result is not None:
        return result

    logger.warning(
        "Failed to extract JSON array from LLM response (len=%d)",
        len(content),
    )
    return []

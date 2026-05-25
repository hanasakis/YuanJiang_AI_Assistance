"""Clean DeepSeek-R1 raw output.

DeepSeek-R1 wraps its chain-of-thought in  Think ... Think tags.
For production use we need to:
1. Strip the thinking block to get the final answer.
2. Extract JSON blocks from the model output (robust to markdown fences).
"""

from __future__ import annotations

import json
import re

# DeepSeek-R1 wraps chain-of-thought in special markers.
# Variant A: <think>...</think>  (ASCII angle brackets)
# Variant B: \U0002DFE8 think \U0002DFE9 ... \U0002DFE8 /think \U0002DFE9
#   (Unicode THINK START/END characters from Supplementary Private Use Area-A)
_THINK_START = r"(?:<\s*think\s*>|\U0002DFE8\s*think\s*\U0002DFE9)"
_THINK_END = r"(?:<\s*/\s*think\s*>|\U0002DFE8\s*/\s*think\s*\U0002DFE9)"

_THINK_PATTERN = re.compile(
    rf"{_THINK_START}.*?{_THINK_END}",
    re.DOTALL | re.IGNORECASE,
)


def strip_think(text: str) -> str:
    """Remove DeepSeek-R1  Think... Think  blocks from the output.

    Args:
        text: Raw model output, possibly containing thinking blocks.

    Returns:
        Text with all  Think... Think  blocks removed, whitespace trimmed.

    Examples:
        >>> strip_think(" Think reasoning... Think The answer is 42.")
        'The answer is 42.'
        >>> strip_think("Plain answer without thinking.")
        'Plain answer without thinking.'
        >>> strip_think(" Think nested  Think The answer.")
        'The answer.'
    """
    cleaned = _THINK_PATTERN.sub("", text)
    return cleaned.strip()


def extract_json_block(text: str) -> dict | list | None:
    """Extract a JSON object or array from model output.

    Handles three common formats:
    1. Fenced code block: ```json { ... } ```
    2. Bare JSON object: {"key": "value"}
    3. Bare JSON array: [{"key": "value"}]

    Args:
        text: Model output that may contain a JSON block.

    Returns:
        Parsed dict or list, or None if no valid JSON found.

    Examples:
        >>> extract_json_block('```json\\n{"a": 1}\\n```')
        {'a': 1}
        >>> extract_json_block('The result is {"score": 0.9}.')
        {'score': 0.9}
        >>> extract_json_block('No JSON here.')
        None
    """
    # Priority 1: fenced code block ```json ... ```
    fence_match = re.search(
        r"```(?:json)?\s*([\s\S]*?)```",
        text,
    )
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass  # fall through to bare JSON attempt

    # Priority 2: bare JSON object or array anywhere in the text
    # Match the outermost { ... } or [ ... ]
    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    return None

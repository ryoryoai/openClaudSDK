"""Message formatter: split long text for Discord's 2000-char limit."""

from __future__ import annotations

DISCORD_MAX_LEN = 2000
# Leave room for code-block wrappers added during splitting
_SAFE_LIMIT = DISCORD_MAX_LEN - 20


def split_message(text: str, limit: int = _SAFE_LIMIT) -> list[str]:
    """Split *text* into chunks that fit within *limit* characters.

    The algorithm:
    1. Prefer splitting at paragraph boundaries (blank lines).
    2. Fall back to single newlines.
    3. Fall back to hard-cutting at *limit*.

    Open code fences (```) are detected: if a chunk ends inside a code
    block the fence is closed at the end and re-opened at the start of the
    next chunk (preserving the language tag).
    """
    if len(text) <= limit:
        return [text]

    raw_chunks = _split_on_boundaries(text, limit)
    return _fix_code_fences(raw_chunks)


def _split_on_boundaries(text: str, limit: int) -> list[str]:
    """Split text by paragraph or line boundaries."""
    chunks: list[str] = []
    remaining = text

    while len(remaining) > limit:
        # Try splitting at a blank-line boundary
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            # Try a single newline
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            # Hard cut
            cut = limit

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")

    if remaining:
        chunks.append(remaining)

    return chunks


def _fix_code_fences(chunks: list[str]) -> list[str]:
    """Ensure code blocks (```) are properly closed/reopened across chunks."""
    result: list[str] = []
    open_lang: str | None = None  # language tag of the currently open fence

    for chunk in chunks:
        if open_lang is not None:
            # Re-open the code block from the previous chunk
            chunk = f"```{open_lang}\n{chunk}"
            open_lang = None

        # Count backtick fences to determine if we end inside a code block
        fence_count = 0
        last_lang = ""
        for line in chunk.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                fence_count += 1
                # Capture language tag when opening
                tag = stripped[3:].strip()
                if tag:
                    last_lang = tag

        if fence_count % 2 == 1:
            # Odd number of fences → we're inside an unclosed block
            chunk += "\n```"
            open_lang = last_lang

        result.append(chunk)

    return result

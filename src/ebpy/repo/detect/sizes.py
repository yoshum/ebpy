"""The file-size backlog, known before any limit is ever switched on.

Reporting it during diagnose is what makes a size tier an informed choice
rather than a number copied from a blog post.
"""

from __future__ import annotations

from ebpy.models import SizeDistribution, SourceFile

DEFAULT_FILE_LINE_LIMIT = 600

_LARGEST_SAMPLE = 10


def summarize_sizes(
    source_files: tuple[SourceFile, ...], limit: int = DEFAULT_FILE_LINE_LIMIT
) -> SizeDistribution:
    """Summarise the source file-size distribution and the largest files over the limit."""
    over = [file for file in source_files if file.lines > limit]
    return SizeDistribution(
        total=len(source_files),
        over_file_limit=len(over),
        largest=tuple(sorted(over, key=lambda file: -file.lines)[:_LARGEST_SAMPLE]),
    )

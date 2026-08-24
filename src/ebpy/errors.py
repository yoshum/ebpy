class CommandError(RuntimeError):
    """The command could not safely perform the requested operation."""


class ToolError(RuntimeError):
    """A repository tool could not produce a measurement.

    It carries two readings of one failure because its readers differ. `summary` is the
    single line a sentence or a table row can hold; `detail` is everything the tool said,
    which is what a whole error message or a JSON field should carry. Choosing the summary
    is the runner's job — only it knows which of its tool's lines a human acts on, and a
    generic "first line" picks the usage banner over the error it precedes.
    """

    def __init__(self, summary: str, detail: str | None = None) -> None:
        """Store the one-line ``summary`` and the full ``detail``, defaulting detail to summary."""
        super().__init__(detail or summary)
        self.summary = summary
        self.detail = detail or summary

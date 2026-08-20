"""Pure verdicts over facts: values in, a decision out, no disk access.

``diagnose`` surveys the repository's gaps, ``analysis_report`` shapes the
backlog as a rule x area matrix, ``drain_order`` computes what to fix first,
``bootstrap_plan`` says what bootstrap would do, and ``freshness`` judges
whether a diagnosis can still be trusted. Everything here is testable without
a filesystem.
"""

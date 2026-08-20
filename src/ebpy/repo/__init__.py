"""Everything read from the target repository's working tree.

``facts`` gathers the tracked files, ``git`` answers the version-control
questions the ledger needs, ``fan_in`` counts importers, and ``detect``
recognises the toolchain, package manager, CI and file sizes. These are the
disk-reading seam; decisions elsewhere take their values and stay pure.
"""

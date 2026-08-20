"""The ``.ebpy/`` ratchet files and the arithmetic that reads them.

``baseline`` owns ``baseline.json`` (the ceiling), ``state`` owns ``state.json``
(the ledger), and ``ceiling_artifacts`` classifies the pair. Nothing outside this
package writes either file.
"""

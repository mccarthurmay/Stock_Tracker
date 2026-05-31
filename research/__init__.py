"""Options day-trading research system (see ROADMAP.md).

M1 — Data spine: rate-limited Alpaca pulls of aligned underlying + option
bars into DuckDB, a point-in-time contract universe, and point-in-time
integrity checks. Phase A only (indicative free feed) — see ROADMAP §2d.
"""

__version__ = "0.1.0"

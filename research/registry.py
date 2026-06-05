"""Indicator registry (ROADMAP §3).

Every indicator is a pure function ``f(df, **params) -> pd.Series`` that, at
each timestamp t, uses only data at or before t (no lookahead). Each is
registered with the columns it needs, its default params + sweep ranges, its
layer, and its **data phase**:

  phase 'A'  — believable on Alpaca free/indicative data (price/volume/Greek
               derived). Greeks are self-computed and approximate, but usable.
  phase 'B'  — IV-derived. Computable in Phase A for plumbing, but NOT to be
               believed until re-validated on vendor data (ROADMAP §2d, §3).

A hypothesis that uses any phase-'B' indicator is itself phase 'B'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

PHASES = ("A", "B")
LAYERS = ("trend", "momentum", "volatility", "volume", "structure",
          "greek", "iv", "pricing", "context")


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    fn: Callable[..., pd.Series]
    layer: str
    inputs: tuple[str, ...]            # required df columns
    params: dict                       # default params
    param_ranges: dict = field(default_factory=dict)  # {param: [values]} for sweeps
    phase: str = "A"
    description: str = ""

    def __post_init__(self):
        if self.layer not in LAYERS:
            raise ValueError(f"{self.name}: unknown layer {self.layer!r}")
        if self.phase not in PHASES:
            raise ValueError(f"{self.name}: phase must be one of {PHASES}")

    def compute(self, df: pd.DataFrame, **overrides) -> pd.Series:
        missing = [c for c in self.inputs if c not in df.columns]
        if missing:
            raise KeyError(f"{self.name}: missing input columns {missing}")
        p = {**self.params, **overrides}
        out = self.fn(df, **p)
        return out.rename(self.name) if isinstance(out, pd.Series) else out


REGISTRY: dict[str, IndicatorSpec] = {}


def register(*, name: str, layer: str, inputs: list[str], params: dict | None = None,
             param_ranges: dict | None = None, phase: str = "A", description: str = ""):
    """Decorator registering a pure indicator function into REGISTRY."""
    def deco(fn):
        if name in REGISTRY:
            raise ValueError(f"duplicate indicator name {name!r}")
        REGISTRY[name] = IndicatorSpec(
            name=name, fn=fn, layer=layer, inputs=tuple(inputs),
            params=dict(params or {}), param_ranges=dict(param_ranges or {}),
            phase=phase, description=description,
        )
        return fn
    return deco


def get(name: str) -> IndicatorSpec:
    if name not in REGISTRY:
        raise KeyError(f"unknown indicator {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name]


def all_specs() -> list[IndicatorSpec]:
    return [REGISTRY[k] for k in sorted(REGISTRY)]


def by_layer(layer: str) -> list[IndicatorSpec]:
    return [s for s in all_specs() if s.layer == layer]

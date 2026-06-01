"""Hypothesis registry — the anti-data-mining core (ROADMAP §4).

Loads and validates ``hypotheses.yaml``. Every hypothesis MUST declare a
written economic rationale, an expected direction of effect, and the
indicators it uses (with optional parameter sweep ranges). Validation is
strict and fail-closed: a hypothesis with no rationale, an unknown indicator,
or an undirected effect is rejected, not silently accepted.

Two derived properties matter downstream:
  * ``phase``  — 'B' if the hypothesis uses ANY phase-'B' (IV-derived)
    indicator, else 'A'. A phase-'B' hypothesis is not to be believed on
    Alpaca data (ROADMAP §2d, §3).
  * ``configs`` — the cartesian expansion of every indicator's swept params
    into concrete configurations. ``config_hash`` of each is what the §6.5
    multiple-testing correction counts (via storage.record_config_run).

There is NO untracked exploration: if it isn't registered here, it isn't run.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import registry
from .settings import RESEARCH_DIR

HYPOTHESES_PATH = RESEARCH_DIR / "hypotheses.yaml"
_DIRECTIONS = ("long", "short", "long_or_short")
_REQUIRED = ("id", "rationale", "expected_direction", "indicators")


@dataclass(frozen=True)
class IndicatorUse:
    name: str
    params: dict = field(default_factory=dict)
    sweep: dict = field(default_factory=dict)  # {param: [values]}


@dataclass(frozen=True)
class Hypothesis:
    id: str
    rationale: str
    expected_direction: str
    indicators: tuple[IndicatorUse, ...]
    notes: str = ""

    @property
    def phase(self) -> str:
        return "B" if any(registry.get(u.name).phase == "B"
                          for u in self.indicators) else "A"

    def configs(self) -> list[dict]:
        """Expand swept params into concrete per-indicator configurations."""
        per_indicator = []
        for u in self.indicators:
            spec = registry.get(u.name)
            base = {**spec.params, **u.params}
            keys = list(u.sweep.keys())
            if not keys:
                per_indicator.append([(u.name, base)])
                continue
            combos = []
            for values in itertools.product(*(u.sweep[k] for k in keys)):
                combos.append((u.name, {**base, **dict(zip(keys, values))}))
            per_indicator.append(combos)

        out = []
        for combo in itertools.product(*per_indicator):
            out.append({name: params for name, params in combo})
        return out


def config_hash(hyp_id: str, config: dict) -> str:
    """Stable hash of (hypothesis id + indicator params) for the run ledger."""
    payload = json.dumps({"id": hyp_id, "config": config}, sort_keys=True,
                         default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _validate_one(raw: dict, idx: int) -> Hypothesis:
    where = f"hypothesis #{idx}" + (f" ({raw.get('id')})" if raw.get("id") else "")
    for key in _REQUIRED:
        if not raw.get(key):
            raise ValueError(f"{where}: missing required field {key!r}")
    if len(str(raw["rationale"]).strip()) < 15:
        raise ValueError(f"{where}: rationale too thin — give a real economic story")
    if raw["expected_direction"] not in _DIRECTIONS:
        raise ValueError(f"{where}: expected_direction must be one of {_DIRECTIONS}")

    uses = []
    for ind in raw["indicators"]:
        if isinstance(ind, str):
            ind = {"name": ind}
        name = ind.get("name")
        if not name:
            raise ValueError(f"{where}: an indicator entry has no name")
        registry.get(name)  # raises KeyError if unknown
        uses.append(IndicatorUse(name=name, params=dict(ind.get("params", {})),
                                  sweep=dict(ind.get("sweep", {}))))
    return Hypothesis(
        id=str(raw["id"]), rationale=str(raw["rationale"]).strip(),
        expected_direction=raw["expected_direction"],
        indicators=tuple(uses), notes=str(raw.get("notes", "")),
    )


def load(path: Path | str = HYPOTHESES_PATH) -> list[Hypothesis]:
    """Load + strictly validate all hypotheses. Raises on the first problem."""
    path = Path(path)
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text()) or {}
    raws = doc.get("hypotheses", [])
    seen = set()
    out = []
    for i, raw in enumerate(raws):
        h = _validate_one(raw, i)
        if h.id in seen:
            raise ValueError(f"duplicate hypothesis id {h.id!r}")
        seen.add(h.id)
        out.append(h)
    return out


def summarize(hyps: list[Hypothesis]) -> dict:
    total_configs = sum(len(h.configs()) for h in hyps)
    return {
        "hypotheses": len(hyps),
        "phase_A": sum(1 for h in hyps if h.phase == "A"),
        "phase_B": sum(1 for h in hyps if h.phase == "B"),
        "total_configs": total_configs,
    }

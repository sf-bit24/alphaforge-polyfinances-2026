"""Grille de mélanges (poids en % entiers, multiples de 5). Bibliothèque standard seulement.

Une grille est décrite par bloc : ``{min, max, step}`` en %, ou ``{values: [...]}``. On garde les
combinaisons dont la somme vaut 100 %, puis on ajoute les mélanges « ancres » (listes explicites), sans doublon.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence

from .schema import BLOCKS, mix_id


def _values(spec: Mapping[str, object]) -> list[int]:
    """``{"min": 0, "max": 60, "step": 10}`` ou ``{"values": [0, 5, 10]}`` (en %, multiples de 5)."""
    if "values" in spec:
        values = [int(v) for v in spec["values"]]  # type: ignore[union-attr]
    else:
        lo, hi, step = int(spec["min"]), int(spec["max"]), int(spec["step"])  # type: ignore[call-overload]
        if step <= 0:
            raise ValueError("pas nul ou négatif")
        values = list(range(lo, hi + 1, step))
    if any(v % 5 or v < 0 or v > 100 for v in values):
        raise ValueError(f"valeurs hors grille de 5 % : {values}")
    return values


def enumerate_mixes(
    blocks: Sequence[str],
    ranges: Mapping[str, object],
    anchors: Sequence[Mapping[str, float]] = (),
    max_mixes: int = 5000,
) -> list[str]:
    """Liste triée (ordre stable) des ``mix_id`` de la grille pour les blocs disponibles ``blocks``.

    Un bloc absent de ``ranges`` vaut 0. Les ancres qui utilisent un bloc indisponible sont ignorées.
    """
    for block in ranges:
        if block not in BLOCKS:
            raise ValueError(f"bloc inconnu dans la grille : {block}")
    active = [b for b in BLOCKS if b in blocks and b in ranges]
    value_lists = [_values(ranges[b]) for b in active]  # type: ignore[arg-type]
    ids: list[str] = []
    seen: set[str] = set()
    for combo in itertools.product(*value_lists):
        if sum(combo) != 100:
            continue
        mid = mix_id({b: v / 100.0 for b, v in zip(active, combo, strict=True)})
        if mid not in seen:
            seen.add(mid)
            ids.append(mid)
    for anchor in anchors:
        if any(float(w) > 0 and b not in blocks for b, w in anchor.items()):
            continue
        mid = mix_id({b: float(w) / 100.0 for b, w in anchor.items()})
        if mid not in seen:
            seen.add(mid)
            ids.append(mid)
    if len(ids) > max_mixes:
        raise ValueError(f"grille trop grande : {len(ids)} mélanges > max_mixes={max_mixes}")
    return ids

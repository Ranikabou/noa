"""Hard constraints — the via negativa half of taste.

You can't specify what makes an image good, but you can accumulate a long list of
what disqualifies it, and that list transfers to a machine in a way positive
description never does. Taste read from outside is mostly *consistency plus
refusal*: the same choices made repeatedly, including the expensive ones.

So this module is not a soft scorer. Every check returns a list of *disqualifiers*
— named, human-readable reasons a candidate is out. A candidate with any
disqualifier is rejected regardless of how well it scores on the manifold; a
brilliant render that breaks the palette or trips the refused list is still out.
That asymmetry is the point: the constraints are cheap to state, densely sampled
near the edge, and never overridden by score.

Three grammars are encoded here — a fixed palette, an allowed crop grammar, and a
refused-motif list — but the shape generalises: add a check, append its
disqualifier string.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# Maximum Euclidean distance between two colours in RGB space (black↔white),
# used to normalise colour distance into [0, 1].
_MAX_RGB_DISTANCE = math.sqrt(3 * 255 ** 2)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse ``#rrggbb`` / ``rrggbb`` / ``#rgb`` into an ``(r, g, b)`` triple."""
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"invalid hex colour: {value!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def color_distance(a: str, b: str) -> float:
    """Normalised RGB distance in ``[0, 1]`` (0 identical, 1 black↔white)."""
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    d = math.sqrt((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2)
    return d / _MAX_RGB_DISTANCE


@dataclass(frozen=True)
class Palette:
    """A fixed, refused-to-drift palette.

    A candidate colour is admissible only if it lands within ``tolerance`` of some
    swatch. ``max_off_palette_fraction`` allows a small share of accent colours to
    fall outside (real interiors carry a spark of contrast) while still rejecting
    a candidate whose colour story has genuinely wandered off.
    """

    swatches: Sequence[str]
    tolerance: float = 0.12
    max_off_palette_fraction: float = 0.15

    def nearest_distance(self, color: str) -> float:
        """Distance from ``color`` to the closest swatch (1.0 if no swatches)."""
        if not self.swatches:
            return 1.0
        return min(color_distance(color, s) for s in self.swatches)

    def off_palette(self, colors: Sequence[str]) -> list[str]:
        """Return the subset of ``colors`` that no swatch admits."""
        return [c for c in colors if self.nearest_distance(c) > self.tolerance]


@dataclass(frozen=True)
class HardConstraints:
    """The refused list, palette, and crop grammar — all disqualifying.

    Any check that fires adds a disqualifier string; a candidate with a non-empty
    disqualifier list is rejected outright by the taste function, no matter its
    manifold score.
    """

    #: Motifs/tags that disqualify on sight (matched case-insensitively).
    refused_motifs: frozenset = field(default_factory=frozenset)
    #: The fixed palette, or ``None`` to skip colour checking.
    palette: Palette | None = None
    #: Allowed aspect ratios (width/height); empty means any crop is allowed.
    allowed_aspect_ratios: Sequence[float] = ()
    #: Fractional tolerance when matching an aspect ratio (0.05 = ±5%).
    aspect_ratio_tolerance: float = 0.05

    @staticmethod
    def _normalise_motif(m: str) -> str:
        return m.strip().lower()

    def refused_hits(self, tags: Iterable[str]) -> list[str]:
        """Tags that appear on the refused list."""
        if not self.refused_motifs:
            return []
        refused = {self._normalise_motif(m) for m in self.refused_motifs}
        seen: list[str] = []
        for tag in tags:
            norm = self._normalise_motif(tag)
            if norm in refused and norm not in seen:
                seen.append(norm)
        return seen

    def _aspect_ok(self, ratio: float) -> bool:
        if not self.allowed_aspect_ratios:
            return True
        return any(
            abs(ratio - allowed) <= self.aspect_ratio_tolerance * allowed
            for allowed in self.allowed_aspect_ratios
        )

    def disqualifiers(
        self,
        tags: Iterable[str] = (),
        colors: Sequence[str] = (),
        aspect_ratio: float | None = None,
    ) -> list[str]:
        """Every reason this candidate is disqualified (empty list = admissible)."""
        reasons: list[str] = []

        for motif in self.refused_hits(tags):
            reasons.append(f"refused_motif:{motif}")

        if self.palette is not None and colors:
            off = self.palette.off_palette(colors)
            if off and (len(off) / len(colors)) > self.palette.max_off_palette_fraction:
                reasons.append("off_palette:" + ",".join(off))

        if aspect_ratio is not None and not self._aspect_ok(aspect_ratio):
            reasons.append(f"bad_crop:{aspect_ratio:.3f}")

        return reasons

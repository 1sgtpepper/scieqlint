"""Compatibility façade for MyST/Markdown math fact lowering."""

from __future__ import annotations

from . import myst_display_math as _display_math
from . import myst_inline_math as _inline_math
from . import myst_shared as _shared

math_occupied_ranges = _display_math.math_occupied_ranges
scan_display_math = _display_math.scan_display_math
scan_raw_latex_math = _display_math.scan_raw_latex_math
scan_inline_math = _inline_math.scan_inline_math
_overlaps_occupied = _inline_math.overlaps_occupied
_plain_text_math_candidate_spans = _inline_math.plain_text_math_candidate_spans
_merge_occupied = _shared.merge_occupied

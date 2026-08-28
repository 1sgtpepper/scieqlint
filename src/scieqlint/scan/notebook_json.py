"""Compatibility exports for the frontend-owned notebook JSON parser."""

from scieqlint.frontend.notebook_json import (
    json_array_ranges,
    json_decoder,
    json_object_members,
    json_string_character_ranges,
    parse_json_document,
)

__all__ = (
    "json_array_ranges",
    "json_decoder",
    "json_object_members",
    "json_string_character_ranges",
    "parse_json_document",
)

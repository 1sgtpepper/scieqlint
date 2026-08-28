"""Source limits for bounded scanner input."""

DEFAULT_MAX_FILE_BYTES = 1_048_576
DEFAULT_MAX_MATH_BLOCKS_PER_FILE = 2_000
# Exact notebook spans materialize one immutable segment per logical character.
DEFAULT_MAX_NOTEBOOK_SOURCE_CHARS = 100_000

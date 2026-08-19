"""Conservative inline-TeX macro declaration syntax scanning.

This module recognizes only declaration shapes whose boundaries can be recovered
without TeX expansion. It returns source-relative syntax records; FactHost owns
persistent facts and FrontendHost supplies document identity and source spans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

MacroDeclarationSyntaxKind = Literal[
    "newcommand",
    "renewcommand",
    "providecommand",
    "def",
]

_DECLARATION_COMMANDS = frozenset({"newcommand", "renewcommand", "providecommand", "def"})


@dataclass(frozen=True, slots=True)
class MacroDeclarationSyntax:
    start: int
    end: int
    name: str
    name_start: int
    name_end: int
    declaration_kind: MacroDeclarationSyntaxKind
    parameter_count: int
    replacement: str


@dataclass(frozen=True, slots=True)
class MacroUseSyntax:
    start: int
    end: int
    name: str


@dataclass(frozen=True, slots=True)
class InlineMacroSyntax:
    declarations: tuple[MacroDeclarationSyntax, ...]
    uses: tuple[MacroUseSyntax, ...]


@dataclass(frozen=True, slots=True)
class InlineMacroSource:
    document_id: str
    source_fact_id: str
    source_start: int
    body: str


@dataclass(frozen=True, slots=True)
class MacroDeclarationKey:
    source_fact_id: str
    start: int


@dataclass(frozen=True, slots=True)
class ScopedMacroDeclarationSyntax:
    source: InlineMacroSource
    declaration: MacroDeclarationSyntax
    declaration_order: int


@dataclass(frozen=True, slots=True)
class ScopedMacroUseSyntax:
    source: InlineMacroSource
    use: MacroUseSyntax
    active_declaration: MacroDeclarationKey | None


@dataclass(frozen=True, slots=True)
class ScopedInlineMacroSyntax:
    declarations: tuple[ScopedMacroDeclarationSyntax, ...]
    uses: tuple[ScopedMacroUseSyntax, ...]


def scan_scoped_inline_macros(
    sources: tuple[InlineMacroSource, ...],
) -> ScopedInlineMacroSyntax:
    """Resolve declaration order and active macro context per document."""

    parsed = tuple(
        (source, scan_inline_macro_syntax(source.body))
        for source in sorted(
            sources,
            key=lambda item: (
                item.document_id,
                item.source_start,
                item.source_fact_id,
            ),
        )
    )
    declarations: list[ScopedMacroDeclarationSyntax] = []
    declaration_order: dict[str, int] = {}
    declared_names: dict[str, set[str]] = {}
    for source, syntax in parsed:
        order = declaration_order.get(source.document_id, 0)
        names = declared_names.setdefault(source.document_id, set())
        for declaration in syntax.declarations:
            declarations.append(ScopedMacroDeclarationSyntax(source, declaration, order))
            order += 1
            names.add(declaration.name)
        declaration_order[source.document_id] = order

    active: dict[tuple[str, str], MacroDeclarationKey] = {}
    uses: list[ScopedMacroUseSyntax] = []
    for source, syntax in parsed:
        declaration_index = 0
        use_index = 0
        while declaration_index < len(syntax.declarations) or use_index < len(syntax.uses):
            declaration = (
                syntax.declarations[declaration_index]
                if declaration_index < len(syntax.declarations)
                else None
            )
            use = syntax.uses[use_index] if use_index < len(syntax.uses) else None
            if use is None or (declaration is not None and declaration.start < use.start):
                assert declaration is not None
                declaration_key = (source.document_id, declaration.name)
                if (
                    declaration.declaration_kind != "providecommand"
                    or declaration_key not in active
                ):
                    active[declaration_key] = MacroDeclarationKey(
                        source.source_fact_id, declaration.start
                    )
                declaration_index += 1
                continue
            if use.name in declared_names.get(source.document_id, set()):
                uses.append(
                    ScopedMacroUseSyntax(
                        source,
                        use,
                        active.get((source.document_id, use.name)),
                    )
                )
            use_index += 1
    return ScopedInlineMacroSyntax(tuple(declarations), tuple(uses))


def scan_inline_macro_syntax(body: str) -> InlineMacroSyntax:
    """Recognize finite declaration forms and control-word use sites in ``body``.

    Supported declarations are ``newcommand``, ``renewcommand``,
    ``providecommand``, and the undelimited ``def`` parameter form. Malformed or
    broader TeX declaration syntax is left uninterpreted.
    """

    declarations: list[MacroDeclarationSyntax] = []
    cursor = 0
    while cursor < len(body):
        if body[cursor] != "\\":
            cursor += 1
            continue
        control = _read_control(body, cursor)
        if control is None:
            cursor += 1
            continue
        command, command_end = control
        if command in _DECLARATION_COMMANDS:
            declaration = _parse_declaration(
                body,
                cursor,
                command_end,
                cast(MacroDeclarationSyntaxKind, command),
            )
            if declaration is not None:
                declarations.append(declaration)
                cursor = declaration.end
                continue
        cursor = command_end

    declaration_ranges = tuple((item.start, item.end) for item in declarations)
    uses = _scan_uses(body, declaration_ranges)
    return InlineMacroSyntax(tuple(declarations), uses)


def _parse_declaration(
    text: str,
    start: int,
    command_end: int,
    kind: MacroDeclarationSyntaxKind,
) -> MacroDeclarationSyntax | None:
    if kind == "def":
        return _parse_def_declaration(text, start, command_end)

    cursor = _skip_space(text, command_end)
    if cursor < len(text) and text[cursor] == "*":
        cursor = _skip_space(text, cursor + 1)
    target = _parse_macro_target(text, cursor)
    if target is None:
        return None
    name, name_start, name_end, cursor = target
    cursor = _skip_space(text, cursor)

    parameter_count = 0
    if cursor < len(text) and text[cursor] == "[":
        parameter_group = _read_group(text, cursor, "[", "]")
        if parameter_group is None:
            return None
        parameter_start, parameter_end, cursor = parameter_group
        parameter_text = text[parameter_start:parameter_end].strip()
        if len(parameter_text) != 1 or not parameter_text.isascii() or not parameter_text.isdigit():
            return None
        parameter_count = int(parameter_text)
        cursor = _skip_space(text, cursor)

    if cursor < len(text) and text[cursor] == "[":
        if parameter_count == 0:
            return None
        default_group = _read_group(text, cursor, "[", "]")
        if default_group is None:
            return None
        _, _, cursor = default_group
        cursor = _skip_space(text, cursor)

    replacement_group = _read_group(text, cursor, "{", "}")
    if replacement_group is None:
        return None
    replacement_start, replacement_end, end = replacement_group
    return MacroDeclarationSyntax(
        start=start,
        end=end,
        name=name,
        name_start=name_start,
        name_end=name_end,
        declaration_kind=kind,
        parameter_count=parameter_count,
        replacement=text[replacement_start:replacement_end],
    )


def _parse_def_declaration(
    text: str,
    start: int,
    command_end: int,
) -> MacroDeclarationSyntax | None:
    cursor = _skip_space(text, command_end)
    target = _parse_direct_macro_target(text, cursor)
    if target is None:
        return None
    name, name_start, name_end, cursor = target

    parameter_count = 0
    while True:
        cursor = _skip_space(text, cursor)
        if cursor >= len(text):
            return None
        if text[cursor] == "{":
            break
        if cursor + 1 >= len(text) or text[cursor] != "#":
            return None
        digit = text[cursor + 1]
        expected = str(parameter_count + 1)
        if digit != expected or digit == "0":
            return None
        parameter_count += 1
        cursor += 2

    replacement_group = _read_group(text, cursor, "{", "}")
    if replacement_group is None:
        return None
    replacement_start, replacement_end, end = replacement_group
    return MacroDeclarationSyntax(
        start=start,
        end=end,
        name=name,
        name_start=name_start,
        name_end=name_end,
        declaration_kind="def",
        parameter_count=parameter_count,
        replacement=text[replacement_start:replacement_end],
    )


def _parse_macro_target(text: str, cursor: int) -> tuple[str, int, int, int] | None:
    if cursor < len(text) and text[cursor] == "{":
        group = _read_group(text, cursor, "{", "}")
        if group is None:
            return None
        content_start, content_end, group_end = group
        name_start = _skip_space(text, content_start)
        name_limit = content_end
        while name_limit > content_start and text[name_limit - 1].isspace():
            name_limit -= 1
        if name_start >= name_limit:
            return None
        target = _parse_direct_macro_target(text, name_start)
        if target is None:
            return None
        name, parsed_start, parsed_end, parsed_cursor = target
        if parsed_cursor != name_limit:
            return None
        return name, parsed_start, parsed_end, group_end
    return _parse_direct_macro_target(text, cursor)


def _parse_direct_macro_target(
    text: str,
    cursor: int,
) -> tuple[str, int, int, int] | None:
    control = _read_control(text, cursor)
    if control is None:
        return None
    command, end = control
    if not command or not all(_is_control_letter(char) for char in command):
        return None
    return f"\\{command}", cursor, end, end


def _scan_uses(
    text: str,
    declaration_ranges: tuple[tuple[int, int], ...],
) -> tuple[MacroUseSyntax, ...]:
    uses: list[MacroUseSyntax] = []
    range_index = 0
    cursor = 0
    while cursor < len(text):
        while (
            range_index < len(declaration_ranges) and declaration_ranges[range_index][1] <= cursor
        ):
            range_index += 1
        if (
            range_index < len(declaration_ranges)
            and declaration_ranges[range_index][0] <= cursor < declaration_ranges[range_index][1]
        ):
            cursor = declaration_ranges[range_index][1]
            continue
        if text[cursor] != "\\":
            cursor += 1
            continue
        control = _read_control(text, cursor)
        if control is None:
            cursor += 1
            continue
        command, end = control
        if (
            command not in _DECLARATION_COMMANDS
            and command
            and all(_is_control_letter(char) for char in command)
        ):
            uses.append(MacroUseSyntax(cursor, end, f"\\{command}"))
        cursor = end
    return tuple(uses)


def _read_control(text: str, start: int) -> tuple[str, int] | None:
    if start < 0 or start >= len(text) or text[start] != "\\":
        return None
    if start + 1 >= len(text):
        return None
    cursor = start + 1
    if _is_control_letter(text[cursor]):
        cursor += 1
        while cursor < len(text) and _is_control_letter(text[cursor]):
            cursor += 1
        return text[start + 1 : cursor], cursor
    return text[cursor], cursor + 1


def _read_group(
    text: str,
    start: int,
    opener: str,
    closer: str,
) -> tuple[int, int, int] | None:
    if start >= len(text) or text[start] != opener:
        return None
    depth = 1
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == opener and not _is_escaped(text, cursor):
            depth += 1
        elif char == closer and not _is_escaped(text, cursor):
            depth -= 1
            if depth == 0:
                return start + 1, cursor, cursor + 1
        cursor += 1
    return None


def _is_escaped(text: str, index: int) -> bool:
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _skip_space(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _is_control_letter(char: str) -> bool:
    return char == "@" or "A" <= char <= "Z" or "a" <= char <= "z"

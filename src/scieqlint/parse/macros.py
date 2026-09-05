"""Conservative inline-TeX macro declaration syntax scanning.

This module recognizes only declaration shapes whose boundaries can be recovered
without TeX expansion. It returns source-relative syntax records; FactHost owns
persistent facts and FrontendHost supplies document identity and source spans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from scieqlint.markdown import without_tex_comments

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

    active_body = without_tex_comments(body)
    group_ends = _group_ends(active_body)
    declarations: list[MacroDeclarationSyntax] = []
    ignored_ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(active_body):
        if active_body[cursor] != "\\":
            cursor += 1
            continue
        control = _read_control(active_body, cursor)
        if control is None:
            cursor += 1
            continue
        command, command_end = control
        if command in _DECLARATION_COMMANDS:
            declaration = _parse_declaration(
                active_body,
                cursor,
                command_end,
                cast(MacroDeclarationSyntaxKind, command),
                source_text=body,
                group_ends=group_ends,
            )
            if declaration is not None:
                declarations.append(declaration)
                cursor = declaration.end
                continue
            recovery_end = _recover_malformed_declaration(active_body, command_end)
            ignored_ranges.append((cursor, recovery_end))
            cursor = recovery_end
            continue
        cursor = command_end

    declaration_ranges = tuple((item.start, item.end) for item in declarations)
    uses = _scan_uses(active_body, declaration_ranges, tuple(ignored_ranges))
    return InlineMacroSyntax(tuple(declarations), uses)


def _parse_declaration(
    text: str,
    start: int,
    command_end: int,
    kind: MacroDeclarationSyntaxKind,
    *,
    source_text: str,
    group_ends: dict[int, int],
) -> MacroDeclarationSyntax | None:
    if kind == "def":
        return _parse_def_declaration(
            text,
            start,
            command_end,
            source_text=source_text,
            group_ends=group_ends,
        )

    cursor = _skip_space(text, command_end)
    if cursor < len(text) and text[cursor] == "*":
        cursor = _skip_space(text, cursor + 1)
    target = _parse_macro_target(text, cursor, group_ends=group_ends)
    if target is None:
        return None
    name, name_start, name_end, cursor = target
    cursor = _skip_space(text, cursor)

    parameter_count = 0
    if cursor < len(text) and text[cursor] == "[":
        parameter_group = _read_group(text, cursor, "[", group_ends=group_ends)
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
        default_group = _read_group(text, cursor, "[", group_ends=group_ends)
        if default_group is None:
            return None
        _, _, cursor = default_group
        cursor = _skip_space(text, cursor)

    replacement_group = _read_group(text, cursor, "{", group_ends=group_ends)
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
        replacement=source_text[replacement_start:replacement_end],
    )


def _parse_def_declaration(
    text: str,
    start: int,
    command_end: int,
    *,
    source_text: str,
    group_ends: dict[int, int],
) -> MacroDeclarationSyntax | None:
    cursor = _skip_space(text, command_end)
    target = _parse_direct_macro_target(text, cursor)
    if target is None:
        return None
    name, name_start, name_end, cursor = target

    # TeX discards the space following a control word. Later spaces belong to
    # delimited parameter text, which this intentionally finite parser rejects.
    cursor = _skip_space(text, cursor)
    parameter_count = 0
    while True:
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

    replacement_group = _read_group(text, cursor, "{", group_ends=group_ends)
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
        replacement=source_text[replacement_start:replacement_end],
    )


def _parse_macro_target(
    text: str,
    cursor: int,
    *,
    group_ends: dict[int, int],
) -> tuple[str, int, int, int] | None:
    if cursor < len(text) and text[cursor] == "{":
        group = _read_group(text, cursor, "{", group_ends=group_ends)
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
    ignored_ranges: tuple[tuple[int, int], ...] = (),
) -> tuple[MacroUseSyntax, ...]:
    uses: list[MacroUseSyntax] = []
    range_index = 0
    ignored_index = 0
    cursor = 0
    while cursor < len(text):
        while (
            range_index < len(declaration_ranges) and declaration_ranges[range_index][1] <= cursor
        ):
            range_index += 1
        while ignored_index < len(ignored_ranges) and ignored_ranges[ignored_index][1] <= cursor:
            ignored_index += 1
        if (
            ignored_index < len(ignored_ranges)
            and ignored_ranges[ignored_index][0] <= cursor < ignored_ranges[ignored_index][1]
        ):
            cursor = ignored_ranges[ignored_index][1]
            continue
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


def _recover_malformed_declaration(text: str, start: int) -> int:
    """Skip one malformed declaration without interpreting nested commands."""

    brace_depth = 0
    bracket_depth = 0
    backslash_count = 0
    cursor = start
    while cursor < len(text):
        character = text[cursor]
        escaped = backslash_count % 2 == 1
        if not escaped and character == "\\":
            control = _read_control(text, cursor)
            if (
                control is not None
                and control[0] in _DECLARATION_COMMANDS
                and brace_depth == 0
                and bracket_depth == 0
            ):
                return cursor
        if not escaped:
            if character == "{":
                brace_depth += 1
            elif character == "[" and brace_depth == 0:
                bracket_depth = 1
            elif character == "}" and brace_depth:
                brace_depth -= 1
            elif character == "]" and brace_depth == 0:
                bracket_depth = 0
        if character == "\\":
            backslash_count += 1
        else:
            backslash_count = 0
        cursor += 1
    return len(text)


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


def _group_ends(text: str) -> dict[int, int]:
    """Index braces and optional arguments without treating bracket data as groups."""

    braces: list[int] = []
    brackets: dict[int, list[int]] = {}
    ends: dict[int, int] = {}
    backslash_count = 0
    for index, character in enumerate(text):
        escaped = backslash_count % 2 == 1
        if not escaped:
            if character == "{":
                braces.append(index)
            elif character == "}":
                brackets.pop(len(braces), None)
                if braces:
                    ends[braces.pop()] = index
            elif character == "[":
                brackets.setdefault(len(braces), []).append(index)
            elif character == "]":
                # Braces protect a closing bracket; another opening bracket
                # at the same depth is ordinary optional-argument content.
                for opener_index in brackets.pop(len(braces), ()):
                    ends[opener_index] = index
        if character == "\\":
            backslash_count += 1
        else:
            backslash_count = 0
    return ends


def _read_group(
    text: str,
    start: int,
    opener: str,
    *,
    group_ends: dict[int, int],
) -> tuple[int, int, int] | None:
    if start >= len(text) or text[start] != opener:
        return None
    group = group_ends.get(start)
    if group is None:
        return None
    return start + 1, group, group + 1


def _skip_space(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _is_control_letter(char: str) -> bool:
    return char == "@" or "A" <= char <= "Z" or "a" <= char <= "z"

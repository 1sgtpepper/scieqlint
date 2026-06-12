"""Render deterministic terminal GIFs used by the README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
WIDTH = 1120
HEIGHT = 580
PADDING = 32
LINE_HEIGHT = 28
FONT_SIZE = 18
BG = "#0f172a"
BAR = "#111827"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
GREEN = "#86efac"
YELLOW = "#fde68a"
RED = "#fca5a5"
BLUE = "#93c5fd"
PURPLE = "#c4b5fd"
PANEL = "#111827"
BORDER = "#334155"


def font(size: int = FONT_SIZE) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/data/data/com.termux/files/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


MONO = font()
BOLD = font(22)
TITLE = font(28)


def draw_terminal(lines: list[tuple[str, str]], visible: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 46), fill=BAR)
    for index, color in enumerate(("#ef4444", "#f59e0b", "#22c55e")):
        x = 24 + index * 22
        draw.ellipse((x, 16, x + 12, 28), fill=color)
    draw.text((104, 13), "scieqlint before review", fill=MUTED, font=MONO)

    draw.text((PADDING, 72), "Catch scientific-document mistakes before review", fill=TEXT, font=TITLE)
    draw.text(
        (PADDING, 108),
        "Exact algebra checks + equation-reference validation for Markdown/MyST docs",
        fill=MUTED,
        font=MONO,
    )

    draw.rounded_rectangle((PADDING, 148, WIDTH - PADDING, HEIGHT - 30), radius=8, fill=PANEL, outline=BORDER)

    y = 172
    for text, color in lines[:visible]:
        draw.text((PADDING + 24, y), text, fill=color, font=MONO)
        y += LINE_HEIGHT
    return image


def make_gif(path: Path, lines: list[tuple[str, str]], hold_frames: int = 4) -> None:
    frames: list[Image.Image] = []
    durations: list[int] = []
    for visible in range(1, len(lines) + 1):
        frames.append(draw_terminal(lines, visible))
        durations.append(300 if visible < len(lines) else 1300)
    for _ in range(hold_frames):
        frames.append(draw_terminal(lines, len(lines)))
        durations.append(900)
    frames[-1].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    make_gif(
        ASSET_DIR / "scieqlint-readme-demo.gif",
        [
            ("$ cat paper.md", GREEN),
            ("The expansion is:", TEXT),
            ("$$ (a+b)^2 = a^2 + b^2 $$", YELLOW),
            ("See {eq}`missing` for the derivation.", YELLOW),
            ("", TEXT),
            ("$ scieqlint check paper.md", GREEN),
            ("paper.md:3:5 ALG001 algebraic identity does not hold", RED),
            ("left - right = 2*a*b", BLUE),
            ("paper.md:4:5 REF002 equation reference target not found", RED),
            ("missing", YELLOW),
            ("", TEXT),
            ("$ scieqlint check paper-fixed.md", GREEN),
            ("OK  no diagnostics", PURPLE),
        ],
    )


if __name__ == "__main__":
    main()

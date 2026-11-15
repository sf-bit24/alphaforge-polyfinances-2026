"""Écrans des vidéos tldoole (1080 × 1920, vertical), dessinés par le code avec Pillow.

Chaque scène du scénario devient une image PNG pleine page : en-tête (marque, concept, progression),
bloc de contenu centré (titre, chiffre clé, courbe, barres ou liste), zone libre pour les sous-titres
incrustés par MediaConvert, puis pied de page (source des chiffres et mention « simulation »).

Les chiffres affichés arrivent déjà formatés par ``facts`` : ce module ne calcule rien, il dessine.
Police : Atkinson Hyperlegible (SIL OFL 1.1, Braille Institute), embarquée dans ``fonts/``.

Le contenu est dessiné sur un calque transparent, mesuré, puis collé centré sur le fond : Pillow ne mélange
les couleurs translucides que sur une image RGB, d'où le collage avec le canal alpha comme masque.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
MARGIN = 84
CONTENT_WIDTH = WIDTH - 2 * MARGIN
CONTENT_TOP, CONTENT_BOTTOM = 240, 1270
# Zone laissée libre pour les sous-titres incrustés (montage.CAPTION_Y).
CAPTION_TOP, CAPTION_BOTTOM = 1300, 1560
FOOTER_TOP = 1610

FONT_DIR = Path(__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "AtkinsonHyperlegible-Regular.ttf"
FONT_BOLD = FONT_DIR / "AtkinsonHyperlegible-Bold.ttf"

BG_TOP = (10, 18, 44)
BG_BOTTOM = (22, 40, 92)
TEXT = (255, 255, 255, 255)
MUTED = (184, 198, 230, 255)
FAINT = (132, 148, 190, 255)
ACCENTS = {
    "blue": (92, 200, 255),
    "yellow": (255, 206, 92),
    "green": (46, 213, 155),
    "coral": (255, 112, 130),
    "violet": (168, 148, 255),
}
LAYOUTS = ("hook", "statement", "number", "chart", "compare", "list", "outro")
NBSP = "\u00a0"
_SPLIT = re.compile(r"[ \t\r\n]+")
_FRENCH_SPACE = re.compile(r" ([?!:;»%$])")
# Symboles absents d'Atkinson Hyperlegible, remplacés avant le dessin (sinon : glyphe .notdef).
_SUBSTITUTES = str.maketrans(
    {
        "\u2192": "\u2013",
        "\u2190": "\u2013",
        "\u2191": "+",
        "\u2193": "\u2212",
        "\u2605": "*",
        "\u2713": "",
        "\u2714": "",
    }
)


@dataclass
class Frame:
    """Contexte commun à toutes les scènes d'une vidéo."""

    concept_label: str
    locale: str = "fr"
    accent: str = "blue"
    brand: str = "tldoole"
    disclaimer: str = "Simulation éducative · pas un conseil financier"

    @property
    def accent_rgb(self) -> tuple[int, int, int]:
        return ACCENTS.get(self.accent, ACCENTS["blue"])


@dataclass
class Scene:
    layout: str
    headline: str
    body: str | None = None
    number: dict[str, Any] | None = None  # {"text", "label", "sublabel"?}
    chart: dict[str, Any] | None = None  # {"values", "title", "start_label", "end_label", "end_text"?, "highlight"?}
    bars: list[dict[str, Any]] = field(default_factory=list)  # [{"label", "value", "text"}]
    items: list[str] = field(default_factory=list)
    source: str | None = None


# --------------------------------------------------------------------------- texte
@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def typeset(text: str | None, locale: str = "fr") -> str:
    """Espaces insécables de la typographie française (avant ? ! : ; » % $, après «)."""
    text = (text or "").translate(_SUBSTITUTES).strip()
    if locale == "fr":
        text = _FRENCH_SPACE.sub(NBSP + r"\1", text).replace("« ", "«" + NBSP)
    return text


def text_width(text: str, face: ImageFont.FreeTypeFont) -> float:
    return face.getlength(text)


def wrap(text: str, face: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Coupe aux espaces ordinaires seulement (jamais à une espace insécable)."""
    words = [w for w in _SPLIT.split(text or "") if w]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if text_width(candidate, face) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while text_width(word, face) > max_width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut] + "-", face) > max_width:
                cut -= 1
            lines.append(word[:cut] + "-")
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def fit(
    text: str, max_width: float, max_lines: int, sizes: tuple[int, ...], *, bold: bool
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Plus grande taille de police pour laquelle le texte tient en ``max_lines`` lignes."""
    for size in sizes:
        face = font(size, bold)
        lines = wrap(text, face, max_width)
        if len(lines) <= max_lines:
            return face, lines
    face = font(sizes[-1], bold)
    lines = wrap(text, face, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;:") + "…"
    return face, lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    face: ImageFont.FreeTypeFont,
    *,
    x: float,
    y: float,
    fill: tuple[int, ...],
    spacing: float = 1.18,
    align: str = "left",
    width: float = CONTENT_WIDTH,
) -> float:
    """Dessine des lignes à partir de ``y`` et renvoie l'ordonnée sous la dernière ligne."""
    step = face.size * spacing
    for index, line in enumerate(lines):
        lx = x + (width - text_width(line, face)) / 2 if align == "center" else x
        draw.text((lx, y + index * step), line, font=face, fill=fill)
    return y + len(lines) * step


def missing_glyphs(text: str, bold: bool = False) -> list[str]:
    """Caractères de ``text`` absents de la police (dessinés comme le glyphe .notdef)."""
    face = font(48, bold)
    notdef = face.getmask("\ue000")  # zone privée : glyphe .notdef
    reference = (notdef.size, bytes(notdef))
    missing = []
    for char in sorted(set(text)):
        if char.isspace():
            continue
        mask = face.getmask(char)
        if (mask.size, bytes(mask)) == reference:
            missing.append(char)
    return missing


# --------------------------------------------------------------------------- fond, en-tête, pied
@lru_cache(maxsize=1)
def _background() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM, strict=True))
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return img


def _to_png(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def background_png() -> bytes:
    return _to_png(_background().copy())


def _header(draw: ImageDraw.ImageDraw, frame: Frame, index: int, total: int) -> None:
    accent = frame.accent_rgb
    gap = 10
    segment = (CONTENT_WIDTH - gap * (total - 1)) / max(total, 1)
    for i in range(total):
        x0 = MARGIN + i * (segment + gap)
        color = (*accent, 255) if i <= index else (255, 255, 255, 64)
        draw.rounded_rectangle([x0, 72, x0 + segment, 80], radius=4, fill=color)
    brand_face = font(40, True)
    draw.rounded_rectangle(
        [MARGIN, 112, MARGIN + text_width(frame.brand, brand_face) + 48, 176], radius=32, fill=(*accent, 255)
    )
    draw.text((MARGIN + 24, 120), frame.brand, font=brand_face, fill=(*BG_TOP, 255))
    chip_face = font(34, True)
    label = typeset(frame.concept_label, frame.locale)[:28]
    chip_width = text_width(label, chip_face) + 48
    x1 = WIDTH - MARGIN
    draw.rounded_rectangle([x1 - chip_width, 114, x1, 174], radius=30, outline=(*accent, 255), width=3)
    draw.text((x1 - chip_width + 24, 123), label, font=chip_face, fill=TEXT)


def _footer(draw: ImageDraw.ImageDraw, frame: Frame, source: str | None) -> None:
    y = FOOTER_TOP
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=(255, 255, 255, 56), width=2)
    y += 28
    if source:
        face = font(30)
        lines = wrap(typeset(source, frame.locale), face, CONTENT_WIDTH)[:3]
        y = draw_lines(draw, lines, face, x=MARGIN, y=y, fill=MUTED, spacing=1.25) + 12
    face = font(28, True)
    draw.text((MARGIN, max(y, HEIGHT - 120)), typeset(frame.disclaimer, frame.locale), font=face, fill=FAINT)


def _star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple[int, ...]) -> None:
    import math

    points = []
    for k in range(10):
        radius = r if k % 2 == 0 else r * 0.45
        angle = -math.pi / 2 + k * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=color)


# --------------------------------------------------------------------------- blocs de contenu
# Chaque mise en page dessine son bloc à partir de y = 0 sur un calque transparent de la largeur de la
# page; render_scene le centre ensuite verticalement entre CONTENT_TOP et CONTENT_BOTTOM.
def _headline(
    c: ImageDraw.ImageDraw,
    text: str,
    frame: Frame,
    *,
    y: float,
    sizes: tuple[int, ...],
    max_lines: int = 3,
    align: str = "left",
) -> float:
    face, lines = fit(typeset(text, frame.locale), CONTENT_WIDTH, max_lines, sizes, bold=True)
    return draw_lines(c, lines, face, x=MARGIN, y=y, fill=TEXT, spacing=1.12, align=align)


def _paragraph(
    c: ImageDraw.ImageDraw,
    text: str | None,
    frame: Frame,
    *,
    y: float,
    max_lines: int,
    sizes: tuple[int, ...],
    color: tuple[int, ...] = MUTED,
    align: str = "left",
) -> float:
    if not text:
        return y
    face, lines = fit(typeset(text, frame.locale), CONTENT_WIDTH, max_lines, sizes, bold=False)
    return draw_lines(c, lines, face, x=MARGIN, y=y, fill=color, spacing=1.3, align=align)


def _hook(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    accent = (*frame.accent_rgb, 255)
    cx, cy, r = WIDTH // 2, 170, 160
    c.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=14)
    face = font(230, True)
    c.text((cx - text_width("?", face) / 2, cy - 150), "?", font=face, fill=accent)
    y = _headline(c, scene.headline, frame, y=cy + r + 90, sizes=(108, 100, 92, 84, 76), align="center")
    _paragraph(c, scene.body, frame, y=y + 36, max_lines=3, sizes=(58, 54, 50), align="center")


def _statement(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    c.rounded_rectangle([MARGIN, 0, MARGIN + 140, 18], radius=9, fill=(*frame.accent_rgb, 255))
    y = _headline(c, scene.headline, frame, y=70, sizes=(100, 92, 84, 76, 68))
    _paragraph(c, scene.body, frame, y=y + 48, max_lines=7, sizes=(62, 58, 54, 50, 46))


def _number(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    accent = (*frame.accent_rgb, 255)
    y = _headline(c, scene.headline, frame, y=0, sizes=(84, 76, 70, 64), max_lines=2)
    number = scene.number or {}
    value_face, value_lines = fit(
        typeset(str(number.get("text") or ""), frame.locale),
        CONTENT_WIDTH - 60,
        1,
        (240, 210, 184, 160, 136, 116),
        bold=True,
    )
    label_face, label_lines = fit(
        typeset(str(number.get("label") or ""), frame.locale), CONTENT_WIDTH - 100, 2, (54, 50, 46), bold=True
    )
    sub = typeset(str(number.get("sublabel") or ""), frame.locale)
    sub_face, sub_lines = fit(sub, CONTENT_WIDTH - 100, 2, (42, 38), bold=False) if sub else (None, [])
    card_top = y + 60
    inner = value_face.size * 1.1 + 30 + label_face.size * 1.18 * len(label_lines)
    if sub_face:
        inner += 18 + sub_face.size * 1.18 * len(sub_lines)
    card_bottom = card_top + inner + 150
    c.rounded_rectangle(
        [MARGIN, card_top, WIDTH - MARGIN, card_bottom],
        radius=48,
        fill=(255, 255, 255, 20),
        outline=(255, 255, 255, 48),
        width=2,
    )
    vy = draw_lines(c, value_lines, value_face, x=MARGIN, y=card_top + 70, fill=accent, align="center", spacing=1.1)
    ly = draw_lines(c, label_lines, label_face, x=MARGIN, y=vy + 30, fill=TEXT, align="center")
    if sub_face:
        draw_lines(c, sub_lines, sub_face, x=MARGIN, y=ly + 18, fill=MUTED, align="center")


def _chart(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    accent = frame.accent_rgb
    y = _headline(c, scene.headline, frame, y=0, sizes=(84, 76, 70, 64), max_lines=2)
    chart = scene.chart or {}
    values = [float(v) for v in chart.get("values") or [] if v is not None]
    top = y + 40
    if chart.get("title"):
        c.text((MARGIN, top), typeset(str(chart["title"]), frame.locale), font=font(40, True), fill=MUTED)
        top += 120
    else:
        top += 80
    x0, y0, x1, y1 = MARGIN, top, WIDTH - MARGIN, top + 560
    if len(values) < 2:
        return
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.08, hi + span * 0.08
    span = hi - lo

    def point(i: int, v: float) -> tuple[float, float]:
        return (x0 + (x1 - x0) * i / (len(values) - 1), y1 - (y1 - y0) * (v - lo) / span)

    points = [point(i, v) for i, v in enumerate(values)]
    for k in range(5):
        gy = y0 + (y1 - y0) * k / 4
        c.line([(x0, gy), (x1, gy)], fill=(255, 255, 255, 34), width=2)
    shade = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shade)
    sdraw.polygon([*points, (x1, y1), (x0, y1)], fill=(*accent, 60))
    highlight = chart.get("highlight")
    if isinstance(highlight, list | tuple) and len(highlight) == 2:
        a, b = int(highlight[0]), int(highlight[1])
        if 0 <= a < b < len(values):
            sdraw.rectangle([points[a][0], y0, points[b][0], y1], fill=(*ACCENTS["coral"], 70))
    layer.alpha_composite(shade)
    c.line(points, fill=(*accent, 255), width=9, joint="curve")
    ex, ey = points[-1]
    c.ellipse([ex - 16, ey - 16, ex + 16, ey + 16], fill=(*accent, 255))
    label_face = font(36)
    c.text((x0, y1 + 24), typeset(str(chart.get("start_label") or ""), frame.locale), font=label_face, fill=MUTED)
    end_label = typeset(str(chart.get("end_label") or ""), frame.locale)
    c.text((x1 - text_width(end_label, label_face), y1 + 24), end_label, font=label_face, fill=MUTED)
    if chart.get("end_text"):
        end_face = font(56, True)
        text = typeset(str(chart["end_text"]), frame.locale)
        tx = min(max(ex - text_width(text, end_face) / 2, x0), x1 - text_width(text, end_face))
        ty = ey - 100 if ey - 100 > y0 - 60 else ey + 36
        c.text((tx, ty), text, font=end_face, fill=TEXT)


def _compare(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    y = _headline(c, scene.headline, frame, y=0, sizes=(84, 76, 70, 64), max_lines=2) + 70
    bars = scene.bars[:3]
    if not bars:
        return
    peak = max(abs(float(b.get("value") or 0)) for b in bars) or 1.0
    second = ACCENTS["coral"] if frame.accent != "coral" else ACCENTS["yellow"]
    colors = [frame.accent_rgb, second, ACCENTS["violet"]]
    for i, bar in enumerate(bars):
        label = typeset(str(bar.get("label") or ""), frame.locale)[:36]
        c.text((MARGIN, y), label, font=font(48, True), fill=TEXT)
        track = y + 74
        c.rounded_rectangle([MARGIN, track, WIDTH - MARGIN, track + 76], radius=38, fill=(255, 255, 255, 26))
        share = abs(float(bar.get("value") or 0)) / peak
        right = MARGIN + max(76, (CONTENT_WIDTH - 260) * share)
        c.rounded_rectangle([MARGIN, track, right, track + 76], radius=38, fill=(*colors[i], 255))
        c.text(
            (right + 26, track + 6), typeset(str(bar.get("text") or ""), frame.locale), font=font(56, True), fill=TEXT
        )
        y = track + 76 + 80
    if scene.body:
        _paragraph(c, scene.body, frame, y=y, max_lines=3, sizes=(50, 46, 42))


def _items(c: ImageDraw.ImageDraw, items: list[str], frame: Frame, *, y: float, check: bool) -> float:
    accent = (*frame.accent_rgb, 255)
    for item in items[:4]:
        face, lines = fit(typeset(item, frame.locale), CONTENT_WIDTH - 110, 3, (58, 54, 50, 46), bold=False)
        if check:
            r = 32
            c.ellipse([MARGIN, y + 6, MARGIN + 2 * r, y + 6 + 2 * r], fill=accent)
            c.line([(MARGIN + 17, y + 40), (MARGIN + 29, y + 52), (MARGIN + 49, y + 24)], fill=(*BG_TOP, 255), width=8)
        else:
            c.rounded_rectangle(
                [MARGIN + 10, y + 10, MARGIN + 26, y + 10 + face.size * 1.25 * len(lines) - 20], radius=8, fill=accent
            )
        y = draw_lines(c, lines, face, x=MARGIN + 104, y=y, fill=TEXT, spacing=1.25) + 44
    return y


def _list(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    y = _headline(c, scene.headline, frame, y=0, sizes=(92, 84, 76, 68), max_lines=2) + 64
    _items(c, scene.items, frame, y=y, check=True)


def _outro(c: ImageDraw.ImageDraw, layer: Image.Image, scene: Scene, frame: Frame) -> None:
    _star(c, MARGIN + 60, 60, 60, (*frame.accent_rgb, 255))
    y = _headline(c, scene.headline, frame, y=170, sizes=(96, 88, 80, 72), max_lines=2) + 56
    if scene.items:
        _items(c, scene.items, frame, y=y, check=False)
    else:
        _paragraph(c, scene.body, frame, y=y, max_lines=5, sizes=(60, 56, 52), color=TEXT)


_LAYOUT_DRAWERS = {
    "hook": _hook,
    "statement": _statement,
    "number": _number,
    "chart": _chart,
    "compare": _compare,
    "list": _list,
    "outro": _outro,
}


def render_scene(scene: Scene, frame: Frame, *, index: int, total: int) -> bytes:
    """Image PNG d'une scène (``index`` à partir de 0)."""
    if scene.layout not in _LAYOUT_DRAWERS:
        raise ValueError(f"unknown layout {scene.layout!r}")
    page = _background().copy()
    chrome = ImageDraw.Draw(page, "RGBA")
    _header(chrome, frame, index, total)
    _footer(chrome, frame, scene.source)

    block = Image.new("RGBA", (WIDTH, 1600), (0, 0, 0, 0))
    _LAYOUT_DRAWERS[scene.layout](ImageDraw.Draw(block, "RGBA"), block, scene, frame)
    bbox = block.getbbox()
    if bbox:
        height = bbox[3] - bbox[1]
        room = CONTENT_BOTTOM - CONTENT_TOP
        top = CONTENT_TOP + max(0, (room - height) // 2) - bbox[1]
        visible = block.crop((0, bbox[1], WIDTH, bbox[1] + min(height, room)))
        page.paste(visible, (0, top + bbox[1]), visible)
    return _to_png(page)

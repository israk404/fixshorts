"""Everything drawn on screen: background, step cards, icons, progress bar and captions (Pillow).

Two layouts share one design: SHORT (1080x1920, vertical) and LONG (1920x1080, horizontal).
"""
import json
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT

FONTS = ROOT / "assets" / "fonts"
ICON_CODES = json.loads((ROOT / "assets" / "icons.json").read_text(encoding="utf-8"))
LOGOS = json.loads((ROOT / "assets" / "logos.json").read_text(encoding="utf-8"))
SS = 2  # supersampling for smooth rounded shapes


@dataclass(frozen=True)
class Layout:
    name: str
    W: int
    H: int
    x0: int               # card left
    x1: int               # card right
    px1: int              # progress bar right end
    progress_y: int
    card_top: int
    card_max_bottom: int
    cap_cx: int
    cap_cy: int
    cap_max_w: int
    cap_size: int
    headline: int         # starting headline size (shrinks to fit)
    hook_headline: int
    icon_panel: tuple = None  # (cx, cy, radius) for the big icon, horizontal layout only


# Vertical: content stays clear of the Shorts interface (top bar, right buttons, bottom title)
SHORT = Layout("short", 1080, 1920, 72, 1008, 1008, 212, 268, 1120, 520, 1330, 860, 84, 96, 108)
LONG = Layout("long", 1920, 1080, 120, 1230, 1800, 86, 140, 790, 960, 932, 1520, 74, 86, 96,
              icon_panel=(1515, 455, 225))

BASE = dict(
    bg_top=(9, 12, 18), bg_bottom=(16, 21, 31),
    panel=(20, 26, 36, 238), border=(46, 56, 72), chip=(32, 40, 54),
    text=(246, 248, 251), muted=(150, 162, 180), ink=(9, 12, 18),
    track=(42, 51, 66), danger=(248, 113, 113), good=(74, 222, 128),
)
ACCENTS = {
    "cyan": (34, 211, 238),
    "lime": (163, 230, 53),
    "amber": (251, 191, 36),
    "violet": (167, 139, 250),
}


@lru_cache(maxsize=96)
def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)


@lru_cache(maxsize=32)
def icon_font(size):
    return ImageFont.truetype(str(FONTS / "tabler-icons.ttf"), size)


def glyph(name):
    return chr(ICON_CODES.get(name, ICON_CODES["tool"]))


# ---------- logos ----------

def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def brand_color(slug, background):
    """The brand's color, or white/ink when it would disappear on this background."""
    hex_ = LOGOS.get(slug, {}).get("hex", "FFFFFF")
    color = tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))
    if contrast(color, background) >= 2.2:
        return color
    return (255, 255, 255) if _lum(background) < 0.4 else (14, 17, 22)


@lru_cache(maxsize=64)
def _logo_mask(slug, size):
    """Grayscale mask cropped to the logo. Its longer side is `size`; wide wordmarks get 40% more width."""
    info = LOGOS[slug]
    if info["source"] == "tabler":
        canvas = Image.new("L", (size * 2, size * 2), 0)
        ImageDraw.Draw(canvas).text((size, size), glyph(info["glyph"]), font=icon_font(size), fill=255, anchor="mm")
        mask = canvas
    else:
        mask = Image.open(ROOT / "assets" / "logos" / f"{slug}.png").convert("L")
    box = mask.getbbox()
    if box:
        mask = mask.crop(box)
    w, h = mask.size
    target = size * (1.4 if w / max(h, 1) > 2.2 else 1.0)
    k = target / max(w, h)
    return mask.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)


def logo_image(slug, size, color):
    """RGBA logo (cropped, longer side about `size` px) in `color`; None if the slug is unknown."""
    if slug not in LOGOS:
        return None
    mask = _logo_mask(slug, size)
    img = Image.new("RGBA", mask.size, tuple(color) + (255,))
    img.putalpha(mask)
    return img


def logo_plate(slug, d, t, problem_icon=None, ring=None):
    """A round plate (diameter d) with the logo, and an optional red problem badge at the lower right."""
    big = Image.new("RGBA", (d * SS, d * SS), (0, 0, 0, 0))
    pd = ImageDraw.Draw(big)
    plate = (18, 23, 33)
    pd.ellipse([3 * SS, 3 * SS, (d - 3) * SS, (d - 3) * SS], fill=plate + (255,), outline=ring or t["accent"], width=6 * SS)
    img = big.resize((d, d), Image.LANCZOS)
    size = int(d * 0.5)
    logo = logo_image(slug, size, brand_color(slug, plate))
    if logo:
        img.alpha_composite(logo, ((d - logo.width) // 2, (d - logo.height) // 2))
    if problem_icon:
        bd = int(d * 0.36)
        badge = Image.new("RGBA", (bd * SS, bd * SS), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(badge)
        bdraw.ellipse([0, 0, bd * SS - 1, bd * SS - 1], fill=t["danger"] + (255,), outline=plate + (255,), width=5 * SS)
        badge = badge.resize((bd, bd), Image.LANCZOS)
        ImageDraw.Draw(badge).text((bd / 2, bd / 2), glyph(problem_icon), font=icon_font(int(bd * 0.6)),
                                   fill=(255, 255, 255), anchor="mm")
        img.alpha_composite(badge, (d - bd - int(d * 0.02), d - bd - int(d * 0.02)))
    return img


def segment_logo(seg, main_logo):
    """Which logo a segment shows: the video's brand on the problem cards, a fix's own brand if it has one."""
    if seg.kind in ("hook", "why"):
        return main_logo if main_logo in LOGOS else ""
    if seg.kind == "fix":
        own = getattr(seg, "logo", "") or ""
        return own if own in LOGOS else ""
    return ""


def theme(name):
    t = dict(BASE)
    t["accent"] = ACCENTS.get(name, ACCENTS["cyan"])
    return t


# ---------- text helpers ----------

def text_w(f, s):
    return f.getlength(s)


def split_long(f, word, max_w):
    """Break a word wider than max_w: after underscores first (error codes), else after hyphens or slashes,
    else between characters."""
    if text_w(f, word) <= max_w:
        return [word]
    parts = [p for p in __import__("re").split(r"(?<=[_\-/])", word) if p]
    if len(parts) == 1:
        parts = list(word)
    out, cur = [], ""
    for p in parts:
        if cur and text_w(f, cur + p) > max_w:
            out.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        out.append(cur)
    return out


def wrap(f, text, max_w):
    lines, line = [], ""
    words = [piece for w in text.split() for piece in split_long(f, w, max_w)]
    for word in words:
        test = f"{line} {word}".strip()
        if text_w(f, test) <= max_w or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def spaced(draw, xy, text, f, fill, spacing):
    """Draw text with extra letter spacing; returns the width drawn."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += text_w(f, ch) + spacing
    return x - xy[0] - spacing


def spaced_w(f, text, spacing):
    return sum(text_w(f, ch) for ch in text) + spacing * (len(text) - 1)


# ---------- background ----------

@lru_cache(maxsize=16)
def background(theme_name, layout=SHORT):
    t = theme(theme_name)
    W, H = layout.W, layout.H
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(t["bg_top"], t["bg_bottom"])))
    img = img.convert("RGBA")

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    s = min(W, H) / 1080
    gd.ellipse([W - 520 * s, -380 * s, W + 420 * s, 520 * s], fill=t["accent"] + (70,))
    gd.ellipse([-420 * s, H - 760 * s, 420 * s, H + 120 * s], fill=t["accent"] + (28,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160 * s)))

    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for y in range(36, H, 54):
        for x in range(36, W, 54):
            dd.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 255, 14))
    img.alpha_composite(dots)
    return img


# ---------- card ----------

def _label_style(kind, t):
    if kind == "avoid":
        return "fill", t["danger"]
    if kind == "why":
        return "outline", t["accent"]
    return "fill", t["accent"]


def _layout_card(seg, kind_label, device, t, n_fixes, headline_size, L, draw=None):
    """Lay out (and optionally draw shapes for) the card content. Returns (bottom y, info)."""
    pad = 56
    x, y = L.x0 + pad, L.card_top + pad
    inner_w = (L.x1 - L.x0) - 2 * pad

    lf = font("Bold", 30)
    lw = spaced_w(lf, kind_label, 3) + 48
    style, color = _label_style(seg.kind, t)
    if draw:
        box = [x * SS, y * SS, (x + lw) * SS, (y + 62) * SS]
        if style == "fill":
            draw.rounded_rectangle(box, radius=31 * SS, fill=color)
        else:
            draw.rounded_rectangle(box, radius=31 * SS, outline=color, width=3 * SS)
    label_fill = t["ink"] if style == "fill" else color
    label_pos = (x + 24, y + 12)

    device_text = device.upper()
    if device_text and draw:
        df = font("Medium", 26)
        dw = spaced_w(df, device_text, 2) + 40
        dx = L.x1 - pad - dw
        draw.rounded_rectangle([dx * SS, (y + 4) * SS, (dx + dw) * SS, (y + 58) * SS],
                               radius=27 * SS, outline=t["border"], width=2 * SS)
    y += 62 + 40

    hf = font("Bold", headline_size)
    lines = wrap(hf, seg.headline, inner_w)
    line_h = int(headline_size * 1.14)
    headline_pos = (x, y, lines, hf, line_h)
    y += line_h * len(lines)

    detail = None
    if seg.kind == "cta" and n_fixes:
        y += 34
        detail = ("numbers", y)
        y += 120
        if seg.detail:
            y += 30
            detail = ("numbers+text", detail[1], y)
            y += 44
    elif seg.detail and "›" in seg.detail:
        y += 34
        cf = font("Medium", 34)
        parts = [p.strip() for p in seg.detail.split("›") if p.strip()]
        rows, row, row_w = [], [], 0
        for p in parts:
            cw = text_w(cf, p) + 44
            need = cw + (44 if row else 0)
            if row and row_w + need > inner_w:
                rows.append(row)
                row, row_w, need = [], 0, cw
            row.append((p, cw))
            row_w += need
        rows.append(row)
        detail = ("chips", y, rows, cf)
        y += len(rows) * 74 - 12
    elif seg.detail:
        y += 26
        pf = font("Medium", 38)
        plines = wrap(pf, seg.detail, inner_w)[:2]
        detail = ("text", y, plines, pf)
        y += len(plines) * 50

    return y + pad, dict(label=(kind_label, lf, label_fill, label_pos), device=device_text,
                         headline=headline_pos, detail=detail, pad=pad, inner_w=inner_w)


def segment_icon(seg, problem_icon):
    return {"hook": problem_icon, "why": problem_icon, "fix": "tool",
            "avoid": "alert-triangle", "cta": "circle-check"}[seg.kind]


def card_layer(seg, kind_label, device, theme_name, n_fixes, L=SHORT, problem_icon="tool", main_logo=""):
    """Full-frame RGBA layer with the card (and, horizontally, the big icon) for one segment."""
    t = theme(theme_name)
    size = L.hook_headline if seg.kind == "hook" else L.headline
    inner_w = (L.x1 - L.x0) - 112
    while True:
        bottom, _ = _layout_card(seg, kind_label, device, t, n_fixes, size, L)
        hf = font("Bold", size)
        whole = all(text_w(hf, w) <= inner_w for w in seg.headline.split() if "_" not in w)
        if (bottom <= L.card_max_bottom and whole) or size <= 56:
            break
        size -= 4

    big = Image.new("RGBA", (L.W * SS, L.H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    border = t["danger"] if seg.kind == "avoid" else t["border"]
    d.rounded_rectangle([L.x0 * SS, L.card_top * SS, L.x1 * SS, bottom * SS], radius=44 * SS,
                        fill=t["panel"], outline=border, width=2 * SS)
    if seg.kind == "avoid":
        d.rounded_rectangle([(L.x0 + 22) * SS, (L.card_top + 56) * SS, (L.x0 + 30) * SS, (bottom - 56) * SS],
                            radius=4 * SS, fill=t["danger"])
    _, info = _layout_card(seg, kind_label, device, t, n_fixes, size, L, draw=d)

    det = info["detail"]
    if det and det[0] == "chips":
        _, y, rows, cf = det
        for row in rows:
            x = L.x0 + info["pad"]
            for i, (p, cw) in enumerate(row):
                if i:
                    x += 44
                d.rounded_rectangle([x * SS, y * SS, (x + cw) * SS, (y + 62) * SS], radius=16 * SS, fill=t["chip"])
                x += cw
            y += 74
    if det and det[0].startswith("numbers"):
        y, r = det[1], 58
        total = n_fixes * 2 * r + (n_fixes - 1) * 36
        cx = (L.x0 + L.x1) / 2 - total / 2 + r
        for _ in range(n_fixes):
            d.ellipse([(cx - r) * SS, y * SS, (cx + r) * SS, (y + 2 * r) * SS], outline=t["accent"], width=5 * SS)
            cx += 2 * r + 36

    logo = segment_logo(seg, main_logo)
    if L.icon_panel and not logo:
        cx, cy, r = L.icon_panel
        ring = t["danger"] if seg.kind == "avoid" else t["accent"]
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=t["panel"],
                  outline=ring, width=6 * SS)
        d.ellipse([(cx - r + 26) * SS, (cy - r + 26) * SS, (cx + r - 26) * SS, (cy + r - 26) * SS],
                  outline=t["border"], width=2 * SS)

    layer = big.resize((L.W, L.H), Image.LANCZOS)
    d = ImageDraw.Draw(layer)

    label, lf, lfill, lpos = info["label"]
    spaced(d, lpos, label, lf, lfill, 3)
    if info["device"]:
        df = font("Medium", 26)
        dw = spaced_w(df, info["device"], 2) + 40
        dx = L.x1 - info["pad"] - dw
        spaced(d, (dx + 20, L.card_top + info["pad"] + 15), info["device"], df, t["muted"], 2)

    hx, hy, lines, hf, line_h = info["headline"]
    for i, line in enumerate(lines):
        d.text((hx, hy + i * line_h), line, font=hf, fill=t["text"])

    if det and det[0] == "chips":
        _, y, rows, cf = det
        af = font("Bold", 40)
        for row in rows:
            x = L.x0 + info["pad"]
            for i, (p, cw) in enumerate(row):
                if i:
                    d.text((x + 12, y + 2), "›", font=af, fill=t["accent"])
                    x += 44
                d.text((x + 22, y + 9), p, font=cf, fill=t["text"])
                x += cw
            y += 74
    elif det and det[0] == "text":
        _, y, plines, pf = det
        for i, line in enumerate(plines):
            d.text((L.x0 + info["pad"], y + i * 50), line, font=pf, fill=t["muted"])
    elif det and det[0].startswith("numbers"):
        y, r = det[1], 58
        nf = font("Bold", 60)
        total = n_fixes * 2 * r + (n_fixes - 1) * 36
        cx = (L.x0 + L.x1) / 2 - total / 2 + r
        for i in range(n_fixes):
            d.text((cx, y + r + 4), str(i + 1), font=nf, fill=t["accent"], anchor="mm")
            cx += 2 * r + 36
        if det[0] == "numbers+text":
            d.text(((L.x0 + L.x1) / 2, det[2] + 20), seg.detail, font=font("Medium", 36), fill=t["muted"], anchor="mm")

    if L.icon_panel and not logo:
        cx, cy, r = L.icon_panel
        color = t["danger"] if seg.kind == "avoid" else (t["good"] if seg.kind == "cta" else t["accent"])
        d.text((cx, cy), glyph(segment_icon(seg, problem_icon)), font=icon_font(int(r * 1.05)), fill=color, anchor="mm")
    elif L.icon_panel and logo:
        cx, cy, r = L.icon_panel
        plate = logo_plate(logo, 2 * r, t, problem_icon if seg.kind == "hook" else None)
        layer.alpha_composite(plate, (cx - r, cy - r))
    elif logo:
        # vertical: use the empty space between the card and the captions, when there is room
        top = bottom + 36
        cap_top = L.cap_cy - 100
        dia = min(250, cap_top - top - 24)
        if dia >= 150:
            plate = logo_plate(logo, dia, t, problem_icon if seg.kind == "hook" else None)
            layer.alpha_composite(plate, ((L.x0 + L.x1) // 2 - dia // 2, top + (cap_top - top - dia) // 2))
    return layer


def channel_mark(img, name, t, L=SHORT):
    if name:
        d = ImageDraw.Draw(img)
        y = 1462 if L.name == "short" else L.H - 64
        spaced(d, (L.x0, y), name.upper(), font("Medium", 26), t["muted"], 3)


# ---------- progress bar ----------

def draw_progress(img, n_segments, current, fraction, t, L=SHORT):
    d = ImageDraw.Draw(img)
    gap = 12
    seg_w = ((L.px1 - L.x0) - gap * (n_segments - 1)) / n_segments
    for i in range(n_segments):
        x = L.x0 + i * (seg_w + gap)
        box = [x, L.progress_y, x + seg_w, L.progress_y + 10]
        d.rounded_rectangle(box, radius=5, fill=t["accent"] if i < current else t["track"])
        if i == current and fraction > 0:
            d.rounded_rectangle([x, L.progress_y, x + max(10, seg_w * min(fraction, 1)), L.progress_y + 10],
                                radius=5, fill=t["accent"])


# ---------- captions ----------

def caption_layer(words, highlight, t, L=SHORT):
    """RGBA image of a caption chunk with one word highlighted. Returns (image, top-left xy)."""
    size = L.cap_size
    while True:
        f = font("Bold", size)
        space = text_w(f, " ") + 26  # room for the highlight pill between words
        lines, line, lw = [], [], 0
        for w in words:
            ww = text_w(f, w)
            need = ww + (space if line else 0)
            if line and lw + need > L.cap_max_w:
                lines.append(line)
                line, lw, need = [], 0, ww
            line.append(w)
            lw += need
        lines.append(line)
        too_wide = any(text_w(f, w) > L.cap_max_w for w in words)
        if (len(lines) <= 2 and not too_wide) or size <= 44:
            break
        size -= 6

    _, top, _, bottom = f.getbbox("Hgjy", anchor="ls")
    line_h = int((bottom - top) * 1.3)
    box_w, box_h = L.cap_max_w + 100, line_h * len(lines) + 40
    big = Image.new("RGBA", (box_w * SS, box_h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    bf = font("Bold", size * SS)
    idx, positions = 0, []
    for li, line in enumerate(lines):
        widths = [text_w(f, w) for w in line]
        total = sum(widths) + space * (len(line) - 1)
        x = box_w / 2 - total / 2
        base = 20 + li * line_h + (line_h - (bottom - top)) / 2 - top
        for w, ww in zip(line, widths):
            positions.append((idx, w, x, base))
            if idx == highlight:
                d.rounded_rectangle([(x - 14) * SS, (base + top - 12) * SS, (x + ww + 14) * SS, (base + bottom + 10) * SS],
                                    radius=18 * SS, fill=t["accent"])
            x += ww + space
            idx += 1
    for i, w, x, base in positions:
        if i == highlight:
            d.text((x * SS, base * SS), w, font=bf, fill=t["ink"], anchor="ls")
        else:
            d.text((x * SS, base * SS), w, font=bf, fill=t["text"], anchor="ls",
                   stroke_width=7 * SS, stroke_fill=(6, 8, 12))
    img = big.resize((box_w, box_h), Image.LANCZOS)
    return img, (int(L.cap_cx - box_w / 2), int(L.cap_cy - box_h / 2))

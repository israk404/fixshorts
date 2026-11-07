"""Everything that gets drawn: background, step cards, progress bar and captions (Pillow)."""
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT

FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1920
SS = 2  # supersampling for smooth rounded shapes

# Layout, chosen to stay clear of the Shorts interface (top bar, right buttons, bottom title)
X0, X1 = 72, 1008
PROGRESS_Y = 212
CARD_TOP = 268
CARD_MAX_BOTTOM = 1120
CAPTION_CENTER_X, CAPTION_CENTER_Y = 520, 1290
CAPTION_MAX_W = 860

BASE = dict(
    bg_top=(9, 12, 18), bg_bottom=(16, 21, 31),
    panel=(20, 26, 36, 238), border=(46, 56, 72), chip=(32, 40, 54),
    text=(246, 248, 251), muted=(150, 162, 180), ink=(9, 12, 18),
    track=(42, 51, 66), danger=(248, 113, 113),
)
ACCENTS = {
    "cyan": (34, 211, 238),
    "lime": (163, 230, 53),
    "amber": (251, 191, 36),
    "violet": (167, 139, 250),
}


@lru_cache(maxsize=64)
def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size)


def theme(name):
    t = dict(BASE)
    t["accent"] = ACCENTS.get(name, ACCENTS["cyan"])
    return t


# ---------- text helpers ----------

def text_w(f, s):
    return f.getlength(s)


def wrap(f, text, max_w):
    lines, line = [], ""
    for word in text.split():
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

@lru_cache(maxsize=8)
def background(theme_name):
    t = theme(theme_name)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(t["bg_top"], t["bg_bottom"])))
    img = img.convert("RGBA")

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 520, -380, W + 420, 520], fill=t["accent"] + (70,))
    gd.ellipse([-420, H - 760, 420, H + 120], fill=t["accent"] + (28,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))

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


def _layout_card(seg, kind_label, device, t, n_fixes, headline_size, draw=None, origin=(0, 0)):
    """Lay out (and optionally draw) the card content at 1x scale. Returns the content bottom y."""
    ox, oy = origin
    pad = 56
    x, y = X0 + pad, CARD_TOP + pad
    inner_w = (X1 - X0) - 2 * pad

    # Row 1: label pill + device chip
    lf = font("Bold", 30)
    lw = spaced_w(lf, kind_label, 3) + 48
    style, color = _label_style(seg.kind, t)
    if draw:
        box = [(x - ox) * SS, (y - oy) * SS, (x + lw - ox) * SS, (y + 62 - oy) * SS]
        if style == "fill":
            draw.rounded_rectangle(box, radius=31 * SS, fill=color)
        else:
            draw.rounded_rectangle(box, radius=31 * SS, outline=color, width=3 * SS)
    label_fill = t["ink"] if style == "fill" else color
    label_pos = (x + 24, y + 12)

    device_text = device.upper()
    if device_text:
        df = font("Medium", 26)
        dw = spaced_w(df, device_text, 2) + 40
        if draw:
            dx = X1 - pad - dw
            draw.rounded_rectangle([(dx - ox) * SS, (y + 4 - oy) * SS, (dx + dw - ox) * SS, (y + 58 - oy) * SS],
                                   radius=27 * SS, outline=t["border"], width=2 * SS)
    y += 62 + 40

    # Headline
    hf = font("Bold", headline_size)
    lines = wrap(hf, seg.headline, inner_w)
    line_h = int(headline_size * 1.14)
    headline_pos = (x, y, lines, hf, line_h)
    y += line_h * len(lines)

    detail_items = None
    if seg.kind == "cta" and n_fixes:
        y += 34
        detail_items = ("numbers", y)
        y += 120
        if seg.detail:
            y += 30
            detail_items = ("numbers+text", detail_items[1], y)
            y += 44
    elif seg.detail and "›" in seg.detail:
        y += 34
        cf = font("Medium", 34)
        parts = [p.strip() for p in seg.detail.split("›") if p.strip()]
        rows, row, row_w = [], [], 0
        arrow_w = 44
        for p in parts:
            cw = text_w(cf, p) + 44
            need = cw + (arrow_w if row else 0)
            if row and row_w + need > inner_w:
                rows.append(row)
                row, row_w = [], 0
                need = cw
            row.append((p, cw))
            row_w += need
        rows.append(row)
        detail_items = ("chips", y, rows, cf)
        y += len(rows) * 74 - 12
    elif seg.detail:
        y += 26
        pf = font("Medium", 38)
        plines = wrap(pf, seg.detail, inner_w)[:2]
        detail_items = ("text", y, plines, pf)
        y += len(plines) * 50

    bottom = y + pad
    return bottom, dict(label=(kind_label, lf, label_fill, label_pos), device=device_text,
                        headline=headline_pos, detail=detail_items, pad=pad, inner_w=inner_w)


def card_layer(seg, kind_label, device, theme_name, n_fixes):
    """Full-frame RGBA layer with the card for one segment."""
    t = theme(theme_name)
    start = 108 if seg.kind == "hook" else 96
    size = start
    while True:
        bottom, _ = _layout_card(seg, kind_label, device, t, n_fixes, size)
        if bottom <= CARD_MAX_BOTTOM or size <= 56:
            break
        size -= 4

    # Draw shapes at 2x, then text at 1x on top (FreeType text is already smooth)
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    border = t["danger"] if seg.kind == "avoid" else t["border"]
    d.rounded_rectangle([X0 * SS, CARD_TOP * SS, X1 * SS, bottom * SS], radius=44 * SS,
                        fill=t["panel"], outline=border, width=2 * SS)
    if seg.kind == "avoid":
        d.rounded_rectangle([(X0 + 22) * SS, (CARD_TOP + 56) * SS, (X0 + 30) * SS, (bottom - 56) * SS],
                            radius=4 * SS, fill=t["danger"])
    _, info = _layout_card(seg, kind_label, device, t, n_fixes, size, draw=d)

    det = info["detail"]
    if det and det[0] == "chips":
        _, y, rows, cf = det
        for row in rows:
            x = X0 + info["pad"]
            for i, (p, cw) in enumerate(row):
                if i:
                    x += 44
                d.rounded_rectangle([x * SS, y * SS, (x + cw) * SS, (y + 62) * SS], radius=16 * SS, fill=t["chip"])
                x += cw
            y += 74
    if det and det[0].startswith("numbers"):
        y = det[1]
        r = 58
        total = n_fixes * 2 * r + (n_fixes - 1) * 36
        cx = (X0 + X1) / 2 - total / 2 + r
        for i in range(n_fixes):
            d.ellipse([(cx - r) * SS, y * SS, (cx + r) * SS, (y + 2 * r) * SS], outline=t["accent"], width=5 * SS)
            cx += 2 * r + 36

    layer = big.resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(layer)

    label, lf, lfill, lpos = info["label"]
    spaced(d, lpos, label, lf, lfill, 3)
    if info["device"]:
        df = font("Medium", 26)
        dw = spaced_w(df, info["device"], 2) + 40
        dx = X1 - info["pad"] - dw
        spaced(d, (dx + 20, CARD_TOP + info["pad"] + 15), info["device"], df, t["muted"], 2)

    hx, hy, lines, hf, line_h = info["headline"]
    for i, line in enumerate(lines):
        d.text((hx, hy + i * line_h), line, font=hf, fill=t["text"])

    if det and det[0] == "chips":
        _, y, rows, cf = det
        af = font("Bold", 40)
        for row in rows:
            x = X0 + info["pad"]
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
            d.text((X0 + info["pad"], y + i * 50), line, font=pf, fill=t["muted"])
    elif det and det[0].startswith("numbers"):
        y = det[1]
        r = 58
        nf = font("Bold", 60)
        total = n_fixes * 2 * r + (n_fixes - 1) * 36
        cx = (X0 + X1) / 2 - total / 2 + r
        for i in range(n_fixes):
            d.text((cx, y + r + 4), str(i + 1), font=nf, fill=t["accent"], anchor="mm")
            cx += 2 * r + 36
        if det[0] == "numbers+text":
            tf = font("Medium", 36)
            d.text(((X0 + X1) / 2, det[2] + 20), seg.detail, font=tf, fill=t["muted"], anchor="mm")
    return layer


def channel_mark(img, name, t):
    if name:
        d = ImageDraw.Draw(img)
        spaced(d, (X0, 1462), name.upper(), font("Medium", 26), t["muted"], 3)


# ---------- progress bar ----------

def draw_progress(img, n_segments, current, fraction, t):
    d = ImageDraw.Draw(img)
    gap = 12
    seg_w = ((X1 - X0) - gap * (n_segments - 1)) / n_segments
    for i in range(n_segments):
        x = X0 + i * (seg_w + gap)
        box = [x, PROGRESS_Y, x + seg_w, PROGRESS_Y + 10]
        d.rounded_rectangle(box, radius=5, fill=t["accent"] if i < current else t["track"])
        if i == current and fraction > 0:
            d.rounded_rectangle([x, PROGRESS_Y, x + max(10, seg_w * min(fraction, 1)), PROGRESS_Y + 10],
                                radius=5, fill=t["accent"])


# ---------- captions ----------

def caption_layer(words, highlight, t):
    """RGBA image of a caption chunk with one word highlighted. Returns (image, top-left xy)."""
    size = 84
    while True:
        f = font("Bold", size)
        space = text_w(f, " ") + 26  # room for the highlight pill between words
        lines, line, lw = [], [], 0
        for w in words:
            ww = text_w(f, w)
            need = ww + (space if line else 0)
            if line and lw + need > CAPTION_MAX_W:
                lines.append(line)
                line, lw, need = [], 0, ww
            line.append(w)
            lw += need
        lines.append(line)
        if len(lines) <= 2 or size <= 60:
            break
        size -= 6

    # Vertical metrics from real glyphs, relative to the baseline (top is negative)
    _, top, _, bottom = f.getbbox("Hgjy", anchor="ls")
    line_h = int((bottom - top) * 1.3)
    box_w, box_h = CAPTION_MAX_W + 100, line_h * len(lines) + 40
    big = Image.new("RGBA", (box_w * SS, box_h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    bf = font("Bold", size * SS)
    idx = 0
    positions = []
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
    return img, (int(CAPTION_CENTER_X - box_w / 2), int(CAPTION_CENTER_Y - box_h / 2))

"""YouTube thumbnails (1280x720) in three styles: bold, split and clean."""
from PIL import Image, ImageDraw, ImageFilter

from .cards import font, glyph, icon_font, theme, wrap

W, H = 1280, 720
STYLES = ("bold", "split", "clean")


def _fit_text(text, max_w, max_lines, start, smallest=64):
    size = start
    while size > smallest:
        f = font("Bold", size)
        lines = wrap(f, text, max_w)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines):
            return f, lines, size
        size -= 6
    f = font("Bold", smallest)
    return f, wrap(f, text, max_w)[:max_lines], smallest


def _stroke_text(d, xy, text, f, fill, stroke, width):
    d.text(xy, text, font=f, fill=fill, stroke_width=width, stroke_fill=stroke)


def _badge(img, x, y, text, bg, fg, check=True):
    """Rounded pill with a check icon, e.g. FIXED."""
    big = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    f = font("Bold", 46)
    tw = f.getlength(text)
    w = tw + (118 if check else 64)
    d.rounded_rectangle([x, y, x + w, y + 84], radius=42, fill=bg)
    if check:
        d.text((x + 52, y + 42), glyph("circle-check"), font=icon_font(54), fill=fg, anchor="mm")
        d.text((x + 90, y + 44), text, font=f, fill=fg, anchor="lm")
    else:
        d.text((x + 32, y + 44), text, font=f, fill=fg, anchor="lm")
    img.alpha_composite(big)


def _glow_bg(accent, base=(10, 13, 20)):
    img = Image.new("RGBA", (W, H), base + (255,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([700, -260, 1500, 640], fill=accent + (110,))
    gd.ellipse([-300, 380, 500, 1100], fill=accent + (40,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(140)))
    return img


def make_thumbnail(script, theme_name, style, out_path):
    t = theme(theme_name)
    accent, good, danger = t["accent"], t["good"], t["danger"]
    text = (script.thumbnail_text or (script.segments[0].headline if script.segments else "")).upper()
    icon = glyph(script.icon)
    device = (script.device or "").upper()

    if style == "split":
        f, lines, size = _fit_text(text, 1160, 2, 112)
        line_h = int(size * 1.05)
        y = H - 40 - line_h * len(lines)
        band_top = y - 28
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        d = ImageDraw.Draw(img)
        # left (problem) and right (fixed) halves meet on a slanted edge above the text band
        top_x, bot_x = 700, 700 - 120 * band_top / H
        d.polygon([(0, 0), (top_x, 0), (bot_x, band_top), (0, band_top)], fill=(52, 16, 20))
        d.polygon([(top_x, 0), (W, 0), (W, band_top), (bot_x, band_top)], fill=(12, 46, 30))
        d.line([(top_x, 0), (bot_x, band_top)], fill=(255, 255, 255), width=8)
        d.rectangle([0, band_top, W, H], fill=(8, 9, 12))
        d.rectangle([0, band_top, W, band_top + 6], fill=(255, 255, 255))
        icon_y = band_top / 2
        icon_size = int(min(270, band_top * 0.72))
        d.text((top_x / 2 + 20, icon_y), icon, font=icon_font(icon_size), fill=danger, anchor="mm")
        d.text(((top_x + W) / 2, icon_y), glyph("circle-check"), font=icon_font(icon_size), fill=good, anchor="mm")
        for i, line in enumerate(lines):
            _stroke_text(d, (W / 2 - f.getlength(line) / 2, y + i * line_h - 10), line, f, (255, 255, 255), (0, 0, 0), 6)

    elif style == "clean":
        img = Image.new("RGBA", (W, H), accent + (255,))
        d = ImageDraw.Draw(img)
        ink = (12, 14, 18)
        f, lines, size = _fit_text(text, 700, 3, 150)
        line_h = int(size * 1.02)
        y = (H - line_h * len(lines)) / 2 - 20
        for i, line in enumerate(lines):
            d.text((70, y + i * line_h), line, font=f, fill=ink)
        d.ellipse([850, 150, 1270, 570], fill=ink)
        d.text((1060, 360), icon, font=icon_font(250), fill=accent, anchor="mm")
        if device:
            d.text((72, 64), device, font=font("Bold", 34), fill=ink)

    else:  # bold
        img = _glow_bg(accent)
        d = ImageDraw.Draw(img)
        cx, cy, r = 1010, 330, 230
        ring = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
        rd = ImageDraw.Draw(ring)
        rd.ellipse([(cx - r) * 2, (cy - r) * 2, (cx + r) * 2, (cy + r) * 2], fill=(18, 23, 33, 255),
                   outline=accent, width=16)
        img.alpha_composite(ring.resize((W, H), Image.LANCZOS))
        d = ImageDraw.Draw(img)
        d.text((cx, cy), icon, font=icon_font(270), fill=accent, anchor="mm")
        f, lines, size = _fit_text(text, 650, 3, 132)
        line_h = int(size * 1.02)
        y = 70
        for i, line in enumerate(lines):
            fill = accent if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255)
            _stroke_text(d, (60, y + i * line_h), line, f, fill, (0, 0, 0), 8)
        _badge(img, 60, H - 140, "FIXED", good, (8, 30, 16))
        if device:
            df = font("Bold", 30)
            dw = df.getlength(device) + 44
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([W - 60 - dw, H - 120, W - 60, H - 66], radius=27, outline=(255, 255, 255), width=3)
            d.text((W - 60 - dw / 2, H - 93), device, font=df, fill=(255, 255, 255), anchor="mm")

    img.convert("RGB").save(out_path, quality=92)
    return out_path

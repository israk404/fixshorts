"""YouTube thumbnails (1280x720) in three styles: bold, split and clean."""
import re

from PIL import Image, ImageDraw, ImageFilter

from .cards import LOGOS, brand_color, font, glyph, icon_font, logo_image, theme, wrap

W, H = 1280, 720
STYLES = ("bold", "split", "clean")


def _fit_text(text, max_w, max_lines, start, smallest=64):
    size = start
    while size > smallest:
        f = font("Bold", size)
        lines = wrap(f, text, max_w)
        # only error codes (with underscores) may be broken across lines; normal words must fit whole
        whole = all(f.getlength(w) <= max_w for w in text.split() if "_" not in w)
        if len(lines) <= max_lines and whole and all(f.getlength(l) <= max_w for l in lines):
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


def _problem_badge(img, cx, cy, d, icon, fill, ring):
    """Small round badge with the problem icon, e.g. a red Wi-Fi-off over the Windows logo."""
    big = Image.new("RGBA", (d * 2, d * 2), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse([0, 0, d * 2 - 1, d * 2 - 1], fill=fill, outline=ring, width=10)
    badge = big.resize((d, d), Image.LANCZOS)
    ImageDraw.Draw(badge).text((d / 2, d / 2), glyph(icon), font=icon_font(int(d * 0.58)), fill=(255, 255, 255), anchor="mm")
    img.alpha_composite(badge, (int(cx - d / 2), int(cy - d / 2)))


def _logo_or_icon(img, slug, icon, cx, cy, size, bg, icon_color):
    """Draw the brand logo when there is one, else the problem icon. Returns True if a logo was drawn."""
    logo = logo_image(slug, size, brand_color(slug, bg)) if slug in LOGOS else None
    if logo:
        img.alpha_composite(logo, (int(cx - logo.width / 2), int(cy - logo.height / 2)))
        return True
    ImageDraw.Draw(img).text((cx, cy), glyph(icon), font=icon_font(int(size * 1.08)), fill=icon_color, anchor="mm")
    return False


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
    raw = script.thumbnail_text or (script.segments[0].headline if script.segments else "")
    text = raw.upper()
    err = (script.error_text or "").strip()
    if err:  # capitals for normal words, but the exact error keeps its own form (0x80070005, not 0X80070005)
        text = re.sub(re.escape(err), lambda m: err, text, flags=re.I)
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
        left_cx = top_x / 2 + 10
        if _logo_or_icon(img, script.logo, script.icon, left_cx, icon_y, int(icon_size * 0.9), (52, 16, 20), danger):
            _problem_badge(img, left_cx + icon_size * 0.42, icon_y + icon_size * 0.34, int(icon_size * 0.42),
                           script.icon, danger + (255,), (52, 16, 20, 255))
        d = ImageDraw.Draw(img)
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
        if _logo_or_icon(img, script.logo, script.icon, 1060, 360, 230, ink, accent):
            _problem_badge(img, 1205, 505, 120, script.icon, danger + (255,), ink + (255,))
        d = ImageDraw.Draw(img)
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
        if _logo_or_icon(img, script.logo, script.icon, cx, cy, 250, (18, 23, 33), accent):
            _problem_badge(img, cx + 165, cy + 165, 130, script.icon, danger + (255,), (10, 13, 20, 255))
        d = ImageDraw.Draw(img)
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

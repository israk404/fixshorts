"""Per-format script text, and the upload details for both videos."""
from .schema import LINK_TOKEN, Segment

LINK_LINES = {
    "long": ("The link is in the description.", "The links are in the description."),
    "short": ("The link is in the full video.", "The links are in the full video."),
}


def format_segments(script, fmt):
    """Copy of the segments with {LINK} turned into the right sentence for this video."""
    n_links = len(script.used_links())
    one, many = LINK_LINES[fmt]
    line = many if n_links > 1 else one
    out = []
    for s in script.segments:
        text = s.narration
        if LINK_TOKEN in text:
            text = text.replace(LINK_TOKEN, line if n_links else "")
        out.append(Segment(kind=s.kind, headline=s.headline, detail=s.detail, narration=" ".join(text.split())))
    return out


def title(script):
    u = script.upload
    if not u or not u.titles:
        return script.slug
    return u.titles[min(max(script.title_choice, 0), len(u.titles) - 1)]


def long_description(script):
    u = script.upload
    parts = [u.description.strip()]
    links = script.used_links()
    if links:
        parts.append("Links:\n" + "\n".join(f"{l.label or 'Link'}: {l.url}" for l in links))
    if u.hashtags:
        parts.append(" ".join(u.hashtags))
    return "\n\n".join(parts)


def short_description(script):
    u = script.upload
    parts = [u.description.strip()]
    n = len(script.used_links())
    if n:
        parts.append(("The links are" if n > 1 else "The link is") + " in the full video on my channel.")
    parts.append(" ".join(["#shorts"] + u.hashtags))
    return "\n\n".join(parts)


def upload_fields(script):
    """Everything the app shows with copy buttons, for both videos."""
    u = script.upload
    return {
        "long": {"title": title(script), "description": long_description(script),
                 "tags": ", ".join(u.tags), "pinned_comment": u.pinned_comment},
        "short": {"title": title(script), "description": short_description(script),
                  "tags": ", ".join(u.tags), "pinned_comment": u.pinned_comment},
    }


def upload_text(script, durations):
    f = upload_fields(script)
    out = []
    for key, name, file in (("long", "FULL VIDEO (16:9)", "video.mp4"), ("short", "SHORT (9:16)", "short.mp4")):
        d = f[key]
        out += [f"===== {name}: {file} =====", "",
                "TITLE", d["title"], "",
                "DESCRIPTION", d["description"], "",
                "TAGS", d["tags"], "",
                "PINNED COMMENT", d["pinned_comment"], ""]
        if key == "long":
            out += ["THUMBNAIL: thumbnail.jpg", f"LENGTH: {durations.get('long', 0):.0f} seconds", ""]
        else:
            out += ["COVER: pick the first frame (or upload cover.jpg)",
                    "RELATED VIDEO: after both are uploaded, set the Short's Related video to the full video",
                    f"LENGTH: {durations.get('short', 0):.0f} seconds", ""]
    out += ["Audience: No, it's not made for kids", "Category: Howto & Style (or Science & Technology)"]
    return "\n".join(out) + "\n"

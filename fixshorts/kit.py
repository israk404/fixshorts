"""Writes the human-readable files: script.md for review and upload.txt for YouTube Studio."""


def script_markdown(script, word_count=None, duration=None):
    lines = [f"# {script.slug}", ""]
    lines.append(f"- Verdict: **{script.verdict}**" + (f" ({script.reject_reason})" if script.reject_reason else ""))
    lines.append(f"- Device: {script.device or '-'}")
    lines.append(f"- Confidence: **{script.confidence}**")
    lines.append(f"- Words: {word_count or script.word_count()}" + (f", about {duration:.0f} s" if duration else ""))
    if script.risk_flags:
        lines += ["", "## Risk flags (check these)"] + [f"- {f}" for f in script.risk_flags]
    if script.review_notes:
        lines += ["", "## Review notes"] + [f"- {n}" for n in script.review_notes]
    lines += ["", "## Script"]
    fix = 0
    for seg in script.segments:
        if seg.kind == "fix":
            fix += 1
        name = f"FIX {fix}" if seg.kind == "fix" else seg.kind.upper()
        lines += ["", f"### {name}: {seg.headline}"]
        if seg.detail:
            lines.append(f"_On screen:_ {seg.detail}")
        lines.append("")
        lines.append(seg.narration)
    lines += ["", "To change anything, edit script.json (not this file), then run the render command again.", ""]
    return "\n".join(lines)


def upload_text(script, duration):
    u = script.upload
    if u is None:
        return "No upload details: this script was rejected.\n"
    out = ["TITLE (pick one, paste into Title)"]
    out += [f"  {i}. {t}" for i, t in enumerate(u.titles, 1)]
    out += ["", "DESCRIPTION (paste into Description)", "-" * 40, u.description.strip()]
    if u.hashtags:
        out += ["", " ".join(u.hashtags)]
    out += ["-" * 40, "", "TAGS (paste into Tags, under Show more)", ", ".join(u.tags)]
    out += ["", "PINNED COMMENT (post it, then pin it)", u.pinned_comment]
    out += ["", "STUDIO SETTINGS",
            "  Audience: No, it's not made for kids",
            f"  Category: Howto & Style  (or Science & Technology)",
            f"  Length: {duration:.0f} seconds"]
    out += ["", "BEFORE YOU PUBLISH", f"  Confidence: {script.confidence}"]
    out += [f"  Check: {f}" for f in script.risk_flags]
    out += [f"  Note: {n}" for n in script.review_notes]
    if script.source.url or script.source.subreddit:
        out += ["", f"SOURCE (for your records): {script.source.subreddit} {script.source.url}".rstrip()]
    return "\n".join(out) + "\n"

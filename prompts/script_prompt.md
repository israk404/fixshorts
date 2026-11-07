# Task
Read the discussion below. Decide whether it makes a good video. If it does, write the script, the links and the upload details. The same script is used for a vertical Short and a horizontal video.

## Segments, in this order
1. **hook** (exactly 1). Name the problem in the viewer's words in one short sentence, then promise the fixes ("Here's how to fix it."). Keep it under 25 words. Headline: the problem as a short question, at most 40 characters. Detail: optional, at most 50 characters.
2. **why** (0 or 1). One sentence on the most likely cause. Skip it if the cause isn't clear. Headline: the cause, at most 45 characters.
3. **fix** (1 to 3). One fix per segment, easiest first, told as direct steps. Headline: the action, starting with a verb, at most 40 characters. Detail: the exact menu path with " › " between steps, at most 70 characters, or a short tip, or empty. If the fix needs a link, end its narration with {LINK}.
4. **avoid** (0 or 1). One common mistake to avoid. Headline starts with "Don't", at most 40 characters.
5. **cta** (exactly 1). Ask which fix worked, under 12 words. Headline: "Which fix worked for you?" or similar.

Total narration across all segments: {{MIN_WORDS}} to {{MAX_WORDS}} words.

## Other fields
- **thumbnail_text**: 2 to 4 punchy words naming the problem, at most 28 characters, for example "WI-FI KEEPS DROPPING".
- **icon**: the one icon that best shows the problem, chosen from this list only: {{ICONS}}
- **logo**: the brand whose product the problem is about, as a slug from this list, or "" when no single brand fits (a general PC problem, or a brand that isn't listed): {{LOGOS}}. Use the operating system's logo (for example "windows" or "android") when the problem is about the system itself.
- **segment "logo"** (optional, fix segments only): the brand of a tool or site that fix uses, from the same list, for example "intel" for Intel's driver tool. Leave it "" otherwise.
- **links**: every useful link. Copy URLs exactly from the "Links found" list, or add an official one you are sure exists. "label" is a short name for the description, like "Intel driver download". "use" is true if it belongs in the description.
- **titles**: 3 options, each at most 70 characters. Include the device or OS when it matters. Honest, no clickbait, no ALL CAPS, no emoji.
- **description**: 2 to 5 short lines: the problem in one line, then the fixes as a numbered list. No links and no hashtags here; the app adds them.
- **tags**: 8 to 15 search phrases people would actually type.
- **hashtags**: 2 to 4 topic hashtags, without #shorts.
- **pinned_comment**: one question that invites viewers to share what worked for them.

## Output
Return only one json object, exactly in this shape (no markdown, no comments):

{
  "verdict": "use",
  "reject_reason": "",
  "slug": "short-kebab-case-topic",
  "device": "Windows 11",
  "confidence": "high",
  "risk_flags": ["side effects or risks the viewer should know about"],
  "review_notes": ["anything the reviewer should double-check"],
  "thumbnail_text": "WI-FI KEEPS DROPPING",
  "icon": "wifi-off",
  "logo": "windows",
  "segments": [
    {"kind": "hook", "headline": "", "detail": "", "narration": ""},
    {"kind": "why", "headline": "", "detail": "", "narration": ""},
    {"kind": "fix", "headline": "", "detail": "", "narration": "... {LINK}", "logo": ""},
    {"kind": "avoid", "headline": "", "detail": "", "narration": ""},
    {"kind": "cta", "headline": "", "detail": "", "narration": ""}
  ],
  "links": [
    {"url": "https://...", "label": "", "use": true, "reason": "why it helps or why not to use it", "source": "thread"}
  ],
  "upload": {
    "titles": ["", "", ""],
    "description": "",
    "tags": [""],
    "hashtags": ["#windows11"],
    "pinned_comment": ""
  }
}

- "device" is the device or OS the fixes are for, for example "Windows 11", "Windows", "Android", "iPhone", "Mac", "Router" or "Any device".
- "confidence" is "high", "medium" or "low": how sure you are that every fix is correct and safe.
- If verdict is "reject", fill "reject_reason", leave "segments" and "links" empty and set "upload" to null.

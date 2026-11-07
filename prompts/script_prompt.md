# Task
Read the Reddit post and its top comments below. Decide whether it makes a good Short. If it does, write the script and the upload details.

## Segments, in this order
1. **hook** (exactly 1). Say the problem in the viewer's own words within the first 3 seconds, then promise the fixes ("Here are 3 fixes, easiest first."). Headline: the problem as a short question, at most 40 characters. Detail: optional, at most 50 characters (for example "Every other device works fine").
2. **why** (0 or 1). One or two sentences on the most likely cause. Skip it if the cause isn't clear. Headline: the cause, at most 45 characters.
3. **fix** (1 to 3). One fix per segment, easiest first. Headline: the action, starting with a verb, at most 40 characters. Detail: the exact menu path with " › " between steps, at most 70 characters. If there is no menu path, give a short practical tip instead, or leave it empty.
4. **avoid** (0 or 1). One common mistake that the comments warn about. Headline starts with "Don't", at most 40 characters.
5. **cta** (exactly 1). Ask which fix worked, under 12 words. Headline: "Which fix worked for you?" or similar.

Total narration across all segments: {{MIN_WORDS}} to {{MAX_WORDS}} words (about 45 to 55 seconds).

## Upload details
- **titles**: 3 options, each at most 70 characters. Include the device or OS when it matters. Honest, no clickbait, no ALL CAPS, no emoji.
- **description**: 2 to 5 short lines: the problem in one line, the fixes as a numbered list, then "Fixes collected from a r/<subreddit> discussion." Never include usernames.
- **tags**: 8 to 15 search phrases people would actually type.
- **hashtags**: 3 to 5, starting with #shorts.
- **pinned_comment**: one question that invites viewers to share what worked for them.

## Output
Return only one JSON object, exactly in this shape (no markdown, no comments):

{
  "verdict": "use",
  "reject_reason": "",
  "slug": "short-kebab-case-topic",
  "device": "Windows 11",
  "confidence": "high",
  "risk_flags": ["side effects or risks the viewer should know about"],
  "review_notes": ["anything the human reviewer should double-check"],
  "segments": [
    {"kind": "hook", "headline": "", "detail": "", "narration": ""},
    {"kind": "why", "headline": "", "detail": "", "narration": ""},
    {"kind": "fix", "headline": "", "detail": "", "narration": ""},
    {"kind": "avoid", "headline": "", "detail": "", "narration": ""},
    {"kind": "cta", "headline": "", "detail": "", "narration": ""}
  ],
  "upload": {
    "titles": ["", "", ""],
    "description": "",
    "tags": [""],
    "hashtags": ["#shorts"],
    "pinned_comment": ""
  },
  "source": {"subreddit": "r/...", "url": ""}
}

- "device" is the device or OS the fixes are for, for example "Windows 11", "Windows", "Android", "iPhone", "Mac", "Router" or "Any device".
- "confidence" is "high", "medium" or "low": how sure you are that every fix is correct and safe.
- If verdict is "reject", fill "reject_reason" and leave "segments" empty and "upload" null.
- Use the subreddit and URL from the post if they are given, otherwise leave them empty.

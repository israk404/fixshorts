# FixShorts

Paste Reddit links about PC, phone and tech problems. FixShorts reads each post, has DeepSeek write a direct problem-and-solution script, waits for your review, then makes two videos (a vertical Short and a horizontal full video), a thumbnail, and ready-to-paste upload details. It runs on your Windows PC; only the AI script and the Edge voice go online.

![Frames from a Short, the full video and its thumbnail](docs/preview.jpg)

![The review screen: what the AI says, the editable script, links and upload details](docs/app.jpg)

## Set up (once)

1. Install **Python 3.12** from [python.org](https://www.python.org/downloads/windows/). During the install, tick **Add python.exe to PATH**.
2. Download this project (Code → Download ZIP, or `git clone https://github.com/israk404/fixshorts`) and unzip it somewhere like `C:\fixshorts`.
3. Double-click **setup.bat**. It installs the Python packages and, if needed, FFmpeg through winget. Takes a few minutes.
4. Double-click **start.bat**. The app opens in your browser at http://127.0.0.1:8765. Keep the black window open while you use it.
5. In **Settings**:
   - Paste your DeepSeek API key (from [platform.deepseek.com](https://platform.deepseek.com)) and press Save key.
   - Press **Log in to Reddit**. A browser window opens; log in with a spare Reddit account. The window closes by itself when you're done, and the app remembers the login in its own browser profile (it never touches your normal browser).

## Daily use

1. **Paste links**, one per line, and press **Add to queue**. Each link is read and scripted in turn. Nothing is made into a video yet.

   A post you've used before is skipped, even months later and even if you deleted that job. The app matches posts by Reddit's post ID, so www., old., mobile, redd.it and share links all count as the same post (share links are checked once the page opens, before any AI cost). To make one again on purpose, tick **Allow links I've used before**, or press **Make it anyway** on the job.
2. **Review** each job marked gold ("Ready for your review"). You see:
   - what the AI says: its confidence, risks the video mentions, notes for you, and a rule check
   - the problem words: the exact error (like `0x80070005` or `DRIVER_IRQL_NOT_LESS_OR_EQUAL`) and the problem in search words (like "Wi-Fi keeps disconnecting"), with a live check of where they appear
   - the script, segment by segment: on-screen headline, small on-screen text, and what the voice says
   - links for the description, each marked Official site or Check this site, and whether it opens
   - thumbnail words, problem icon and brand logo, titles, description, tags, hashtags and pinned comment

   Edit anything, then press **Save changes**. **Write again** asks the AI for a new script.
3. Press **Approve and make videos**, or **Approve all ready** for the whole batch. Videos are made one job at a time.
4. When a job shows **Videos ready**, open it to play both videos, copy each upload field, or open the folder.

**Exact problem words:** people search for the exact error they see and click when a title shows it. So the AI copies the error code or message from the post character for character, and the app checks it:

- With an error, it must appear unchanged in the first card, every title, the thumbnail and the description's first line. An error that isn't in the post (a dropped digit, a "corrected" spelling) is sent back to the AI to fix.
- Without an error, the problem in the asker's own words ("laptop won't turn on") must be on the first card, the thumbnail and at least 2 titles.

The thumbnail is in capitals, but the error keeps its exact letters (`0x80070005` stays lowercase x). Long codes with underscores wrap at the underscores instead of shrinking the text.

**Uploading:** upload the full video first (`video.mp4` with `thumbnail.jpg`), then the Short (`short.mp4`). In YouTube Studio, set the Short's **Related video** to the full video. Links in Shorts descriptions aren't clickable, so the Short tells viewers the links are in the full video.

Each job's files are in `output\<date>_<topic>\`:

| File | What it is |
|---|---|
| `video.mp4` | Full video, 1920×1080 |
| `short.mp4` | Short, 1080×1920 |
| `thumbnail.jpg` | Thumbnail for the full video (1280×720) |
| `cover.jpg` | First frame of the Short, if you want a cover |
| `upload.txt` | Titles, descriptions, tags and pinned comment for both videos |
| `script.json` | The script as you approved it |

## Cost

Scripts use `deepseek-flash` with low thinking, about a quarter of a US cent per link off-peak. The top bar shows your DeepSeek balance. DeepSeek doubles its prices on weekdays from 07:00 to 10:00 and 12:00 to 16:00 Bangladesh time; the top bar warns you during those hours. You can switch to `deepseek-v4-pro` in Settings for better scripts at about 4 times the cost.

## Logos

When a problem is about one brand (Windows, Chrome, iPhone, Samsung, WhatsApp...), the AI picks its logo. It appears on the thumbnail, on the problem cards (with a small red badge showing the problem), and in the full video's side panel. A fix that uses a brand's own tool or site (an Intel driver tool, say) can show that brand's logo too. You can change or remove any logo in review.

About 140 tech brands are bundled in `assets/logos`, from [Simple Icons](https://simpleicons.org) (CC0). Microsoft, Amazon, Adobe and a few others asked Simple Icons to remove their logos, so for those (Windows, Edge, Office, Xbox, Teams and more) the app uses simple outline icons from Tabler Icons instead. Logos are trademarks of their owners and are shown only to identify the product a video is about. To add brands, see `tools/build_logos.py`.

The videos don't use stock photos: free photo services can't reliably leave out people, and text cards with icons and logos already carry these videos.

## Voices

The default is Microsoft Edge's free voices (Andrew, Brian, Ava, Emma and more; pick one and press **Play sample** in Settings). They need internet. They come through the unofficial `edge-tts` library, so Microsoft could change or limit them at any time.

As a backup, install the offline Kokoro voice once: open a terminal in the folder and run `.venv\Scripts\python.exe setup_models.py` (downloads about 350 MB). After that, if Edge ever fails, the app switches to the offline voice by itself, and you can also choose it in Settings.

## Settings

Most settings are in the app. Advanced defaults live in `config.toml`; what you change in the app is saved to `settings.json` and wins over `config.toml`.

| What | Where |
|---|---|
| DeepSeek key, model, thinking level | Settings → DeepSeek |
| Voice and speed | Settings → Voice |
| Thumbnail style (bold, problem/fixed, clean), video colors, channel name | Settings → Look |
| Reddit login, browser (Edge or Chrome) | Settings → Reddit |
| Script length | Settings → Script length |
| Channel voice and accuracy rules for the AI | `prompts\style_guide.md` |
| Script structure | `prompts\script_prompt.md` |
| Other AI providers (Gemini, OpenAI, Groq) | `config.toml`, `[ai]` section |

## Troubleshooting

- **"Reddit wants you to log in"**: Settings → Log in to Reddit. Jobs that failed only because of the login start again automatically.
- **"Couldn't open Edge or Chrome"**: close any window the app opened earlier, or pick the other browser in Settings.
- **"Edge voice didn't answer"**: check your internet. If the offline voice is installed, the app uses it instead.
- **"FFmpeg isn't installed"**: run `winget install Gyan.FFmpeg` in a terminal, then restart the app.
- **The page doesn't open**: another program may be using port 8765. Change `port` under `[app]` in `config.toml`.

## How it works

`app.py` serves the app and runs two background workers (`fixshorts/jobs.py`):

- **Prep worker:** `history.py` skips posts you've used before, `extract.py` reads the Reddit page in the app's own browser, `writer.py` writes the script with DeepSeek, `schema.py` checks it (exact problem words, no Reddit mentions, no AI-sounding phrases, length, structure), and `links.py` rates and tests each link.
- **Video worker:** after you approve, `tts_edge.py` records the voice with exact word timings, `cards.py` and `render.py` draw and encode both videos with FFmpeg (Intel Quick Sync when available), `thumbs.py` makes the thumbnail, and `kit.py` writes the upload details.

Fonts and icons: Poppins (SIL Open Font License) and Tabler Icons (MIT), in `assets/fonts`. Offline voice: Kokoro-82M (Apache 2.0).

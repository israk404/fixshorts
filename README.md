# FixShorts

Turns a PC, phone or tech-fix post from Reddit into a finished YouTube Short (1080×1920, voice-over and word-by-word captions, no music) plus a ready-to-paste upload kit. Everything runs on your Windows PC; the only thing that goes online is the AI call that writes the script.

![Six frames from the sample Short: the problem card, fix cards with menu paths, and the closing question](docs/preview.jpg)

## One-time setup (about 15 minutes)

1. **Python 3.12** from [python.org](https://www.python.org/downloads/windows/). During install, tick **Add python.exe to PATH**.
2. **FFmpeg** (full build, includes Intel Quick Sync). In PowerShell:
   ```
   winget install Gyan.FFmpeg
   ```
   Close and reopen PowerShell afterwards, then check with `ffmpeg -version`.
3. **This project.** Unzip it anywhere (for example `C:\fixshorts`), then in PowerShell:
   ```
   cd C:\fixshorts
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python setup_models.py
   ```
   The last command downloads the voice model (about 350 MB, once).
4. **AI key.** Create a key at [platform.deepseek.com](https://platform.deepseek.com) (API keys) and add a little balance. Copy `.env.example` to `.env` and paste the key after `DEEPSEEK_API_KEY=`. Never commit `.env`; it's already in `.gitignore`.

Every new PowerShell session, run `.venv\Scripts\activate` inside the folder first.

## Test it without a key

```
python run.py all input\sample_post.txt --script input\sample_script.json
```
This skips the AI and renders the included sample script, so you can check the voice, look and speed on your PC. It takes about a minute.

## Daily use

1. **Save a post.** Open a Reddit post, copy the title, the post text and the top comments (with upvote numbers if you can) into a new text file in `input\`, for example `input\wifi-drops.txt`. The format doesn't need to be neat; look at `input\sample_post.txt` for an example.
2. **Write the script.**
   ```
   python run.py write input\wifi-drops.txt
   ```
   It prints the confidence, risk flags and review notes, and creates `output\<date>_<topic>\`.
3. **Review.** Read `script.md` in that folder. To change anything (a headline, a sentence, a fix), edit `script.json` in the same folder and save.
4. **Render.**
   ```
   python run.py render "output\2026-11-08_laptop-wifi-keeps-dropping"
   ```
5. **Upload.** In the folder: `video.mp4` is the Short, `upload.txt` has the titles, description, tags, hashtags and pinned comment to paste into YouTube Studio. `cover.png` is the first frame if you want it as the Shorts cover.

Shortcut: `python run.py all input\wifi-drops.txt` writes and renders in one go, skipping the review stop.

To check the look of a script quickly without rendering: `python run.py preview "output\<folder>"` saves one still per card into `preview\`.

## AI model and cost

Scripts are written by DeepSeek. `deepseek-v4-pro`, the best model, writes each first draft. If the draft breaks a rule (too long, a missing segment), the cheaper `deepseek-flash` fixes it. Every `write` prints the tokens used and an estimated cost, usually around 1 to 2 US cents per script off-peak.

DeepSeek doubles its prices on weekdays from 07:00 to 10:00 and 12:00 to 16:00 Bangladesh time (01:00–04:00 and 06:00–10:00 UTC). The script tells you when you're in that window and when it ends; weekends are always off-peak.

To make your balance last about 4 times longer, set `model = "deepseek-flash"` in `config.toml`.

## Changing things (config.toml)

| What | Setting |
|---|---|
| Voice | `[voice] voice` (try `af_heart`, `am_adam`, `bm_george`) |
| Speaking speed | `[voice] speed` (1.1 default) |
| A word the voice says wrong | add a line under `[pronounce]` |
| Script length | `[script] min_words` / `max_words` |
| Color theme | `[video] theme` (`auto` rotates: cyan, lime, amber, violet) |
| Channel name on screen | `[video] channel_name` |
| Cheaper or stronger AI | `[ai] model` (`deepseek-v4-pro` or `deepseek-flash`) and `reasoning_effort` (`low`, `high`, `max`) |
| Different AI provider | `[ai]` section (Gemini, OpenAI, Groq and OpenRouter examples included) |

The channel's voice and the accuracy rules live in `prompts\style_guide.md`, and the script structure in `prompts\script_prompt.md`. Editing those is the best way to change how the scripts sound.

## How it works

`run.py` → `writer.py` (AI script, checked against the rules in `schema.py`, sent back to the AI up to 3 times if it breaks them) → `voice.py` (Kokoro on your CPU; each sentence is voiced separately so captions stay in sync) → `cards.py` + `render.py` (Pillow draws the cards, FFmpeg encodes one file per card using Quick Sync if available, joins them, adds the voice at YouTube's -14 LUFS loudness) → `kit.py` (upload.txt and script.md).

## Troubleshooting

- **`ffmpeg` is not recognized**: reopen PowerShell after installing, or put the full path to `ffmpeg.exe` in `config.toml` under `[video] ffmpeg`.
- **"Quick Sync isn't available"**: rendering falls back to the CPU automatically. Updating the Intel graphics driver usually enables Quick Sync.
- **Video over 58 seconds**: the voice is sped up by up to 15% automatically. Beyond that you'll get a warning; trim the script in `script.json`.
- **AI errors about `response_format`**: set `json_mode = false` in `config.toml`.
- **"reply was cut off"**: raise `max_tokens` under `[ai]`, or set `reasoning_effort = "low"`.
- **"Insufficient Balance" from DeepSeek**: top up at platform.deepseek.com.

Fonts: Poppins, under the SIL Open Font License (`assets\fonts\OFL.txt`). Voice model: Kokoro-82M (Apache 2.0).

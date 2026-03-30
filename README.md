# py-sharepoint-video-downloader

Python helper to download Microsoft Teams / SharePoint recordings using DASH
`videomanifest` URLs exposed in the browser.

This tool relies on `yt-dlp` and `ffmpeg`.
It does **not** bypass authentication, DRM, or access controls.

---

## What this does

This script downloads Microsoft Teams / SharePoint recordings by directly
consuming the DASH `videomanifest` URL that the web player uses internally.

It works only for videos that:
- You are already authorized to view in your browser
- Are delivered as DASH streams (`videomanifest`)

The script simply automates what the browser already does.

---

## Requirements

- Python **3.10+**
- `uv`
- `ffmpeg` available in `PATH`

### Ubuntu dependencies

Install `ffmpeg` and `curl` first:

```bash
sudo apt update
sudo apt install -y ffmpeg curl ca-certificates
```

`ffmpeg` is required because `yt-dlp` downloads separate DASH audio/video
streams and then merges them into the final MP4 file.

---

## Bootstrap with `uv`

From the project root:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv sync
```

This will create the project environment and install the Python dependencies
from `pyproject.toml`.

---

## How to obtain the videomanifest URL

1. Open the video in **SharePoint or Microsoft Teams (web)**.
2. Open **Chrome DevTools**.
3. Go to the **Network** tab.
4. Filter requests by `videomanifest`.
5. Copy the request URL.
6. Save the full URL into a text file.

> **Important**:
> These URLs are **time-limited**. If the download fails with 403/404 errors,
> reload the page and copy a fresh URL.

The script will automatically shorten the URL so it ends at:

```text
part=index&format=dash
```

---

## Usage

Save the `videomanifest` URL into a text file (for example `videomanifest.txt`).

Then run:

```bash
uv run sp-video-download videomanifest.txt -o output.mp4
```

Or, if you prefer to run the script directly:

```bash
uv run python download.py videomanifest.txt -o output.mp4
```

- `videomanifest.txt` must contain **only the URL**
- The default output container is **MP4**

### Runtime language

User-facing messages are selected from the terminal locale:
- Spanish terminals (`LANG`, `LC_MESSAGES`, or `LC_ALL` starting with `es`) -> Spanish messages
- All other locales -> English messages

English is the default fallback.

---

## Performance limitations (important)

Microsoft applies **aggressive server-side throttling**, especially on
**audio DASH streams**.

Observed behavior:

* Video usually downloads at ~0.8–1.2 MB/s
* Audio can be throttled to **<100 KB/s**
* Increasing fragment concurrency often results in:

  * HTTP 503 errors
  * Read timeouts
  * Worse overall performance

This is a **Microsoft CDN limitation**, not a bug in the script.

---

## Notes on parallelism

The script enables DASH fragment parallelism when supported by the server.
However, Microsoft’s CDN often collapses parallel requests into a single
effective connection for audio streams.

Do not expect linear speedups by increasing concurrency.

---

## Contributions are welcome

Bug reports, improvements, and documentation updates are appreciated.

---

## License

MIT License

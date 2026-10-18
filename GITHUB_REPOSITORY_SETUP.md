# GitHub repository settings

**Suggested repository name:** `chatgpt-media-downloader`

**Description (GitHub About):** Desktop app for downloading authorized video, audio and playlist media, with a Tkinter GUI.

**Website:** `https://slydtaz.github.io/chatgpt-media-downloader/`

**Suggested topics:** `python`, `tkinter`, `media-downloader`, `playlist-manager`, `yt-dlp`, `ffmpeg`, `open-source`

## First publish

Follow [`PUBLISH_TO_GITHUB.md`](PUBLISH_TO_GITHUB.md) to create the empty remote repository and push this source tree.

## After importing this repository

1. Set repository visibility to **Public** if you want public Issues, Pull Requests and Releases.
2. In **Settings → Pages**, choose **GitHub Actions** as the source. The `pages.yml` workflow will deploy `site/index.html` on a push to `main`/`master` when the site changes.
3. Confirm **Settings → Actions → General → Workflow permissions** allows workflows to write releases/pages where requested. The release workflow declares `contents: write`; Pages declares `pages: write` and `id-token: write`.
4. Run the tests workflow and resolve any failures before publishing a version.
5. To publish a Windows build, push the `stable` tag (or a version tag such as `v5.0.3`). The stable-tag workflow tests the source, builds `ChatGPTMediaDownloader.exe`, calculates SHA-256 and attaches both files to the stable GitHub Release.
6. Confirm the release and static website are visible before linking them publicly. The GitHub Releases and Pages URLs referenced in the README assume that this repository is named `slydtaz/chatgpt-media-downloader`.

GitHub has native Issues and Pull Requests. The `.github/ISSUE_TEMPLATE` and `.github/PULL_REQUEST_TEMPLATE.md` files provide standardized forms/checklists; they do not replace the platform's native functionality.

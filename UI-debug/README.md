# UI-debug — Cosmic interface prototype

**Version:** 0.1.0-dev.7  
**Channel:** development  
**Status:** visual prototype — not a production downloader and not a GitHub Release.

UI-debug is a standalone Tkinter application for reviewing the proposed layout before the production UI is changed. It does not import modules from the production \`app/\` directory, does not run FFmpeg, and never downloads media files. When you explicitly request a preview, it can use yt-dlp in metadata-only mode (\`download=False\`) if installed, or YouTube/Vimeo oEmbed for individual links.

## Run

- Windows: double-click \`run_ui_debug.bat\`, or run \`python UI-debug/ui_debug.py\` from the repository root.
- macOS/Linux: run \`sh UI-debug/run_ui_debug.sh\`, or run \`python3 UI-debug/ui_debug.py\`.

Requirements: Python 3.10+ with Tkinter. The UI starts without third-party packages. For broad site and playlist metadata support, install \`yt-dlp\`; for JPEG/WebP thumbnail rendering, install \`Pillow\` too. Run \`python -m pip install yt-dlp Pillow\` to enable both. Without Pillow, the UI still works and shows its designed placeholder when Tk cannot decode a fetched image.

## Prototype scope

Working:
- Page navigation.
- On-demand media preview showing title, channel, duration and a thumbnail when provided by the source.
- Playlist/list preview with thumbnail cards for up to 20 entries when yt-dlp is installed; clicking an entry takes it back to the main preview.
- Thumbnail retrieval is only started by the user, uses size-limited HTTPS image responses, and never fetches media streams.
- Theme selection (dark, light, OLED), custom accent colors, gradient presets, density and motion preferences.
- Saving its own settings in a dedicated \`MediaDownloader-UI-debug\` user-data directory.
- Checking and installing updates from the \`ui-debug\` development branch, after explicit confirmation.

Mocked:
- Media downloads, dependency installation, app repair and real diagnostics. Previewing metadata does not download the video/audio.

The updater reads \`UI-debug/version.json\` from the dedicated development branch. It does not use the production app version or GitHub Releases. It downloads the branch source archive only when the user accepts a newer version; it validates the archive and replaces only files belonging to the UI-debug app. Preferences are stored outside this folder and are preserved.

## Visual direction

The Media Lab symbol is larger; navigation icons are rendered from 4× supersampled images with Lanczos downsampling when Pillow is installed, with larger round-capped vector strokes as a fallback. The Home page has an on-demand media poster preview, and each playlist row has its own thumbnail card. The layout keeps the current project's main sections (Home, Playlists, Appearance, Dependencies, Updates, Help and Diagnostics) and adopts the public OrionMacro dashboard's broader visual direction: near-black violet surfaces, neon-violet active cards, cyan/green status accents, a compact activity waveform and clearer selected navigation. UI assets and code were drawn for this prototype rather than copied. The startup loader uses each orbit as a smooth reusable vector path and reuses a small number of multi-point trail items, avoiding the old stack of independent trail segments. The app opens using the monitor's available work area and adaptively scales typography, controls and outlines (up to 125% on 2560×1440 displays), with a more conservative floor for smaller displays.

The two \`share.google\` reference links could not be resolved by the browsing environment, so the layout uses the current app's organization and public SKlauncher 4.0 documentation as general layout inspiration.

## Development checks

From the repository root:

\`\`\`sh
python -m unittest discover -s UI-debug/tests -v
python -m py_compile UI-debug/ui_debug.py
\`\`\`

This directory is self-contained; no production project files are required at runtime. The branch exists for review and does not create or publish a GitHub Release.

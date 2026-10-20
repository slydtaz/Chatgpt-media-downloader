# UI-debug — Cosmic interface prototype

**Version:** 0.1.0-dev.9  
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

The Media Lab symbol is larger; navigation uses simple, smooth outline icons with 4× supersampling when Pillow is present and a vector fallback otherwise. Primary actions now have small native Tk icons for preview, download, conversion, save and refresh, so icon rendering does not require another package. The Home page has an on-demand media preview and the playlist view has thumbnail cards. The interface uses near-black violet surfaces, restrained violet-to-periwinkle/blue gradients, a soft halo around primary buttons, and clearer selected navigation. Saturated pink is reduced; cyan is a supporting accent rather than the dominant endpoint. UI assets are original to this prototype rather than copied. The startup loader keeps its rotating atom and orbital motion; only the background gradient, orbit trails, stars, and nucleus glow are slightly more luminous. App typography, controls, and outlines continue to scale to the display.

The two \`share.google\` reference links could not be resolved by the browsing environment, so the layout uses the current app's organization and public SKlauncher 4.0 documentation as general layout inspiration.

## Development checks

From the repository root:

\`\`\`sh
python -m unittest discover -s UI-debug/tests -v
python -m py_compile UI-debug/ui_debug.py
\`\`\`

This directory is self-contained; no production project files are required at runtime. The branch exists for review and does not create or publish a GitHub Release.

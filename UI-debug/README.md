# UI-debug — Cosmic interface prototype

**Version:** 0.1.0-dev.2  
**Channel:** development  
**Status:** visual prototype — not a production downloader and not a GitHub Release.

UI-debug is a standalone Tkinter application for reviewing the proposed layout before the production UI is changed. It does not import modules from the production \`app/\` directory, does not run yt-dlp or FFmpeg, and never downloads media.

## Run

- Windows: double-click \`run_ui_debug.bat\`, or run \`python UI-debug/ui_debug.py\` from the repository root.
- macOS/Linux: run \`sh UI-debug/run_ui_debug.sh\`, or run \`python3 UI-debug/ui_debug.py\`.

Requirements: Python 3.10+ with Tkinter. No third-party Python packages are required.

## Prototype scope

Working:
- Page navigation.
- Theme selection (dark, light, OLED), custom accent colors, gradient presets, density and motion preferences.
- Saving its own settings in a dedicated \`MediaDownloader-UI-debug\` user-data directory.
- Checking and installing updates from the \`ui-debug\` development branch, after explicit confirmation.

Mocked:
- Media downloads, playlist processing, dependency installation, app repair and real diagnostics.

The updater reads \`UI-debug/version.json\` from the dedicated development branch. It does not use the production app version or GitHub Releases. It downloads the branch source archive only when the user accepts a newer version; it validates the archive and replaces only files belonging to the UI-debug app. Preferences are stored outside this folder and are preserved.

## Visual direction

The layout keeps the current project's main sections (Home, Playlists, Appearance, Dependencies, Updates, Help and Diagnostics) while experimenting with a compact space-inspired palette, cleaner rounded cards, restrained gradients and no full-window slide/fade transitions. Decorative animated icon candidates are intentionally not embedded yet; they will be added only after visual approval.

The two \`share.google\` reference links could not be resolved by the browsing environment, so the first pass uses the current app's organization and public SKlauncher 4.0 documentation as general layout inspiration. An uploaded image or direct image URL can help align the next iteration more closely.

## Development checks

From the repository root:

\`\`\`sh
python -m unittest discover -s UI-debug/tests -v
python -m py_compile UI-debug/ui_debug.py
\`\`\`

This directory is self-contained; no production project files are required at runtime. The branch exists for review and does not create or publish a GitHub Release.

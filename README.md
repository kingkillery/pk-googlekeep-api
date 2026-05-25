# Keep Notes Exporter

Two tools for exporting Google Keep notes directly to your local vault:

1. **Keep Live Extractor** (recommended) — A local Python script that opens a visible Chrome window with a "Save to Vault" button. Has full filesystem access, no Chrome sandbox limitations.
2. **Chrome Extension** — A lightweight extension that downloads notes as a ZIP file (for when you can't run Python).

---

## Option 1: Keep Live Extractor (Recommended)

This is the "Obsidian plugin style" approach — a local script with full filesystem access that controls a visible browser window.

### How to use

1. Double-click `Run-Keep-Extractor.bat` (or run `python keep_live_extractor.py`)
2. A Chrome window opens to [keep.google.com](https://keep.google.com)
3. Log in if needed
4. A blue **"💾 Save to Vault"** button appears in the top-right of the page
5. Navigate to Main, Archive, or Trash
6. Click the button — notes save directly to this folder as `.md` files
7. Close Chrome when done

### Features

- **Direct filesystem save** — No ZIP, no download dialog, no server needed
- **Section aware** — Archive notes prefixed `archive_`; Trash notes prefixed `trash_`
- **Matching format** — YAML frontmatter matches your Obsidian vault (`title`, `source`, `source_section`, `color`, `pinned`, `archived`, `labels`, `is_list`)
- **On-demand** — Click the button whenever you want, as many times as you want
- **Auto-reinjects** — Button stays visible when navigating between sections

---

## Option 2: Chrome Extension

A lightweight Manifest V3 extension for environments where you can't run Python.

### Install (unpacked)

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select this folder: `keep-extension`
5. The extension icon appears in your toolbar

### How to use

1. Go to [keep.google.com](https://keep.google.com)
2. Navigate to the view you want to export
3. Click the **Keep Exporter** extension icon
4. Click **Extract Notes**
5. Click **Download as ZIP**
6. Choose where to save the `.zip` file

---

## Notes

- Both tools read notes from the **currently visible page only**. Scroll down to load more notes before extracting.
- Checklists are preserved with `[x]` / `[ ]` syntax.
- Label extraction is best-effort based on visible chips.

## Files

| File | Purpose |
|------|---------|
| `keep_live_extractor.py` | Local Python script with visible Chrome + direct filesystem save |
| `Run-Keep-Extractor.bat` | Double-click launcher for the Python script |
| `manifest.json` | Chrome Extension V3 manifest |
| `content.js` | Content script that scrapes note cards from Keep's DOM |
| `popup.html/js/css` | Extension popup UI |
| `jszip.min.js` | JSZip library for creating ZIPs (extension only) |

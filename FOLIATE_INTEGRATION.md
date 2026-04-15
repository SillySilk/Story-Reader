# Foliate-js Integration Guide

This document explains the Foliate-js integration for Story Reader, which adds multi-format support and automatic zoom reflow.

## Overview

Story Reader now supports **two rendering modes**:

1. **Legacy Mode** (default): Character-based pagination for DOCX files
2. **Foliate Mode**: Professional EPUB rendering with multi-format support

## Feature Comparison

| Feature | Legacy Mode | Foliate Mode |
|---------|-------------|--------------|
| **Formats Supported** | DOCX only | DOCX, TXT, MD, PDF, HTML, ODT, RTF, EPUB (+30 more) |
| **Zoom Behavior** | ❌ Breaks pagination | ✅ Auto-reflows content |
| **Bookmark System** | Page numbers | CFI (precise locations) |
| **Rendering Engine** | Mammoth + Custom JS | Foliate-js (industry standard) |
| **Conversion** | Direct HTML | DOCX → EPUB (cached) |
| **Performance** | Instant load | ~1-3 sec first load, instant after (cache) |

## Enabling Foliate Mode

### Option 1: Manual Config Edit

Edit `~/.story_reader_config.json`:

```json
{
  "use_foliate": true
}
```

### Option 2: Python Script

```python
from utils import load_config, save_config

config = load_config()
config['use_foliate'] = True
save_config(config)
```

Then restart the app.

## How It Works

### Conversion Pipeline

```
User opens file → Format detected → Convert to EPUB (Pandoc) → Cache → Render with Foliate-js
                                           ↓
                                    Cache hit? → Skip conversion
```

**Caching**:
- EPUBs cached in `~/.story_reader_cache/`
- Cache key: `SHA256(file_path + modification_time)`
- Subsequent opens are instant
- Auto-cleanup: Removes entries older than 30 days

### Bookmark System

**Legacy Mode** (page-based):
```json
{
  "path": "story.docx",
  "page_num": 42,
  "type": "page"
}
```

**Foliate Mode** (CFI-based):
```json
{
  "path": "story.docx",
  "epub_path": "~/.story_reader_cache/abc123.epub",
  "cfi": "epubcfi(/6/14!/4/2/10,/1:0,/1:15)",
  "progress": 0.42,
  "type": "cfi"
}
```

## Migrating Bookmarks

If you have existing page-based bookmarks and want to use Foliate mode:

### Method 1: GUI (Recommended)

1. Options → Migrate Bookmarks to CFI
2. Confirm migration
3. Restart app

### Method 2: Command Line

```bash
python migrate_bookmarks.py
```

**Important Notes**:
- Migration creates a backup: `~/.story_reader_bookmarks.json.backup`
- Migrated positions are **approximate** (based on page fractions)
- For exact positions, re-bookmark each file in Foliate mode

## Supported File Formats

When `use_foliate: true`:

### Documents
- Microsoft Word: `.docx`, `.doc`
- OpenDocument: `.odt`
- Rich Text: `.rtf`
- PDF: `.pdf` (via pdftotext, best-effort)

### Text Formats
- Plain Text: `.txt`
- Markdown: `.md`, `.markdown`
- HTML: `.html`, `.htm`

### E-books
- EPUB: `.epub` (pass-through, no conversion)

And 30+ more formats supported by Pandoc!

## Cache Management

### View Cache Stats

Options → Clear EPUB Cache → Shows current cache size

### Clear Cache

Options → Clear EPUB Cache → Confirm

Files will be reconverted on next open.

### Manual Cache Cleanup

```bash
rm -rf ~/.story_reader_cache/
```

## Troubleshooting

### "Conversion Failed"

**Problem**: Pandoc conversion error
**Solution**:
- Check file is valid and not corrupted
- Verify format is supported: `python -m format_detector file.docx`
- Try re-saving file in original application

### "Unable to get current location"

**Problem**: Tried to bookmark before Foliate-js fully loaded
**Solution**: Wait 1-2 seconds after page loads, then bookmark

### Zoom doesn't reflow content

**Problem**: Still in legacy mode
**Solution**: Enable Foliate mode in config (see above)

### Bookmarks don't work after migration

**Problem**: CFI positions are approximate
**Solution**: Re-bookmark files in Foliate mode for exact positions

### Files take long to open

**Problem**: First-time conversion
**Solution**:
- Normal! Conversion takes 1-3 seconds
- Subsequent opens are instant (cache hit)
- Large PDFs may take longer (~10-30 seconds)

## Configuration Reference

All config keys in `~/.story_reader_config.json`:

```json
{
  // Feature flag
  "use_foliate": false,  // Enable Foliate-js renderer

  // Cache settings
  "cache_dir": "~/.story_reader_cache",
  "cache_max_age_days": 30,
  "cache_max_size_mb": 500,

  // Conversion settings
  "conversion_timeout_sec": 300,
  "preferred_converter": "pandoc",  // "pandoc" or "mammoth"
  "show_conversion_progress": true,

  // ... other settings ...
}
```

## Architecture

### File Structure

```
Story reader/
├── conversion_engine.py      # Format → EPUB conversion
├── epub_cache.py              # Cache management
├── format_detector.py         # File format detection
├── foliate_integration.py     # Foliate-js wrapper
├── migrate_bookmarks.py       # Bookmark migration tool
├── reader_window.py           # Main app (dual-renderer)
├── assets/
│   └── foliate-js/           # Foliate-js library
└── ~/.story_reader_cache/    # Cached EPUBs (user home)
```

### Key Components

**ConversionEngine** (`conversion_engine.py`):
- Converts 40+ formats to EPUB using Pandoc
- Falls back to Mammoth for DOCX if Pandoc unavailable
- Progress callbacks for UI updates

**EPUBCache** (`epub_cache.py`):
- SHA256-based content caching
- Automatic cleanup (age + size limits)
- Cache hit detection via file modification time

**FoliateRenderer** (`foliate_integration.py`):
- QWebEngineView wrapper
- Python↔JavaScript bridge (QWebChannel)
- CFI navigation API

**Dual Renderer** (`reader_window.py`):
- Feature flag: `use_foliate`
- Transparent switching between modes
- Bookmark compatibility layer

## Performance Tips

1. **First opens are slow**: Files convert once, then cache
2. **Keep cache under limit**: Default 500MB, adjust in config
3. **PDF caveat**: Large PDFs take longer (pdftotext conversion)
4. **Clear cache periodically**: Options → Clear EPUB Cache

## Reverting to Legacy Mode

1. Edit config: `"use_foliate": false`
2. Restart app
3. Bookmarks remain compatible (both types supported)

## Developer Notes

### Adding Format Support

Pandoc supports it? You're done! Format detection handles extensions automatically.

Custom format? Implement in `conversion_engine.py`:

```python
# Add to SUPPORTED_FORMATS
SUPPORTED_FORMATS = {
    '.your_ext': 'pandoc_format_name'
}
```

### Extending CFI Bookmarks

CFI format in `foliate_integration.py`:

```python
class CFIBookmark:
    def __init__(self, epub_path, cfi, ...):
        self.epub_path = epub_path
        self.cfi = cfi  # epubcfi(/6/14!/4...)
        ...
```

## FAQ

**Q: Can I use both modes for different files?**
A: No, it's a global setting. Switch via config.

**Q: Will old bookmarks work in Foliate mode?**
A: Use the migration tool (Options → Migrate Bookmarks)

**Q: What happens if I change a file after caching?**
A: Cache invalidates automatically (SHA256 includes mtime)

**Q: Can I use Foliate mode offline?**
A: Yes! Pandoc and Foliate-js work offline. Google Fonts in CSS won't load, but content renders fine.

**Q: Does this replace the old pagination?**
A: No! Legacy mode still works. Foliate mode is opt-in.

## Credits

- **Foliate-js**: https://github.com/johnfactotum/foliate-js
- **Pandoc**: https://pandoc.org/
- **pypandoc**: https://github.com/NicklasTegner/pypandoc
- **ebooklib**: https://github.com/aerkalov/ebooklib

## License

Foliate-js integration follows the Story Reader license. Foliate-js itself is MIT licensed.

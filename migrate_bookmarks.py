"""
Bookmark Migration Script

Migrates legacy page-based bookmarks to CFI (Canonical Fragment Identifier) format
for use with Foliate-js renderer.

NOTE: This is a best-effort migration. CFI locations are estimated based on page
numbers, and may not be perfectly accurate. The original bookmarks are preserved
in a backup file.

Usage:
    python migrate_bookmarks.py
"""

import os
import json
import shutil
from pathlib import Path

from utils import BOOKMARKS_FILE, load_json, save_json
from conversion_engine import ConversionEngine
from epub_cache import EPUBCache
from format_detector import FormatDetector


def estimate_cfi_from_page(page_num, total_pages):
    """
    Estimate a CFI location from a page number.

    This is a simplified estimation. Real CFI would require parsing the EPUB
    and finding the exact location, but for migration we use a fractional approach.

    Args:
        page_num: Page number (1-indexed)
        total_pages: Total number of pages

    Returns:
        Estimated fraction (0.0 - 1.0)
    """
    if total_pages <= 0:
        return 0.0

    # Convert to 0-indexed, then get fraction
    fraction = (page_num - 1) / max(total_pages, 1)

    # Clamp to valid range
    return max(0.0, min(1.0, fraction))


def migrate_bookmarks(dry_run=False):
    """
    Migrate legacy bookmarks to CFI format.

    Args:
        dry_run: If True, don't save changes, just show what would happen

    Returns:
        Number of bookmarks migrated
    """
    # Load bookmarks
    if not os.path.exists(BOOKMARKS_FILE):
        print("No bookmarks file found.")
        return 0

    bookmarks = load_json(BOOKMARKS_FILE, default=[])

    if not bookmarks:
        print("No bookmarks to migrate.")
        return 0

    print(f"Found {len(bookmarks)} bookmarks")
    print()

    # Initialize conversion infrastructure
    conversion_engine = ConversionEngine()
    epub_cache = EPUBCache()

    migrated_count = 0
    migrated_bookmarks = []

    for i, bookmark in enumerate(bookmarks):
        print(f"\n[{i+1}/{len(bookmarks)}] Processing bookmark...")

        # Check if already CFI format
        if bookmark.get('type') == 'cfi':
            print(f"  ✓ Already in CFI format: {os.path.basename(bookmark['path'])}")
            migrated_bookmarks.append(bookmark)
            continue

        # Legacy page-based bookmark
        file_path = bookmark.get('path')
        page_num = bookmark.get('page_num', 1)

        if not file_path or not os.path.exists(file_path):
            print(f"  ⚠ File not found: {file_path}")
            print(f"    Preserving bookmark as-is")
            migrated_bookmarks.append(bookmark)
            continue

        print(f"  File: {os.path.basename(file_path)}")
        print(f"  Page: {page_num}")

        # Check if format is supported
        if not FormatDetector.is_supported(file_path):
            print(f"  ⚠ Unsupported format, preserving as-is")
            migrated_bookmarks.append(bookmark)
            continue

        try:
            # Convert to EPUB (or get from cache)
            print(f"  Converting to EPUB...")

            cached_epub = epub_cache.get_cached_epub(file_path)

            if not cached_epub:
                # Need to convert
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.epub', delete=False) as tmp:
                    temp_epub = tmp.name

                metadata = conversion_engine.extract_metadata(file_path)

                success = conversion_engine.convert_to_epub(
                    file_path,
                    temp_epub,
                    metadata=metadata,
                    progress_callback=lambda p, m: None  # Silent
                )

                if not success:
                    print(f"  ⚠ Conversion failed, preserving as-is")
                    if os.path.exists(temp_epub):
                        os.remove(temp_epub)
                    migrated_bookmarks.append(bookmark)
                    continue

                # Cache it
                cached_epub = epub_cache.add_to_cache(file_path, temp_epub)

                # Clean up
                if os.path.exists(temp_epub):
                    os.remove(temp_epub)

            print(f"  ✓ EPUB: {os.path.basename(cached_epub)}")

            # Estimate CFI from page number
            # NOTE: This is a rough estimate. We don't have total page count from
            # the old bookmark, so we'll use a placeholder CFI and just store progress

            # For migration, use fractional progress (assume ~30 pages per DOCX)
            estimated_total_pages = 30  # Rough estimate for average DOCX
            progress = estimate_cfi_from_page(page_num, estimated_total_pages)

            # Create migrated bookmark
            migrated_bookmark = {
                "path": file_path,
                "epub_path": cached_epub,
                "cfi": None,  # CFI will be set when user navigates with Foliate
                "progress": progress,
                "display_text": f"~Page {page_num} (migrated, approximate)",
                "type": "cfi",
                "migrated_from_page": page_num  # Keep original for reference
            }

            migrated_bookmarks.append(migrated_bookmark)
            migrated_count += 1

            print(f"  ✓ Migrated to CFI format (progress: {progress:.1%})")

        except Exception as e:
            print(f"  ⚠ Error during migration: {e}")
            print(f"    Preserving bookmark as-is")
            migrated_bookmarks.append(bookmark)

    print()
    print("="*80)
    print(f"Migration Summary:")
    print(f"  Total bookmarks: {len(bookmarks)}")
    print(f"  Migrated: {migrated_count}")
    print(f"  Preserved as-is: {len(bookmarks) - migrated_count}")
    print("="*80)

    if dry_run:
        print("\n[DRY RUN] No changes saved.")
        return migrated_count

    # Backup original bookmarks
    if not dry_run and migrated_count > 0:
        backup_path = BOOKMARKS_FILE + ".backup"
        shutil.copy2(BOOKMARKS_FILE, backup_path)
        print(f"\n✓ Original bookmarks backed up to: {backup_path}")

        # Save migrated bookmarks
        save_json(BOOKMARKS_FILE, migrated_bookmarks)
        print(f"✓ Migrated bookmarks saved to: {BOOKMARKS_FILE}")

        print("\nIMPORTANT NOTES:")
        print("- Migrated bookmark positions are APPROXIMATE")
        print("- To get exact positions, re-bookmark each document in Foliate mode")
        print("- Original bookmarks preserved in .backup file")

    return migrated_count


def main():
    """Run migration"""
    import sys

    print("="*80)
    print("BOOKMARK MIGRATION TOOL")
    print("="*80)
    print()
    print("This tool migrates legacy page-based bookmarks to CFI format.")
    print("Page positions are estimated and may not be perfectly accurate.")
    print()
    print("Options:")
    print("  1. Dry run (preview changes)")
    print("  2. Migrate (backup original and save changes)")
    print("  3. Cancel")
    print()

    choice = input("Enter choice (1-3): ").strip()

    if choice == "1":
        print("\nRunning dry run...")
        migrate_bookmarks(dry_run=True)

    elif choice == "2":
        print("\nMigrating bookmarks...")

        confirm = input("Create backup and migrate? (yes/no): ").strip().lower()

        if confirm == "yes":
            migrated = migrate_bookmarks(dry_run=False)

            if migrated > 0:
                print("\n✓ Migration complete!")
            else:
                print("\nNo bookmarks needed migration.")
        else:
            print("\nMigration cancelled.")

    else:
        print("\nCancelled.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

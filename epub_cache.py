"""
EPUB Cache Management System

This module manages a cache of converted EPUB files to avoid reconverting
the same document multiple times. Cache entries are keyed by SHA256 hash
of (file_path + modification_time) to detect file changes.

Cache structure:
~/.story_reader_cache/
    <hash1>.epub
    <hash2>.epub
    cache_index.json  # Metadata about cached files
"""

import os
import json
import hashlib
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EPUBCache:
    """
    Manages caching of converted EPUB files.

    Cache entries are stored in ~/.story_reader_cache/ with SHA256 hash filenames.
    Automatically cleans up old entries (default: 30 days).
    """

    def __init__(self,
                 cache_dir: Optional[str] = None,
                 max_age_days: int = 30,
                 max_size_mb: int = 500):
        """
        Initialize the EPUB cache manager.

        Args:
            cache_dir: Directory for cache storage (default: ~/.story_reader_cache)
            max_age_days: Maximum age for cache entries before cleanup
            max_size_mb: Maximum total cache size in megabytes
        """
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb
        self.index_file = os.path.join(self.cache_dir, 'cache_index.json')

        # Ensure cache directory exists
        self._ensure_cache_dir()

        # Load index
        self.index = self._load_index()

    def _get_default_cache_dir(self) -> str:
        """Get the default cache directory path"""
        home = Path.home()
        return str(home / '.story_reader_cache')

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist"""
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"Cache directory: {self.cache_dir}")

    def _load_index(self) -> Dict:
        """Load the cache index from disk"""
        if not os.path.exists(self.index_file):
            return {}

        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache index: {e}")
            return {}

    def _save_index(self):
        """Save the cache index to disk"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")

    def _generate_cache_key(self, file_path: str) -> str:
        """
        Generate a unique cache key for a file.

        Key is SHA256(file_path + modification_time) to detect file changes.

        Args:
            file_path: Path to the original file

        Returns:
            SHA256 hash string
        """
        abs_path = os.path.abspath(file_path)

        # Get file modification time
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            # File doesn't exist
            mtime = 0

        # Create hash from path + mtime
        key_string = f"{abs_path}:{mtime}"
        hash_obj = hashlib.sha256(key_string.encode('utf-8'))
        return hash_obj.hexdigest()

    def get_cached_epub(self, source_file: str) -> Optional[str]:
        """
        Get cached EPUB path if it exists and is valid.

        Args:
            source_file: Path to the original document

        Returns:
            Path to cached EPUB file, or None if not cached/invalid
        """
        if not os.path.exists(source_file):
            return None

        # Generate cache key
        cache_key = self._generate_cache_key(source_file)

        # Check if we have this in the index
        if cache_key not in self.index:
            logger.debug(f"Cache miss: {source_file}")
            return None

        # Get cache entry
        entry = self.index[cache_key]
        cached_epub_path = entry.get('epub_path')

        # Verify cached file exists
        if not cached_epub_path or not os.path.exists(cached_epub_path):
            logger.warning(f"Cached file missing, removing from index: {cache_key}")
            del self.index[cache_key]
            self._save_index()
            return None

        # Check if cache entry is too old
        created_time = entry.get('created', 0)
        age_days = (time.time() - created_time) / (24 * 3600)

        if age_days > self.max_age_days:
            logger.info(f"Cache entry expired ({age_days:.1f} days old): {source_file}")
            self.remove_from_cache(source_file)
            return None

        logger.info(f"Cache hit: {source_file}")
        return cached_epub_path

    def add_to_cache(self,
                     source_file: str,
                     epub_file: str) -> str:
        """
        Add a converted EPUB to the cache.

        Args:
            source_file: Path to the original document
            epub_file: Path to the converted EPUB file

        Returns:
            Path to the cached EPUB file
        """
        # Generate cache key
        cache_key = self._generate_cache_key(source_file)

        # Generate cached filename
        cached_filename = f"{cache_key}.epub"
        cached_path = os.path.join(self.cache_dir, cached_filename)

        try:
            # Copy EPUB to cache
            shutil.copy2(epub_file, cached_path)

            # Update index
            self.index[cache_key] = {
                'source_file': os.path.abspath(source_file),
                'epub_path': cached_path,
                'created': time.time(),
                'size_bytes': os.path.getsize(cached_path)
            }

            self._save_index()

            logger.info(f"Added to cache: {source_file} -> {cached_filename}")
            return cached_path

        except Exception as e:
            logger.error(f"Failed to add to cache: {e}")
            return epub_file

    def remove_from_cache(self, source_file: str) -> bool:
        """
        Remove a file from the cache.

        Args:
            source_file: Path to the original document

        Returns:
            True if removed, False if not found
        """
        cache_key = self._generate_cache_key(source_file)

        if cache_key not in self.index:
            return False

        # Get entry
        entry = self.index[cache_key]
        cached_path = entry.get('epub_path')

        # Delete cached file
        if cached_path and os.path.exists(cached_path):
            try:
                os.remove(cached_path)
                logger.info(f"Deleted cached file: {cached_path}")
            except Exception as e:
                logger.warning(f"Failed to delete cached file: {e}")

        # Remove from index
        del self.index[cache_key]
        self._save_index()

        return True

    def cleanup_old_entries(self) -> int:
        """
        Remove cache entries older than max_age_days.

        Returns:
            Number of entries removed
        """
        now = time.time()
        max_age_seconds = self.max_age_days * 24 * 3600
        removed_count = 0

        # Collect keys to remove (can't modify dict during iteration)
        keys_to_remove = []

        for cache_key, entry in self.index.items():
            created = entry.get('created', 0)
            age = now - created

            if age > max_age_seconds:
                keys_to_remove.append(cache_key)

        # Remove old entries
        for cache_key in keys_to_remove:
            entry = self.index[cache_key]
            cached_path = entry.get('epub_path')

            # Delete file
            if cached_path and os.path.exists(cached_path):
                try:
                    os.remove(cached_path)
                    logger.info(f"Removed old cache entry: {cached_path}")
                    removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove old entry: {e}")

            # Remove from index
            del self.index[cache_key]

        if removed_count > 0:
            self._save_index()
            logger.info(f"Cleaned up {removed_count} old cache entries")

        return removed_count

    def cleanup_by_size(self) -> int:
        """
        Remove oldest entries if cache exceeds max_size_mb.

        Returns:
            Number of entries removed
        """
        # Calculate total cache size
        total_size_bytes = sum(
            entry.get('size_bytes', 0)
            for entry in self.index.values()
        )

        max_size_bytes = self.max_size_mb * 1024 * 1024

        if total_size_bytes <= max_size_bytes:
            return 0

        # Sort entries by creation time (oldest first)
        sorted_entries = sorted(
            self.index.items(),
            key=lambda x: x[1].get('created', 0)
        )

        removed_count = 0

        # Remove oldest entries until under limit
        for cache_key, entry in sorted_entries:
            if total_size_bytes <= max_size_bytes:
                break

            cached_path = entry.get('epub_path')
            size_bytes = entry.get('size_bytes', 0)

            # Delete file
            if cached_path and os.path.exists(cached_path):
                try:
                    os.remove(cached_path)
                    total_size_bytes -= size_bytes
                    removed_count += 1
                    logger.info(f"Removed cache entry to reduce size: {cached_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove entry: {e}")

            # Remove from index
            del self.index[cache_key]

        if removed_count > 0:
            self._save_index()
            logger.info(f"Removed {removed_count} entries to reduce cache size")

        return removed_count

    def clear_cache(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries removed
        """
        removed_count = 0

        for cache_key, entry in list(self.index.items()):
            cached_path = entry.get('epub_path')

            if cached_path and os.path.exists(cached_path):
                try:
                    os.remove(cached_path)
                    removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove cache entry: {e}")

        self.index.clear()
        self._save_index()

        logger.info(f"Cleared cache: {removed_count} entries removed")
        return removed_count

    def get_cache_stats(self) -> Dict:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        total_size = sum(
            entry.get('size_bytes', 0)
            for entry in self.index.values()
        )

        return {
            'entry_count': len(self.index),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'cache_dir': self.cache_dir,
            'max_age_days': self.max_age_days,
            'max_size_mb': self.max_size_mb
        }

    def print_cache_stats(self):
        """Print cache statistics to console"""
        stats = self.get_cache_stats()

        print("=== EPUB Cache Statistics ===")
        print(f"Cache directory: {stats['cache_dir']}")
        print(f"Total entries: {stats['entry_count']}")
        print(f"Total size: {stats['total_size_mb']:.2f} MB")
        print(f"Max age: {stats['max_age_days']} days")
        print(f"Max size: {stats['max_size_mb']} MB")

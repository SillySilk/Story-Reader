"""
Document Format Detection

This module provides utilities for detecting document formats based on
file extensions and magic numbers (file signatures).

Supports detection for:
- DOCX, DOC (Microsoft Word)
- TXT (Plain text)
- MD, Markdown (Markdown files)
- PDF (Portable Document Format)
- HTML, HTM (Web pages)
- ODT (OpenDocument Text)
- RTF (Rich Text Format)
- EPUB (Electronic Publication)
"""

import os
from pathlib import Path
from typing import Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormatDetector:
    """
    Detects document formats using file extensions and magic numbers.
    """

    # File magic numbers (signatures) for format detection
    MAGIC_NUMBERS = {
        # ZIP-based formats (DOCX, ODT, EPUB)
        b'PK\x03\x04': 'zip-based',  # Will need further inspection

        # PDF
        b'%PDF': 'pdf',

        # RTF
        b'{\\rtf': 'rtf',

        # Old DOC format
        b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': 'doc',
    }

    # Format categories
    SUPPORTED_EXTENSIONS = {
        # Word processing
        '.docx': 'Word Document (DOCX)',
        '.doc': 'Word Document (DOC)',

        # Plain text
        '.txt': 'Plain Text',
        '.md': 'Markdown',
        '.markdown': 'Markdown',

        # Web
        '.html': 'HTML Document',
        '.htm': 'HTML Document',

        # Other formats
        '.odt': 'OpenDocument Text',
        '.rtf': 'Rich Text Format',
        '.pdf': 'PDF Document',

        # E-books
        '.epub': 'EPUB E-book',
    }

    @staticmethod
    def get_format_from_extension(file_path: str) -> Optional[str]:
        """
        Get format type from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Format name or None if not recognized
        """
        ext = Path(file_path).suffix.lower()
        return FormatDetector.SUPPORTED_EXTENSIONS.get(ext)

    @staticmethod
    def detect_zip_based_format(file_path: str) -> Optional[str]:
        """
        Detect specific format for ZIP-based files (DOCX, ODT, EPUB).

        These formats are all ZIP archives with different internal structures.

        Args:
            file_path: Path to the file

        Returns:
            'docx', 'odt', 'epub', or None
        """
        try:
            import zipfile

            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                namelist = zip_ref.namelist()

                # DOCX: Contains word/document.xml
                if any('word/document.xml' in name for name in namelist):
                    return 'docx'

                # ODT: Contains content.xml and mimetype
                if 'content.xml' in namelist and 'mimetype' in namelist:
                    try:
                        mimetype = zip_ref.read('mimetype').decode('utf-8').strip()
                        if 'opendocument.text' in mimetype:
                            return 'odt'
                    except:
                        pass

                # EPUB: Contains META-INF/container.xml
                if 'META-INF/container.xml' in namelist:
                    return 'epub'

        except Exception as e:
            logger.debug(f"Error inspecting ZIP file: {e}")

        return None

    @staticmethod
    def detect_format(file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect the format of a document file.

        Uses both magic numbers and file extensions for detection.

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (format_key, format_description)
            Example: ('docx', 'Word Document (DOCX)')
        """
        if not os.path.exists(file_path):
            return (None, None)

        # First, try magic number detection
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)  # Read first 8 bytes

                # Check for known magic numbers
                for magic, format_type in FormatDetector.MAGIC_NUMBERS.items():
                    if header.startswith(magic):
                        if format_type == 'zip-based':
                            # Need to inspect ZIP contents
                            specific_format = FormatDetector.detect_zip_based_format(file_path)
                            if specific_format:
                                ext = f'.{specific_format}'
                                desc = FormatDetector.SUPPORTED_EXTENSIONS.get(ext)
                                return (specific_format, desc)
                        else:
                            ext = f'.{format_type}'
                            desc = FormatDetector.SUPPORTED_EXTENSIONS.get(ext)
                            return (format_type, desc)

        except Exception as e:
            logger.debug(f"Error reading file magic number: {e}")

        # Fall back to extension-based detection
        ext = Path(file_path).suffix.lower()
        desc = FormatDetector.SUPPORTED_EXTENSIONS.get(ext)

        if desc:
            format_key = ext[1:]  # Remove leading dot
            return (format_key, desc)

        return (None, None)

    @staticmethod
    def is_supported(file_path: str) -> bool:
        """
        Check if a file format is supported.

        Args:
            file_path: Path to the file

        Returns:
            True if format is supported, False otherwise
        """
        format_key, _ = FormatDetector.detect_format(file_path)
        return format_key is not None

    @staticmethod
    def get_supported_extensions() -> list:
        """
        Get list of all supported file extensions.

        Returns:
            List of supported extensions (e.g., ['.docx', '.txt', ...])
        """
        return list(FormatDetector.SUPPORTED_EXTENSIONS.keys())

    @staticmethod
    def get_file_filter_string() -> str:
        """
        Get a file filter string for QFileDialog.

        Returns:
            File filter string (e.g., "Documents (*.docx *.txt *.pdf)")
        """
        extensions = FormatDetector.get_supported_extensions()
        ext_list = ' '.join(f'*{ext}' for ext in extensions)
        return f"Supported Documents ({ext_list})"

    @staticmethod
    def is_text_based(file_path: str) -> bool:
        """
        Check if a format is primarily text-based.

        Args:
            file_path: Path to the file

        Returns:
            True if format is text-based (TXT, MD, HTML)
        """
        ext = Path(file_path).suffix.lower()
        return ext in ['.txt', '.md', '.markdown', '.html', '.htm']

    @staticmethod
    def requires_conversion(file_path: str) -> bool:
        """
        Check if a file requires conversion to EPUB.

        Args:
            file_path: Path to the file

        Returns:
            True if conversion needed, False if already EPUB
        """
        ext = Path(file_path).suffix.lower()
        return ext != '.epub'


# Convenience functions
def detect_format(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect the format of a document file.

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (format_key, format_description)
    """
    return FormatDetector.detect_format(file_path)


def is_supported(file_path: str) -> bool:
    """
    Check if a file format is supported.

    Args:
        file_path: Path to the file

    Returns:
        True if supported, False otherwise
    """
    return FormatDetector.is_supported(file_path)


def get_file_filter() -> str:
    """
    Get file filter string for file dialogs.

    Returns:
        File filter string
    """
    return FormatDetector.get_file_filter_string()

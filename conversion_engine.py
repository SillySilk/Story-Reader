"""
Document to EPUB Conversion Engine

This module handles converting various document formats (DOCX, TXT, PDF, MD, HTML, etc.)
to EPUB format using Pandoc as the primary converter with fallback options.

Supported formats:
- DOCX, DOC (via Pandoc or Mammoth fallback)
- TXT, MD, Markdown (via Pandoc)
- PDF (via Pandoc with pdftotext)
- HTML, HTM (via Pandoc)
- ODT, RTF (via Pandoc)
- And 40+ more formats supported by Pandoc
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """Raised when document conversion fails"""
    pass


class ConversionEngine:
    """
    Handles conversion of various document formats to EPUB.

    Uses Pandoc as primary converter with fallback to Mammoth+ebooklib for DOCX.
    Provides progress callbacks and detailed error reporting.
    """

    # Supported formats mapping (extension -> pandoc format name)
    SUPPORTED_FORMATS = {
        # Word formats
        '.docx': 'docx',
        '.doc': 'doc',

        # Text formats
        '.txt': 'plain',
        '.md': 'markdown',
        '.markdown': 'markdown',

        # Web formats
        '.html': 'html',
        '.htm': 'html',

        # Other document formats
        '.odt': 'odt',
        '.rtf': 'rtf',
        '.pdf': 'pdf',

        # E-book formats (pass-through)
        '.epub': 'epub',
    }

    def __init__(self,
                 preferred_converter: str = 'pandoc',
                 conversion_timeout: int = 300,
                 temp_dir: Optional[str] = None):
        """
        Initialize the conversion engine.

        Args:
            preferred_converter: 'pandoc' or 'mammoth' (for DOCX only)
            conversion_timeout: Maximum time in seconds for conversion
            temp_dir: Custom temporary directory for conversion files
        """
        self.preferred_converter = preferred_converter
        self.conversion_timeout = conversion_timeout
        self.temp_dir = temp_dir or tempfile.gettempdir()

        # Check if Pandoc is available
        self._pandoc_available = self._check_pandoc()

        if not self._pandoc_available and preferred_converter == 'pandoc':
            logger.warning("Pandoc not available, will use fallback converters")

    def _check_pandoc(self) -> bool:
        """Check if Pandoc is available"""
        try:
            import pypandoc
            # pypandoc-binary includes Pandoc bundled
            return True
        except ImportError:
            logger.warning("pypandoc not installed")
            return False
        except Exception as e:
            logger.warning(f"Error checking Pandoc: {e}")
            return False

    def is_supported(self, file_path: str) -> bool:
        """
        Check if a file format is supported for conversion.

        Args:
            file_path: Path to the file

        Returns:
            True if format is supported, False otherwise
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_FORMATS

    def get_format_name(self, file_path: str) -> Optional[str]:
        """
        Get the Pandoc format name for a file.

        Args:
            file_path: Path to the file

        Returns:
            Pandoc format name or None if unsupported
        """
        ext = Path(file_path).suffix.lower()
        return self.SUPPORTED_FORMATS.get(ext)

    def convert_to_epub(self,
                       input_path: str,
                       output_path: str,
                       metadata: Optional[Dict[str, str]] = None,
                       progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """
        Convert a document to EPUB format.

        Args:
            input_path: Path to input document
            output_path: Path where EPUB should be saved
            metadata: Optional metadata (title, author, etc.)
            progress_callback: Optional callback(percent, status_message)

        Returns:
            True if conversion succeeded, False otherwise

        Raises:
            ConversionError: If conversion fails
        """
        if not os.path.exists(input_path):
            raise ConversionError(f"Input file not found: {input_path}")

        if not self.is_supported(input_path):
            ext = Path(input_path).suffix
            raise ConversionError(f"Unsupported file format: {ext}")

        # If already EPUB, just copy it
        if Path(input_path).suffix.lower() == '.epub':
            if progress_callback:
                progress_callback(50, "Copying EPUB file...")
            shutil.copy2(input_path, output_path)
            if progress_callback:
                progress_callback(100, "Complete")
            return True

        # Try Pandoc first
        if self._pandoc_available:
            try:
                if progress_callback:
                    progress_callback(10, "Starting Pandoc conversion...")

                success = self._convert_with_pandoc(
                    input_path, output_path, metadata, progress_callback
                )

                if success:
                    if progress_callback:
                        progress_callback(100, "Conversion complete")
                    return True

            except Exception as e:
                logger.warning(f"Pandoc conversion failed: {e}")
                # Fall through to fallback methods

        # Fallback for DOCX: Mammoth + ebooklib
        ext = Path(input_path).suffix.lower()
        if ext in ['.docx', '.doc']:
            try:
                if progress_callback:
                    progress_callback(10, "Using Mammoth fallback for DOCX...")

                success = self._convert_docx_fallback(
                    input_path, output_path, metadata, progress_callback
                )

                if success:
                    if progress_callback:
                        progress_callback(100, "Conversion complete")
                    return True

            except Exception as e:
                logger.error(f"DOCX fallback conversion failed: {e}")
                raise ConversionError(f"Failed to convert DOCX: {e}")

        # No converter available
        raise ConversionError(
            f"No converter available for {ext}. "
            "Install pypandoc-binary for full format support."
        )

    def _convert_with_pandoc(self,
                            input_path: str,
                            output_path: str,
                            metadata: Optional[Dict[str, str]],
                            progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """
        Convert document using Pandoc.

        Args:
            input_path: Path to input file
            output_path: Path to output EPUB
            metadata: Optional metadata dict
            progress_callback: Optional progress callback

        Returns:
            True if successful, False otherwise
        """
        try:
            import pypandoc

            # Get source format
            source_format = self.get_format_name(input_path)
            if not source_format:
                return False

            if progress_callback:
                progress_callback(30, f"Converting {source_format.upper()} to EPUB...")

            # Build extra arguments
            extra_args = [
                '--standalone',
                '--toc',  # Table of contents
                '--toc-depth=3',
            ]

            # Add metadata if provided
            if metadata:
                if 'title' in metadata:
                    extra_args.extend(['--metadata', f'title={metadata["title"]}'])
                if 'author' in metadata:
                    extra_args.extend(['--metadata', f'author={metadata["author"]}'])
                if 'language' in metadata:
                    extra_args.extend(['--metadata', f'lang={metadata["language"]}'])

            if progress_callback:
                progress_callback(60, "Processing document...")

            # Perform conversion
            pypandoc.convert_file(
                input_path,
                'epub',
                outputfile=output_path,
                format=source_format,
                extra_args=extra_args
            )

            if progress_callback:
                progress_callback(90, "Finalizing EPUB...")

            # Verify output exists
            if not os.path.exists(output_path):
                return False

            logger.info(f"Successfully converted {input_path} to EPUB using Pandoc")
            return True

        except Exception as e:
            logger.error(f"Pandoc conversion error: {e}")
            return False

    def _convert_docx_fallback(self,
                              input_path: str,
                              output_path: str,
                              metadata: Optional[Dict[str, str]],
                              progress_callback: Optional[Callable[[int, str], None]]) -> bool:
        """
        Convert DOCX using Mammoth + ebooklib as fallback.

        Args:
            input_path: Path to DOCX file
            output_path: Path to output EPUB
            metadata: Optional metadata dict
            progress_callback: Optional progress callback

        Returns:
            True if successful, False otherwise
        """
        try:
            import mammoth
            from ebooklib import epub

            if progress_callback:
                progress_callback(20, "Reading DOCX with Mammoth...")

            # Convert DOCX to HTML using Mammoth
            with open(input_path, 'rb') as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html_content = result.value

            if progress_callback:
                progress_callback(50, "Creating EPUB structure...")

            # Create EPUB book
            book = epub.EpubBook()

            # Set metadata
            title = metadata.get('title', Path(input_path).stem) if metadata else Path(input_path).stem
            author = metadata.get('author', 'Unknown') if metadata else 'Unknown'
            language = metadata.get('language', 'en') if metadata else 'en'

            book.set_identifier(f'id_{Path(input_path).stem}')
            book.set_title(title)
            book.set_language(language)
            book.add_author(author)

            if progress_callback:
                progress_callback(70, "Adding content to EPUB...")

            # Create a chapter with the HTML content
            chapter = epub.EpubHtml(
                title='Content',
                file_name='content.xhtml',
                lang=language
            )
            chapter.content = f'<html><body>{html_content}</body></html>'

            book.add_item(chapter)

            # Define Table of Contents
            book.toc = (chapter,)

            # Add navigation files
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())

            # Define CSS style
            style = '''
                body { font-family: Georgia, serif; margin: 2em; }
                p { margin: 1em 0; line-height: 1.5; }
                h1, h2, h3 { margin-top: 1.5em; }
            '''
            nav_css = epub.EpubItem(
                uid="style_nav",
                file_name="style/nav.css",
                media_type="text/css",
                content=style
            )
            book.add_item(nav_css)

            # Create spine
            book.spine = ['nav', chapter]

            if progress_callback:
                progress_callback(90, "Writing EPUB file...")

            # Write EPUB file
            epub.write_epub(output_path, book)

            logger.info(f"Successfully converted {input_path} to EPUB using Mammoth fallback")
            return True

        except Exception as e:
            logger.error(f"Mammoth fallback conversion error: {e}")
            return False

    def extract_metadata(self, file_path: str) -> Dict[str, str]:
        """
        Extract metadata from a document.

        Args:
            file_path: Path to document

        Returns:
            Dictionary with metadata (title, author, etc.)
        """
        metadata = {
            'title': Path(file_path).stem,
            'author': 'Unknown',
            'language': 'en'
        }

        # Try to extract metadata from DOCX using python-docx
        ext = Path(file_path).suffix.lower()
        if ext in ['.docx']:
            try:
                from docx import Document
                doc = Document(file_path)
                core_props = doc.core_properties

                if core_props.title:
                    metadata['title'] = core_props.title
                if core_props.author:
                    metadata['author'] = core_props.author
                if core_props.language:
                    metadata['language'] = core_props.language

            except Exception as e:
                logger.debug(f"Could not extract DOCX metadata: {e}")

        return metadata


# Convenience function for simple conversions
def convert_to_epub(input_path: str,
                   output_path: str,
                   progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
    """
    Simple function to convert a document to EPUB.

    Args:
        input_path: Path to input document
        output_path: Path where EPUB should be saved
        progress_callback: Optional callback for progress updates

    Returns:
        True if conversion succeeded

    Raises:
        ConversionError: If conversion fails
    """
    engine = ConversionEngine()

    # Extract metadata
    metadata = engine.extract_metadata(input_path)

    # Perform conversion
    return engine.convert_to_epub(input_path, output_path, metadata, progress_callback)

"""
Foliate-js Integration for PyQt6

This module integrates the Foliate-js EPUB renderer with PyQt6's QWebEngineView.
Provides automatic reflow on zoom, CFI-based bookmarks, and rich navigation features.

Key features:
- Native EPUB rendering with Foliate-js
- Automatic content reflow on zoom
- CFI (Canonical Fragment Identifier) based navigation
- Python↔JavaScript communication via QWebChannel
- Progress tracking and table of contents
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FoliateJSBridge(QObject):
    """
    Bridge object for Python↔JavaScript communication via QWebChannel.

    Signals:
        location_changed: Emitted when user navigates to a new location
        progress_changed: Emitted when reading progress changes
    """

    location_changed = pyqtSignal(str)  # CFI location
    progress_changed = pyqtSignal(float)  # 0.0 - 1.0

    def __init__(self):
        super().__init__()
        self._current_cfi = None
        self._progress = 0.0

    @pyqtSlot(str)
    def onLocationChanged(self, cfi: str):
        """Called from JavaScript when location changes"""
        self._current_cfi = cfi
        logger.debug(f"Location changed to: {cfi}")
        self.location_changed.emit(cfi)

    @pyqtSlot(float)
    def onProgressChanged(self, progress: float):
        """Called from JavaScript when progress changes"""
        self._progress = progress
        logger.debug(f"Progress: {progress:.2%}")
        self.progress_changed.emit(progress)

    @pyqtSlot(str)
    def logMessage(self, message: str):
        """Log messages from JavaScript"""
        logger.info(f"[JS] {message}")

    def get_current_cfi(self) -> Optional[str]:
        """Get the current CFI location"""
        return self._current_cfi

    def get_progress(self) -> float:
        """Get current reading progress (0.0 - 1.0)"""
        return self._progress


class FoliateRenderer:
    """
    Foliate-js EPUB renderer for PyQt6 QWebEngineView.

    Handles EPUB rendering with automatic reflow, CFI navigation,
    and Python↔JavaScript communication.
    """

    def __init__(self, web_view, http_server=None):
        """
        Initialize the Foliate renderer.

        Args:
            web_view: QWebEngineView instance
            http_server: Optional FoliateHTTPServer instance for serving files over HTTP
        """
        self.web_view = web_view
        self.http_server = http_server
        self.bridge = FoliateJSBridge()
        self.channel = QWebChannel()
        self.channel.registerObject('pyBridge', self.bridge)

        # Set up web view
        self.web_view.page().setWebChannel(self.channel)

        # Enable JavaScript and local file access
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        # Critical for ES modules
        from PyQt6.QtCore import QUrl
        scheme_handler_installed = False  # We'll use file:// directly

        # Current state
        self.current_epub_path = None

    def generate_reader_html(self, epub_path: str) -> str:
        """
        Generate HTML template for Foliate-js reader.

        Args:
            epub_path: Absolute path to EPUB file

        Returns:
            HTML string with embedded Foliate-js
        """
        # Use HTTP URLs if server is available, otherwise fall back to file:// URLs
        if self.http_server and self.http_server.is_running():
            # Copy EPUB to served directory (cache may be outside served root)
            import shutil
            temp_dir = os.path.join(os.getcwd(), 'assets', 'temp')
            os.makedirs(temp_dir, exist_ok=True)

            epub_filename = os.path.basename(epub_path)
            served_epub_path = os.path.join(temp_dir, epub_filename)

            # Copy EPUB if not already there or source is newer
            if not os.path.exists(served_epub_path) or \
               os.path.getmtime(epub_path) > os.path.getmtime(served_epub_path):
                shutil.copy2(epub_path, served_epub_path)
                logger.debug(f"Copied EPUB to served directory: {served_epub_path}")

            # Generate HTTP URLs relative to server root
            epub_url = self.http_server.get_url(f'assets/temp/{epub_filename}')
            foliate_url = self.http_server.get_url('assets/foliate-js')
            logger.info(f"Using HTTP URLs - EPUB: {epub_url}, Foliate: {foliate_url}")
        else:
            # Fall back to file:// URLs (will have ES module issues)
            epub_url = Path(epub_path).as_uri()
            foliate_dir = os.path.abspath("assets/foliate-js")
            foliate_url = Path(foliate_dir).as_uri()
            logger.warning("HTTP server not available - using file:// URLs (ES modules may not work)")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Foliate Reader</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            width: 100%;
            height: 100%;
            overflow: hidden;
            background: #1e1e1e;
        }}

        #viewer {{
            width: 100%;
            height: 100%;
        }}

        foliate-view {{
            width: 100%;
            height: 100%;
            display: block;
        }}

        /* Reading area styling */
        foliate-view::part(main) {{
            background: #2a2a2a;
        }}

        /* Content styling */
        body {{
            font-family: Georgia, serif;
            line-height: 1.6;
            color: #e0e0e0;
        }}
    </style>

    <script type="module">
        console.log('🚀 Foliate reader script starting...');
        console.log('Foliate URL:', '{foliate_url}/view.js');
        console.log('EPUB URL:', '{epub_url}');

        // Import Foliate-js view
        import '{foliate_url}/view.js';
        console.log('✅ Import statement executed');

        let view = null;

        // Initialize Foliate view immediately (without QWebChannel for now)
        initializeFoliate();

        async function initializeFoliate() {{
            console.log('Initializing Foliate view...');

            // Create foliate-view element
            view = document.createElement('foliate-view');
            document.getElementById('viewer').appendChild(view);
            console.log('Foliate view element created');

            // Listen for location changes
            view.addEventListener('relocate', (e) => {{
                const cfi = e.detail?.cfi || '';
                const fraction = e.detail?.fraction || 0;
                console.log('Location changed:', cfi, 'Progress:', fraction);
            }});

            // Open the EPUB
            try {{
                console.log('Opening EPUB:', '{epub_url}');
                await view.open('{epub_url}');
                console.log('✅ EPUB opened successfully!');
            }} catch (err) {{
                console.error('❌ Error opening EPUB:', err);
                console.error('Error stack:', err.stack);
            }}
        }}

        // Expose navigation functions to Python
        window.goToLocation = async function(cfi) {{
            if (view) {{
                try {{
                    await view.goTo(cfi);
                    return true;
                }} catch (err) {{
                    console.error('Error navigating to CFI:', err);
                    return false;
                }}
            }}
            return false;
        }};

        window.goToFraction = async function(fraction) {{
            if (view) {{
                try {{
                    await view.goToFraction(fraction);
                    return true;
                }} catch (err) {{
                    console.error('Error navigating to fraction:', err);
                    return false;
                }}
            }}
            return false;
        }};

        window.nextPage = function() {{
            if (view) view.next();
        }};

        window.prevPage = function() {{
            if (view) view.prev();
        }};

        window.getMetadata = function() {{
            if (view && view.book) {{
                return {{
                    title: view.book.metadata?.title || 'Unknown',
                    author: view.book.metadata?.author || 'Unknown',
                    language: view.book.metadata?.language || 'en'
                }};
            }}
            return null;
        }};
    </script>
</head>
<body>
    <div id="viewer"></div>
</body>
</html>
"""
        return html

    def load_epub(self, epub_path: str):
        """
        Load an EPUB file into the renderer.

        Args:
            epub_path: Absolute path to EPUB file
        """
        if not os.path.exists(epub_path):
            logger.error(f"EPUB file not found: {epub_path}")
            return

        self.current_epub_path = epub_path

        # Generate HTML
        html = self.generate_reader_html(epub_path)

        if self.http_server and self.http_server.is_running():
            # Use HTTP server - write HTML to served directory and load via HTTP
            reader_html_path = os.path.join(os.getcwd(), 'assets', 'foliate-js', 'reader.html')
            with open(reader_html_path, 'w', encoding='utf-8') as f:
                f.write(html)

            http_url = self.http_server.get_url('assets/foliate-js/reader.html')
            logger.info(f"Loading via HTTP: {http_url}")
            self.web_view.setUrl(QUrl(http_url))
        else:
            # Fall back to file:// with temp file (ES modules won't work)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp:
                tmp.write(html)
                temp_html_path = tmp.name

            file_url = QUrl.fromLocalFile(temp_html_path)
            logger.warning(f"Loading via file:// - ES modules may fail: {file_url.toString()}")
            self.web_view.setUrl(file_url)

        logger.info(f"Loaded EPUB: {epub_path}")

    def go_to_cfi(self, cfi: str, callback: Optional[Callable] = None):
        """
        Navigate to a CFI location.

        Args:
            cfi: CFI string (e.g., "epubcfi(/6/14!/4/2/10)")
            callback: Optional callback for result
        """
        js_code = f"goToLocation('{cfi}')"

        if callback:
            self.web_view.page().runJavaScript(js_code, callback)
        else:
            self.web_view.page().runJavaScript(js_code)

    def go_to_fraction(self, fraction: float, callback: Optional[Callable] = None):
        """
        Navigate to a fractional position (0.0 - 1.0).

        Args:
            fraction: Position as decimal (0.0 = start, 1.0 = end)
            callback: Optional callback for result
        """
        js_code = f"goToFraction({fraction})"

        if callback:
            self.web_view.page().runJavaScript(js_code, callback)
        else:
            self.web_view.page().runJavaScript(js_code)

    def next_page(self):
        """Go to next page"""
        self.web_view.page().runJavaScript("nextPage()")

    def prev_page(self):
        """Go to previous page"""
        self.web_view.page().runJavaScript("prevPage()")

    def get_metadata(self, callback: Callable):
        """
        Get EPUB metadata.

        Args:
            callback: Function to receive metadata dict
        """
        self.web_view.page().runJavaScript("getMetadata()", callback)

    def get_current_cfi(self) -> Optional[str]:
        """Get current CFI location"""
        return self.bridge.get_current_cfi()

    def get_progress(self) -> float:
        """Get current reading progress (0.0 - 1.0)"""
        return self.bridge.get_progress()

    def connect_location_changed(self, slot: Callable):
        """
        Connect a slot to location change signal.

        Args:
            slot: Function to call when location changes (receives CFI string)
        """
        self.bridge.location_changed.connect(slot)

    def connect_progress_changed(self, slot: Callable):
        """
        Connect a slot to progress change signal.

        Args:
            slot: Function to call when progress changes (receives float 0.0-1.0)
        """
        self.bridge.progress_changed.connect(slot)


class CFIBookmark:
    """
    CFI-based bookmark for EPUB files.

    CFI (Canonical Fragment Identifier) is the standard way to reference
    locations in EPUB files, replacing page numbers.
    """

    def __init__(self,
                 epub_path: str,
                 cfi: str,
                 display_text: Optional[str] = None,
                 page_num: Optional[int] = None):
        """
        Create a CFI bookmark.

        Args:
            epub_path: Path to EPUB file
            cfi: CFI location string
            display_text: Optional human-readable description
            page_num: Optional legacy page number (for display only)
        """
        self.epub_path = epub_path
        self.cfi = cfi
        self.display_text = display_text or cfi
        self.page_num = page_num  # Legacy, for display only

    def to_dict(self) -> Dict:
        """Convert bookmark to dictionary for JSON serialization"""
        return {
            'epub_path': self.epub_path,
            'cfi': self.cfi,
            'display_text': self.display_text,
            'page_num': self.page_num
        }

    @staticmethod
    def from_dict(data: Dict) -> 'CFIBookmark':
        """Create bookmark from dictionary"""
        return CFIBookmark(
            epub_path=data.get('epub_path', ''),
            cfi=data.get('cfi', ''),
            display_text=data.get('display_text'),
            page_num=data.get('page_num')
        )

    def __repr__(self):
        if self.page_num:
            return f"CFIBookmark(page={self.page_num}, cfi={self.cfi[:20]}...)"
        return f"CFIBookmark(cfi={self.cfi})"

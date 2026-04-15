import os
import glob
import atexit
import mammoth
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QVBoxLayout, QHBoxLayout,
                             QPushButton, QWidget, QFrame, QFileDialog, QApplication,
                             QLineEdit, QLabel)
from PyQt6.QtGui import QAction
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import Qt, QTimer

from utils import load_json, save_json, CONFIG_FILE, SESSION_FILE, BOOKMARKS_FILE, DEFAULT_BINDINGS
from input_engine import InputBridge
from gui_dialogs import OptionsDialog, BookmarksDialog

class WebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS Console [{level}] Line {lineNumber}: {message}")

class StoryReader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_FILE)
        self.bookmarks = load_json(BOOKMARKS_FILE, default=[])
        self.loaded_stories = set()
        self.load_session()
        atexit.register(self.cleanup_session)

        self.setWindowTitle("Story Reader Pro")
        self.setStyleSheet("background-color: #222; color: #EEE;")
        self.resize(1000, 800)
        
        # --- Bridge Setup ---
        self.bridge = InputBridge()
        self.bridge.sig_trigger_action.connect(self.handle_action)
        
        # --- UI Setup ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # Side panel for controls
        side_panel = QFrame()
        side_panel.setStyleSheet("background: #2a2a2a; border-right: 1px solid #555;")
        side_panel.setMinimumWidth(200)
        side_panel.setMaximumWidth(200)

        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(10, 10, 10, 10)
        side_layout.setSpacing(10)

        style = "QPushButton { background: #444; color: #EEE; padding: 10px; border-radius: 4px; font-size: 14px; }"
        def mk_btn(txt, func, col=None):
            b = QPushButton(txt)
            b.setStyleSheet(style if not col else f"background: {col}; color: white; padding: 10px; border-radius: 4px; font-size: 14px;")
            b.clicked.connect(func)
            return b

        # Navigation buttons
        side_layout.addWidget(mk_btn("<< -5 Pages", lambda: self.js("jumpPages(-5)")))
        side_layout.addWidget(mk_btn("< Previous", lambda: self.js("jumpPages(-1)")))
        side_layout.addWidget(mk_btn("Next >", lambda: self.js("jumpPages(1)")))
        side_layout.addWidget(mk_btn("5 Pages >>", lambda: self.js("jumpPages(5)")))

        side_layout.addSpacing(20)

        # Page counter display
        self.page_display = QLabel("1 / 1")
        self.page_display.setStyleSheet("color: #EEE; padding: 10px; font-weight: bold; font-size: 16px; background: #333; border-radius: 4px; text-align: center;")
        self.page_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(self.page_display)

        # Page number input
        page_label = QLabel("Jump to Page:")
        page_label.setStyleSheet("color: #EEE; font-size: 12px;")
        side_layout.addWidget(page_label)

        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Enter page #")
        self.page_input.setStyleSheet("background: #555; color: #EEE; padding: 8px; border-radius: 4px; border: 1px solid #666; font-size: 14px;")
        self.page_input.returnPressed.connect(self.jump_to_input_page)
        side_layout.addWidget(self.page_input)

        side_layout.addWidget(mk_btn("Go", self.jump_to_input_page, "#28a745"))

        side_layout.addSpacing(20)

        # Bookmarks
        side_layout.addWidget(mk_btn("Bookmarks", self.open_bookmarks))
        side_layout.addWidget(mk_btn("Bookmark Page", self.add_bookmark, "#0275d8"))

        side_layout.addStretch()

        # Web view
        self.web = QWebEngineView()
        self.web.setPage(WebPage(self.web))
        self.web.setStyleSheet("background: black;")
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Enable developer tools for debugging
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        main_layout.addWidget(side_panel)
        main_layout.addWidget(self.web)
        
        self.setup_menu()
        self.update_bindings()

        # Timer to update page display periodically (started when file loads)
        self.page_timer = QTimer()
        self.page_timer.timeout.connect(self.update_page_display)

        self.auto_load()

    def setup_menu(self):
        bar = self.menuBar()
        
        def add_action(menu, text, slot, shortcut=None):
            act = QAction(text, self)
            if shortcut: act.setShortcut(shortcut)
            act.triggered.connect(slot)
            menu.addAction(act)

        f_menu = bar.addMenu("File")
        add_action(f_menu, "Open", self.open_file, "Ctrl+O")
        add_action(f_menu, "Exit", self.close, "Ctrl+Q")
        
        o_menu = bar.addMenu("Options")
        add_action(o_menu, "Preferences", self.open_options, "Ctrl+P")
        add_action(o_menu, "Reset History", self.reset_session)

    def handle_action(self, action):
        if QApplication.activeWindow() is None: return
        if QApplication.activeModalWidget(): return

        map = {
            "nav_next_page": lambda: self.js("jumpPages(1)"),
            "nav_prev_page": lambda: self.js("jumpPages(-1)"),
            "nav_jump_fwd_5": lambda: self.js("jumpPages(5)"),
            "nav_jump_back_5": lambda: self.js("jumpPages(-5)"),
            "nav_bookmark": self.add_bookmark,
            "nav_next_story": self.next_file,
            "nav_random_story": self.random_file
        }
        if action in map: map[action]()

    def js(self, code, cb=None):
        if self.web.page():
            if cb: self.web.page().runJavaScript(code, cb)
            else: self.web.page().runJavaScript(code)

    def generate_html(self, content, page_num=1):
        # CHARACTER-BASED APPROACH: Calculate chars per page, split by that count
        import re

        # Strip HTML tags to count raw characters
        text_only = re.sub(r'<[^>]+>', '', content)

        # Fixed measurements:
        # - Font: 18px
        # - Line height: 1.8 (32.4px per line)
        # - Page height: ~617px
        # - Padding: 50px top + 50px bottom = 100px
        # - Available height: 517px
        # - Lines per page: 517 / 32.4 = ~16 lines
        # - Chars per line: ~65 (typical at 900px width with 18px font)
        # - Chars per page: 16 * 65 = 1040 chars
        # - Apply 20% safety margin: 1040 * 0.8 = 832 chars

        CHARS_PER_PAGE = 1050  # Target character count per page

        # Split content into pages at word boundaries
        pages = []
        current_pos = 0

        while current_pos < len(content):
            # Get target chunk
            end_pos = current_pos + CHARS_PER_PAGE

            if end_pos >= len(content):
                # Last page - take everything remaining
                page_content = content[current_pos:]
                pages.append(page_content)
                break

            # Find the last space before end_pos to avoid cutting words
            chunk = content[current_pos:end_pos]

            # Look for last space in the chunk
            last_space = chunk.rfind(' ')

            # If no space found, look for other word boundaries
            if last_space == -1:
                last_space = max(
                    chunk.rfind('.'),
                    chunk.rfind(','),
                    chunk.rfind('>'),  # HTML tag end
                    chunk.rfind('\n')
                )

            if last_space != -1:
                # Break at the word boundary
                page_content = content[current_pos:current_pos + last_space + 1]
                pages.append(page_content)
                current_pos += last_space + 1
            else:
                # No good break point found, just break at target
                page_content = content[current_pos:end_pos]
                pages.append(page_content)
                current_pos = end_pos

        if not pages:
            pages = [content]

        # Create page divs
        page_divs = ''
        for i, page_content in enumerate(pages):
            active_class = 'active' if i == page_num - 1 else ''
            page_divs += f'<div class="page {active_class}" id="page-{i}">{page_content}</div>\n'

        css = """<style>
            @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@300;700&display=swap');
            body {
                background: #1a1a1a;
                color: #DDD;
                font-family: 'Merriweather', serif;
                margin: 0;
                overflow: hidden;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            #book-container {
                width: 100%;
                max-width: 900px;
                height: 100vh;
                position: relative;
                background: #f5f5dc;
                box-shadow: 0 10px 50px rgba(0,0,0,0.5);
                overflow: hidden; /* Clip content to viewport */
            }
            .page {
                color: #222;
                padding: 50px 80px;
                box-sizing: border-box;
                height: 100%;
                width: 100%;
                font-size: 18px;
                line-height: 1.8;
                text-align: justify;
                overflow: hidden;
                display: none;
            }
            .page.active {
                display: block;
                animation: flipIn 0.4s ease-out;
            }
            @keyframes flipIn {
                from {
                    opacity: 0;
                    transform: rotateY(-15deg);
                }
                to {
                    opacity: 1;
                    transform: rotateY(0);
                }
            }
            .page p {
                margin: 0 0 1em 0;
            }
            .page h1, .page h2, .page h3 {
                margin: 1.5em 0 0.5em 0;
            }
            #bar {
                position: fixed;
                bottom: 0;
                left: 0;
                height: 4px;
                background: #555;
                width: 0%;
            }
        </style>"""

        total_pages = len(pages)

        js = f"""<script>
            let currentPage = 1;
            let totalPages = {total_pages};

            window.onload = () => {{
                showPage({page_num});
            }};

            function showPage(pageNum) {{
                currentPage = Math.max(1, Math.min(pageNum, totalPages));

                // Hide all pages
                const pages = document.querySelectorAll('.page');
                pages.forEach(p => p.classList.remove('active'));

                // Show current page
                const currentPageDiv = document.getElementById('page-' + (currentPage - 1));
                if (currentPageDiv) {{
                    currentPageDiv.classList.add('active');
                }}

                update();
            }}

            function update() {{
                const progress = totalPages > 1 ? ((currentPage - 1) / (totalPages - 1)) * 100 : 0;
                document.getElementById('bar').style.width = progress + '%';

                window.currentPage = currentPage;
                window.totalPages = totalPages;
            }}

            function jumpPages(n) {{
                showPage(currentPage + n);
            }}

            function jumpToPage(pageNum) {{
                showPage(pageNum);
            }}

            function getInfo() {{
                return [currentPage - 1, currentPage.toString()];
            }}

            function getPageInfo() {{
                return {{
                    'current': currentPage,
                    'total': totalPages
                }};
            }}
        </script>"""

        html = f"""<html>
        <head>
            <meta charset="UTF-8">
            {css}
        </head>
        <body>
            <div id="book-container">
                {page_divs}
            </div>
            <div id="bar"></div>
            {js}
        </body>
        </html>"""

        return html

    def load_file(self, path, page_num=1):
        if not path or not os.path.exists(path): return
        self.curr_path = path
        self.setWindowTitle(f"Story Reader - {os.path.basename(path)}")
        try:
            with open(path, "rb") as f:
                html = mammoth.convert_to_html(f).value
                self.web.setHtml(self.generate_html(html, page_num))
            self.loaded_stories.add(os.path.abspath(path))
            self.save_session()

            # Start page timer after content is loaded
            if not self.page_timer.isActive():
                self.page_timer.start(500)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def add_bookmark(self):
        if not hasattr(self, 'curr_path'): return
        self.js("getInfo()", self._save_bm)
    
    def _save_bm(self, info):
        if not info: return
        page_num = int(info[1]) if isinstance(info[1], str) else info[1]
        entry = {
            "path": self.curr_path,
            "page_num": page_num,
            "display_page": str(page_num)
        }
        self.bookmarks = [b for b in self.bookmarks if b['path'] != self.curr_path]
        self.bookmarks.insert(0, entry)
        save_json(BOOKMARKS_FILE, self.bookmarks)
        QMessageBox.information(self, "Saved", f"Bookmarked Page {page_num}")

    def open_bookmarks(self):
        dlg = BookmarksDialog(self, self.bookmarks,
                              lambda bm: self.load_file(bm['path'], bm.get('page_num', 1)),
                              lambda idx: self._del_bm(idx))
        dlg.exec()

    def _del_bm(self, idx):
        if 0 <= idx < len(self.bookmarks):
            del self.bookmarks[idx]
            save_json(BOOKMARKS_FILE, self.bookmarks)

    def open_options(self):
        folder = self.config.get("default_folder", "")
        binds = self.config.get("bindings", DEFAULT_BINDINGS)
        dlg = OptionsDialog(self, folder, binds)
        if dlg.exec():
            f, b = dlg.get_results()
            self.config["default_folder"] = f
            self.config["bindings"] = b
            save_json(CONFIG_FILE, self.config)
            self.update_bindings()

    def update_bindings(self):
        self.bridge.update_bindings(self.config.get("bindings", DEFAULT_BINDINGS))

    def auto_load(self):
        # Try to load last opened file first
        if hasattr(self, 'last_file') and self.last_file and os.path.exists(self.last_file):
            self.load_file(self.last_file)
            return

        # Otherwise load first file from default folder
        d = self.config.get("default_folder", "")
        if d and os.path.exists(d):
            fs = sorted(glob.glob(os.path.join(d, "*.docx")))
            if fs: self.load_file(fs[0])
            
    def open_file(self):
        # Start in default folder if configured
        default_dir = self.config.get("default_folder", "")
        f, _ = QFileDialog.getOpenFileName(self, "Open", default_dir, "Word (*.docx)")
        if f: self.load_file(f)
        
    def next_file(self): self._cycle_file(1)
    
    def _cycle_file(self, delta):
        # Always cycle through default folder, not current file's directory
        d = self.config.get("default_folder", "")
        if not d or not os.path.exists(d): return

        fs = sorted(glob.glob(os.path.join(d, "*.docx")), key=lambda s: s.lower())
        if not fs: return

        # Find current file in default folder list
        try:
            if hasattr(self, 'curr_path'):
                curr = next(i for i, f in enumerate(fs) if os.path.abspath(f) == os.path.abspath(self.curr_path))
            else:
                curr = -1  # Start from beginning if no current file
            self.load_file(fs[(curr + delta) % len(fs)])
        except:
            # Current file not in default folder, start from beginning
            self.load_file(fs[0 if delta > 0 else -1])

    def random_file(self):
        if not hasattr(self, 'curr_path'): return
        d = os.path.dirname(self.curr_path)
        fs = glob.glob(os.path.join(d, "*.docx"))
        import random
        self.load_file(random.choice(fs))

    def jump_to_input_page(self):
        try:
            page_num = int(self.page_input.text())
            self.js(f"jumpToPage({page_num})")
            self.page_input.clear()
        except ValueError:
            QMessageBox.warning(self, "Invalid Page", "Please enter a valid page number")

    def update_page_display(self):
        # Only update if page is loaded and has content
        if self.web.page() and hasattr(self, 'curr_path'):
            self.js("getPageInfo()", self._update_display)

    def _update_display(self, info):
        if info and isinstance(info, dict):
            current = info.get('current', 1)
            total = info.get('total', 1)
            self.page_display.setText(f"{current} / {total}")
            self.page_input.setPlaceholderText(str(current))

    # Session helpers
    def load_session(self):
        session = load_json(SESSION_FILE)
        self.loaded_stories = set(session.get("loaded", []))
        self.last_file = session.get("last_file", None)

    def save_session(self):
        save_json(SESSION_FILE, {
            "loaded": list(self.loaded_stories),
            "last_file": self.curr_path if hasattr(self, 'curr_path') else None
        })
    def reset_session(self): 
        self.loaded_stories = set()
        self.save_session()
    def cleanup_session(self):
        # Preserve last_file but clear loaded_stories list
        session = load_json(SESSION_FILE)
        save_json(SESSION_FILE, {
            "loaded": [],
            "last_file": session.get("last_file", None)
        })
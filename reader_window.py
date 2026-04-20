import os
import glob
import json
import atexit
import re
import mammoth
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QVBoxLayout, QWidget, QFileDialog, QApplication
from PyQt6.QtGui import QAction
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QTimer, QUrl

from utils import load_json, save_json, CONFIG_FILE, SESSION_FILE, BOOKMARKS_FILE, DEFAULT_BINDINGS
from input_engine import InputBridge
from gui_dialogs import OptionsDialog, BookmarksDialog

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reader_template.html')


class WebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS [{level}] L{lineNumber}: {message}")


class StoryReader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_FILE)
        self.bookmarks = load_json(BOOKMARKS_FILE, default=[])
        self.loaded_stories = set()
        self.curr_path = None
        self.load_session()
        atexit.register(self.cleanup_session)

        self.setWindowTitle("Story Reader Pro")
        self.resize(1200, 900)

        self.bridge = InputBridge()
        self.bridge.sig_trigger_action.connect(self.handle_action)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.web = QWebEngineView()
        self.web.setPage(WebPage(self.web))
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        layout.addWidget(self.web)

        self.setup_menu()
        self.update_bindings()

        # Load template once; Python injects content via JS
        base_url = QUrl.fromLocalFile(TEMPLATE_PATH)
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            template_html = f.read()
        self.web.setHtml(template_html, base_url)

        # After page loads, push library + bookmarks and auto-load
        self.web.loadFinished.connect(self._on_load_finished)

        # Poll for JS->Python actions (JS sets window._pendingAction)
        self._action_timer = QTimer()
        self._action_timer.timeout.connect(self._check_js_action)
        self._action_timer.start(250)

    def _on_load_finished(self, ok):
        if not ok:
            return
        self.web.loadFinished.disconnect(self._on_load_finished)
        self._push_library()
        self._push_bookmarks()
        self.auto_load()

    def _push_library(self):
        d = self.config.get('default_folder', '')
        if not d or not os.path.exists(d):
            return
        fs = sorted(glob.glob(os.path.join(d, '*.docx')))
        items = [
            {
                'id': os.path.abspath(p),
                'title': os.path.splitext(os.path.basename(p))[0],
                'author': '',
                'pages': 0,
                'progress': 0.0
            }
            for p in fs
        ]
        self.js(f"window.setLibrary({json.dumps(items)})")

    def _push_bookmarks(self):
        bms = [
            {
                'bookId': b['path'],
                'title': os.path.splitext(os.path.basename(b['path']))[0],
                'page': b.get('page_num', 1),
                'date': ''
            }
            for b in self.bookmarks
            if 'path' in b
        ]
        self.js(f"window.setBookmarks({json.dumps(bms)})")

    def setup_menu(self):
        bar = self.menuBar()

        def add_action(menu, text, slot, shortcut=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            menu.addAction(act)

        f_menu = bar.addMenu("File")
        add_action(f_menu, "Open", self.open_file, "Ctrl+O")
        add_action(f_menu, "Exit", self.close, "Ctrl+Q")

        o_menu = bar.addMenu("Options")
        add_action(o_menu, "Preferences", self.open_options, "Ctrl+P")
        add_action(o_menu, "Bookmarks", self.open_bookmarks, "Ctrl+B")
        add_action(o_menu, "Reset History", self.reset_session)

    def handle_action(self, action):
        if QApplication.activeWindow() is None:
            return
        if QApplication.activeModalWidget():
            return
        action_map = {
            "nav_next_page":    lambda: self.js("window.jumpPages(1)"),
            "nav_prev_page":    lambda: self.js("window.jumpPages(-1)"),
            "nav_jump_fwd_5":   lambda: self.js("window.jumpPages(5)"),
            "nav_jump_back_5":  lambda: self.js("window.jumpPages(-5)"),
            "nav_bookmark":     self.add_bookmark,
            "nav_next_story":   self.next_file,
            "nav_random_story": self.random_file,
        }
        if action in action_map:
            action_map[action]()

    def js(self, code, cb=None):
        if self.web.page():
            if cb:
                self.web.page().runJavaScript(code, cb)
            else:
                self.web.page().runJavaScript(code)

    def _check_js_action(self):
        self.js(
            "(function(){ const a=window._pendingAction; window._pendingAction=null; return a; })()",
            self._handle_js_action
        )

    def _handle_js_action(self, action):
        if not action or not isinstance(action, dict):
            return
        t = action.get('type')
        if t == 'openBook':
            path = action.get('id', '')
            if path and os.path.exists(path):
                self.load_file(path)
        elif t == 'openFile':
            self.open_file()
        elif t == 'addBookmark':
            self._save_bm_from_js(action.get('page', 1))
        elif t == 'delBookmark':
            self._del_bm_by_page(action.get('bookId'), action.get('page'))
        elif t == 'jumpBookmark':
            path = action.get('bookId', '')
            page = action.get('page', 1)
            if path and os.path.exists(path):
                self.load_file(path, page)
        elif t == 'openPrefs':
            self.open_options()

    def _save_bm_from_js(self, page_num):
        if not self.curr_path:
            return
        entry = {
            "path": self.curr_path,
            "page_num": page_num,
            "display_page": str(page_num)
        }
        self.bookmarks = [b for b in self.bookmarks if b.get('path') != self.curr_path]
        self.bookmarks.insert(0, entry)
        save_json(BOOKMARKS_FILE, self.bookmarks)

    def _del_bm_by_page(self, book_id, page):
        self.bookmarks = [
            b for b in self.bookmarks
            if not (b.get('path') == book_id and b.get('page_num') == page)
        ]
        save_json(BOOKMARKS_FILE, self.bookmarks)

    def load_file(self, path, page_num=1):
        if not path or not os.path.exists(path):
            return
        self.curr_path = path
        self.setWindowTitle(f"Story Reader \u2014 {os.path.basename(path)}")
        try:
            with open(path, "rb") as f:
                raw_html = mammoth.convert_to_html(f).value
            chapters = self._extract_chapters(raw_html)
            book_id = os.path.abspath(path)
            title = os.path.splitext(os.path.basename(path))[0]
            chapters_json = json.dumps(chapters)
            raw_json = json.dumps(raw_html)
            title_json = json.dumps(title)
            book_id_json = json.dumps(book_id)
            self.js(
                f"window.loadBookFromHtml({book_id_json}, {title_json}, {raw_json}, {chapters_json}, {page_num})"
            )
            self.loaded_stories.add(os.path.abspath(path))
            self.save_session()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _extract_chapters(self, html):
        roman = [
            'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
            'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX'
        ]
        titles = re.findall(r'<h[123][^>]*>(.*?)</h[123]>', html, re.I | re.S)
        titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles]
        return [
            {"num": roman[i] if i < len(roman) else str(i + 1), "title": t, "start": 1}
            for i, t in enumerate(titles)
        ]

    def add_bookmark(self):
        if not self.curr_path:
            return
        self.js("window.getInfo()", self._save_bm)

    def _save_bm(self, info):
        if not info:
            return
        page_num = int(info[1]) if isinstance(info, list) and len(info) > 1 else 1
        self._save_bm_from_js(page_num)
        self.js(f"toast('Bookmarked page {page_num}')")

    def open_bookmarks(self):
        dlg = BookmarksDialog(
            self,
            self.bookmarks,
            lambda bm: self.load_file(bm['path'], bm.get('page_num', 1)),
            lambda idx: self._del_bm(idx)
        )
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
            self._push_library()

    def update_bindings(self):
        self.bridge.update_bindings(self.config.get("bindings", DEFAULT_BINDINGS))

    def auto_load(self):
        if self.last_file and os.path.exists(self.last_file):
            self.load_file(self.last_file)
            return
        d = self.config.get("default_folder", "")
        if d and os.path.exists(d):
            fs = sorted(glob.glob(os.path.join(d, "*.docx")))
            if fs:
                self.load_file(fs[0])

    def open_file(self):
        default_dir = self.config.get("default_folder", "")
        f, _ = QFileDialog.getOpenFileName(self, "Open", default_dir, "Word (*.docx)")
        if f:
            self.load_file(f)

    def next_file(self):
        self._cycle_file(1)

    def _cycle_file(self, delta):
        d = self.config.get("default_folder", "")
        if not d or not os.path.exists(d):
            return
        fs = sorted(glob.glob(os.path.join(d, "*.docx")), key=lambda s: s.lower())
        if not fs:
            return
        try:
            curr = next(
                i for i, f in enumerate(fs)
                if os.path.abspath(f) == os.path.abspath(self.curr_path)
            ) if self.curr_path else -1
            self.load_file(fs[(curr + delta) % len(fs)])
        except StopIteration:
            self.load_file(fs[0 if delta > 0 else -1])

    def random_file(self):
        d = self.config.get("default_folder", "")
        if not d:
            return
        fs = glob.glob(os.path.join(d, "*.docx"))
        if fs:
            import random
            self.load_file(random.choice(fs))

    def load_session(self):
        session = load_json(SESSION_FILE)
        self.loaded_stories = set(session.get("loaded", []))
        self.last_file = session.get("last_file", None)

    def save_session(self):
        save_json(SESSION_FILE, {
            "loaded": list(self.loaded_stories),
            "last_file": self.curr_path
        })

    def reset_session(self):
        self.loaded_stories = set()
        self.save_session()

    def cleanup_session(self):
        session = load_json(SESSION_FILE)
        save_json(SESSION_FILE, {
            "loaded": [],
            "last_file": session.get("last_file")
        })

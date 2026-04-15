import os
import mouse
import keyboard
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QWidget, QTabWidget, 
                             QScrollArea, QListWidget, QListWidgetItem, QFileDialog)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer

class InputRecorder(QObject):
    sig_input_detected = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.listening = False
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._attach_hooks)

    def start(self):
        if self.listening: return
        self.listening = True
        self._timer.start(250) 

    def stop(self):
        self.listening = False
        self._timer.stop() 
        try:
            mouse.unhook(self._on_mouse)
            keyboard.unhook(self._on_key)
        except: pass

    def _attach_hooks(self):
        if not self.listening: return
        try:
            mouse.hook(self._on_mouse)
            keyboard.hook(self._on_key)
        except: self.stop()

    def _on_mouse(self, event):
        if not self.listening: return
        det = None
        if isinstance(event, mouse.WheelEvent):
            det = "wheel_up" if event.delta > 0 else "wheel_down"
        elif isinstance(event, mouse.ButtonEvent) and event.event_type == 'up':
            btn = str(event.button).lower()
            # --- FIX: Ignore Left Click during recording ---
            if btn == 'left': return 
            det = btn
            
        if det:
            self.stop()
            self.sig_input_detected.emit(det)

    def _on_key(self, event):
        if not self.listening: return
        if event.event_type == 'down':
            if event.name in ['ctrl', 'shift', 'alt']: return
            self.stop()
            self.sig_input_detected.emit(event.name)

class KeyCaptureButton(QPushButton):
    def __init__(self, target_edit):
        super().__init__("Record Key")
        self.setCheckable(True)
        self.target = target_edit
        self.recorder = InputRecorder()
        self.recorder.sig_input_detected.connect(self.on_input)
        self.clicked.connect(self.toggle)
        self.setStyleSheet("QPushButton:checked { background-color: #d9534f; color: white; }")

    def toggle(self):
        if self.isChecked():
            self.setText("Press Input...")
            self.recorder.start()
        else:
            self.reset()
    
    def on_input(self, text):
        self.target.setText(text)
        self.reset()
        
    def reset(self):
        self.recorder.stop()
        self.setChecked(False)
        self.setText("Record Key")

class OptionsDialog(QDialog):
    def __init__(self, parent, folder, bindings):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(600, 500)
        self.bindings = bindings.copy()
        
        main = QVBoxLayout(self)
        tabs = QTabWidget()
        
        # General
        gen_tab = QWidget()
        gen_lay = QVBoxLayout(gen_tab)
        
        row = QHBoxLayout()
        self.f_input = QLineEdit(folder)
        btn_br = QPushButton("Browse...")
        btn_br.clicked.connect(self.browse)
        row.addWidget(QLabel("Default Folder:"))
        row.addWidget(self.f_input)
        row.addWidget(btn_br)
        
        gen_lay.addLayout(row)
        gen_lay.addStretch()
        
        # Keys
        key_tab = QWidget()
        key_lay = QVBoxLayout(key_tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        s_widget = QWidget()
        form = QVBoxLayout(s_widget)
        
        names = {
            "nav_next_page": "Next Page", "nav_prev_page": "Prev Page",
            "nav_next_story": "Next Story", "nav_random_story": "Random Story",
            "nav_bookmark": "Bookmark", 
            "nav_jump_fwd_5": "+5 Pages", "nav_jump_back_5": "-5 Pages"
        }
        
        for act, nice_name in names.items():
            r = QHBoxLayout()
            lbl = QLabel(nice_name)
            lbl.setMinimumWidth(120)
            edit = QLineEdit(self.bindings.get(act, ""))
            edit.textChanged.connect(lambda t, a=act: self.bindings.update({a: t}))
            btn = KeyCaptureButton(edit)
            r.addWidget(lbl)
            r.addWidget(edit)
            r.addWidget(btn)
            form.addLayout(r)
            
        scroll.setWidget(s_widget)
        key_lay.addWidget(scroll)
        
        tabs.addTab(gen_tab, "General")
        tabs.addTab(key_tab, "Bindings")
        main.addWidget(tabs)
        
        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cncl = QPushButton("Cancel")
        cncl.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cncl)
        main.addLayout(btns)
        
    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Folder")
        if d: self.f_input.setText(d)
    
    def get_results(self): return self.f_input.text(), self.bindings

class BookmarksDialog(QDialog):
    def __init__(self, parent, bookmarks, on_load, on_del):
        super().__init__(parent)
        self.setWindowTitle("Bookmarks")
        self.resize(500, 400)
        self.bms = bookmarks
        self.on_load = on_load
        self.on_del = on_del
        
        lay = QVBoxLayout(self)
        self.lst = QListWidget()
        self.refresh()
        self.lst.itemDoubleClicked.connect(self.load)
        lay.addWidget(self.lst)
        
        btns = QHBoxLayout()
        b_load = QPushButton("Load")
        b_load.clicked.connect(self.load)
        b_del = QPushButton("Delete")
        b_del.clicked.connect(self.delete)
        b_cls = QPushButton("Close")
        b_cls.clicked.connect(self.reject)
        btns.addWidget(b_load)
        btns.addWidget(b_del)
        btns.addWidget(b_cls)
        lay.addLayout(btns)
        
    def refresh(self):
        self.lst.clear()
        for i, b in enumerate(self.bms):
            name = os.path.basename(b['path'])
            try: pg = b.get('display_page', '?')
            except: pg = "?"
            item = QListWidgetItem(f"{name} (Page {pg})")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.lst.addItem(item)
            
    def load(self):
        if self.lst.currentItem():
            idx = self.lst.currentItem().data(Qt.ItemDataRole.UserRole)
            self.on_load(self.bms[idx])
            self.accept()
            
    def delete(self):
        if self.lst.currentItem():
            idx = self.lst.currentItem().data(Qt.ItemDataRole.UserRole)
            self.on_del(idx)
            self.refresh()
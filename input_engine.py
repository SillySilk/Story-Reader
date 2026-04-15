import time
import keyboard
import mouse
from PyQt6.QtCore import QObject, pyqtSignal

class Debouncer:
    def __init__(self, interval=0.08):
        self.interval = interval
        self.last_call = 0
    def can_run(self):
        now = time.time()
        if now - self.last_call >= self.interval:
            self.last_call = now
            return True
        return False

class ActionCooldown:
    def __init__(self, cooldown=0.4):
        self.cooldown = cooldown
        self.last = 0
    def is_ready(self):
        now = time.time()
        if now - self.last >= self.cooldown:
            self.last = now
            return True
        return False

class InputBridge(QObject):
    sig_trigger_action = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.scroll_debouncer = Debouncer(0.08)
        self.action_cooldown = ActionCooldown(0.4)
        self.action_map = {}
        
        try:
            mouse.hook(self._global_mouse_handler)
        except Exception as e:
            print(f"Mouse Error: {e}")

    def update_bindings(self, new_bindings):
        try:
            keyboard.unhook_all()
        except: pass

        self.action_map = {}
        for action, key in new_bindings.items():
            if not key: continue
            key = key.lower().strip()
            
            # --- FIX: SAFETY BLOCK ---
            # Never allow Left Click to be a binding, or you can't click menus!
            if key == 'left': continue 
            
            self.action_map[key] = action
            
            if key not in ['wheel_up', 'wheel_down', 'left', 'right', 'middle', 'x', 'x2']:
                clean = self._normalize(key)
                try:
                    keyboard.add_hotkey(clean, lambda a=action: self._attempt_trigger(a), suppress=False)
                except: pass

    def _attempt_trigger(self, action_name):
        if self.action_cooldown.is_ready():
            self.sig_trigger_action.emit(action_name)

    def _global_mouse_handler(self, event):
        trigger = None
        if isinstance(event, mouse.WheelEvent):
            if not self.scroll_debouncer.can_run(): return
            trigger = "wheel_up" if event.delta > 0 else "wheel_down"
        elif isinstance(event, mouse.ButtonEvent) and event.event_type == 'up':
            trigger = str(event.button).lower()

        # --- FIX: SAFETY BLOCK ---
        if trigger == 'left': return

        if trigger and trigger in self.action_map:
            self._attempt_trigger(self.action_map[trigger])

    def _normalize(self, key):
        mapping = {"pgup": "page up", "pgdown": "page down", "return": "enter", "del": "delete"}
        return mapping.get(key, key)
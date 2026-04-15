import os
import json
import tempfile

DEFAULT_BINDINGS = {
    "nav_next_page": "wheel_down",
    "nav_prev_page": "wheel_up",
    "nav_next_story": "N",
    "nav_random_story": "R",
    "nav_bookmark": "B",
    "nav_jump_fwd_5": "Down",
    "nav_jump_back_5": "Up"
}

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".story_reader_config.json")
BOOKMARKS_FILE = os.path.join(os.path.expanduser("~"), ".story_reader_bookmarks.json")
SESSION_FILE = os.path.join(tempfile.gettempdir(), ".story_reader_session.json")

def load_json(path, default=None):
    if default is None: default = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w') as f: json.dump(data, f, indent=2)
    except: pass
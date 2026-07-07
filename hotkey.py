"""Global system-wide push-to-talk hotkey via pynput.

Supports key combinations (e.g. "ctrl+shift+d", "alt+f8", "f8") that fire even
when the browser / any other app has focus, AND mouse buttons
("mouse_left", "mouse_middle", "mouse_right", "mouse_x1", "mouse_x2") — handy
for a thumb/side button on a gaming mouse. Combos may mix keyboard modifiers
with a mouse button (e.g. "ctrl+mouse_x1"). Reconfigurable and toggleable at
runtime from the web UI.

On Windows the native action of a side button that is part of the active combo
is absorbed (via pynput's win32_event_filter) so e.g. Mouse 4 doesn't also
navigate the browser back/forward. Left/right/middle are never suppressed
(that would block normal clicking).

Note: keyboard events are observed but not suppressed, so a keyboard combo may
still reach the focused app. Prefer a combo that doesn't collide with shortcuts
in the apps you use (a modifier + letter/special key works well).
"""
import asyncio
import sys
import threading

try:
    from pynput import keyboard, mouse
    _AVAILABLE = True
except Exception:  # pynput not installed
    keyboard = None
    mouse = None
    _AVAILABLE = False


_MOD_ALIASES = {"control": "ctrl", "super": "cmd", "meta": "cmd",
                "win": "cmd", "option": "alt", "command": "cmd"}
_SPECIAL = {
    "space": "space", "spacebar": "space",
    "enter": "enter", "return": "enter",
    "tab": "tab", "escape": "esc", "esc": "esc",
    "pause": "pause", "break": "pause",
    "insert": "insert", "home": "home", "end": "end",
    "pageup": "pageup", "page_up": "pageup",
    "pagedown": "pagedown", "page_down": "pagedown",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "backspace": "backspace", "delete": "delete",
    "capslock": "capslock", "caps_lock": "capslock",
    "scrolllock": "scrolllock", "scroll_lock": "scrolllock",
    "numlock": "numlock", "num_lock": "numlock",
}

# pynput mouse.Button -> canonical token. Built only if pynput imported.
_MOUSE_BUTTON_TO_TOKEN = {}
if mouse is not None:
    _MOUSE_BUTTON_TO_TOKEN = {
        mouse.Button.left: "mouse_left",
        mouse.Button.middle: "mouse_middle",
        mouse.Button.right: "mouse_right",
        mouse.Button.x1: "mouse_x1",
        mouse.Button.x2: "mouse_x2",
    }
# Side buttons whose native action is safe (and desirable) to absorb.
_SUPPRESSIBLE_MOUSE = {"mouse_x1", "mouse_x2"}


def is_available() -> bool:
    return _AVAILABLE


def _canonical(token: str) -> str:
    token = token.strip().lower()
    token = _MOD_ALIASES.get(token, token)
    token = _SPECIAL.get(token, token)
    if len(token) >= 2 and token[0] == "f" and token[1:].isdigit():  # f1..f24
        return token
    return token


def normalize_combo(spec: str) -> set:
    """'Ctrl+Shift+D' -> {'ctrl', 'shift', 'd'}; 'mouse_x1' -> {'mouse_x1'}."""
    if not spec:
        return set()
    return {_canonical(t) for t in spec.split("+") if t.strip()}


def _key_to_token(key):
    """Map a pynput key to a canonical token, or None if unusable."""
    if isinstance(key, keyboard.KeyCode):
        ch = key.char
        if ch and len(ch) == 1 and ch.isalnum():
            return ch.lower()
        vk = getattr(key, "vk", None)
        if vk is not None:
            try:
                c = chr(int(vk))
                if c.isalnum():
                    return c.lower()
            except (ValueError, TypeError):
                pass
        return None
    name = getattr(key, "name", None)
    if name is None:
        return None
    if name in ("ctrl_l", "ctrl_r"):
        return "ctrl"
    if name in ("alt_l", "alt_r"):
        return "alt"
    if name in ("shift_l", "shift_r"):
        return "shift"
    if name in ("cmd_l", "cmd_r"):
        return "cmd"
    return _canonical(name)


def _mouse_button_to_token(button):
    """Map a pynput mouse.Button to a canonical token, or None if unusable."""
    return _MOUSE_BUTTON_TO_TOKEN.get(button)


class HotkeyListener:
    def __init__(self, loop, on_press, on_release, combo="f8", enabled=True):
        self.loop = loop
        self.on_press = on_press
        self.on_release = on_release
        self.combo_str = (combo or "f8").strip()
        self.combo = normalize_combo(self.combo_str)
        self.enabled = bool(enabled)
        self._pressed = set()
        self._active = False
        self._listeners = []          # running pynput listeners (keyboard + mouse)
        self._mouse_listener = None   # ref for suppress_event() in the win32 filter
        self._lock = threading.RLock()

    def state(self):
        return {"enabled": self.enabled and bool(self.combo), "key": self.combo_str or None}

    # -- lifecycle --------------------------------------------------------
    def start(self):
        if not self.enabled or self._listeners or not self.combo:
            return
        listeners = []
        # Keyboard listener (also tracks modifiers for mixed combos).
        kb = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        kb.daemon = True
        listeners.append(kb)
        # Mouse listener; on Windows attach a filter to absorb side-button native actions.
        mouse_kwargs = {"on_click": self._on_click}
        if sys.platform == "win32":
            mouse_kwargs["win32_event_filter"] = self._win32_filter
        ms = mouse.Listener(**mouse_kwargs)
        ms.daemon = True
        listeners.append(ms)
        self._mouse_listener = ms
        self._listeners = listeners
        for l in listeners:
            l.start()

    def stop(self):
        listeners = self._listeners
        self._listeners = []
        self._mouse_listener = None
        for l in listeners:
            try:
                l.stop()
            except Exception:
                pass
        was_active = self._active
        self._active = False
        self._pressed.clear()
        if was_active:
            asyncio.run_coroutine_threadsafe(self.on_release(), self.loop)

    def reconfigure(self, combo_str):
        enabled = self.enabled
        self.stop()
        self.combo_str = (combo_str or "").strip()
        self.combo = normalize_combo(self.combo_str)
        self._active = False
        if enabled:
            self.start()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if self.enabled:
            self.start()
        else:
            self.stop()

    # -- pynput callbacks (run in pynput's threads) -----------------------
    def _press(self):
        if not self._active:
            self._active = True
            asyncio.run_coroutine_threadsafe(self.on_press(), self.loop)

    def _on_press(self, key):
        token = _key_to_token(key)
        if token is None:
            return
        with self._lock:
            self._pressed.add(token)
            if self.combo and self.combo.issubset(self._pressed):
                self._press()

    def _on_release(self, key):
        token = _key_to_token(key)
        if token is None:
            return
        with self._lock:
            self._pressed.discard(token)
            if self._active and token in self.combo:
                self._active = False
                asyncio.run_coroutine_threadsafe(self.on_release(), self.loop)

    def _on_click(self, x, y, button, pressed):
        token = _mouse_button_to_token(button)
        if token is None:
            return
        with self._lock:
            if pressed:
                self._pressed.add(token)
                if self.combo and self.combo.issubset(self._pressed):
                    self._press()
            else:
                self._pressed.discard(token)
                if self._active and token in self.combo:
                    self._active = False
                    asyncio.run_coroutine_threadsafe(self.on_release(), self.loop)

    def _win32_filter(self, msg, data):
        """Absorb the native action of combo side buttons (mouse 4/5); leave
        everything else (incl. left/right/middle) untouched. Returning True keeps
        the listener running."""
        try:
            button = getattr(data, "button", None)
        except Exception:
            return True
        if button is None:
            return True
        token = _MOUSE_BUTTON_TO_TOKEN.get(button)
        if token in _SUPPRESSIBLE_MOUSE and token in self.combo and self._mouse_listener is not None:
            self._mouse_listener.suppress_event()
        return True

"""Star Citizen Dashboard companion.

Run this on the Windows PC that plays Star Citizen. It serves the touch
dashboard to your iPad over the local network and turns button presses into
keyboard input for the game (DirectInput scan codes via SendInput).

Usage:  python sc_companion.py [--port 8770] [--dry-run]

Only the Python standard library is used.
"""

import argparse
import ctypes
import json
import math
import os
import queue
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.0.0-dev"  # set from the release tag when the installer is built
IS_WINDOWS = sys.platform == "win32"
# App files ship with the program (read only once installed); your settings live in DATA_DIR
# so installing an update never touches them.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(HERE, "web")
DEFAULT_BINDS_PATH = os.path.join(HERE, "keybinds.json")
DATA_DIR = os.environ.get("SC_DASH_DATA") or (
    os.path.join(os.environ["APPDATA"], "SC Dashboard") if os.environ.get("APPDATA") else
    os.path.join(os.path.expanduser("~"), ".sc-dashboard"))
BINDS_PATH = os.path.join(DATA_DIR, "keybinds.json")
SHIP_CACHE_PATH = os.path.join(DATA_DIR, "ship_cache_v2.json")
LOG_CANDIDATES = [
    r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log",
    r"D:\Roberts Space Industries\StarCitizen\LIVE\Game.log",
    r"C:\Roberts Space Industries\StarCitizen\LIVE\Game.log",
    r"D:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log",
    r"E:\Roberts Space Industries\StarCitizen\LIVE\Game.log",
]
MANUFACTURERS = {
    "AEGS": "Aegis", "ANVL": "Anvil", "DRAK": "Drake", "ORIG": "Origin", "RSI": "RSI",
    "CRUS": "Crusader", "MISC": "MISC", "ARGO": "Argo", "CNOU": "C.O.", "ESPR": "Esperia",
    "BANU": "Banu", "KRIG": "Kruger", "MRAI": "Mirai", "GAMA": "Gatac", "TMBL": "Tumbril",
    "XIAN": "Aopoa", "XNAA": "Aopoa", "GRIN": "Greycat", "VNCL": "Vanduul", "AOPOA": "Aopoa",
}

# Set-1 scan codes. A value >= 0x100 marks an extended key (E0 prefix).
SCAN = {
    "esc": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B, "minus": 0x0C,
    "equals": 0x0D, "backspace": 0x0E, "tab": 0x0F, "q": 0x10, "w": 0x11,
    "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16, "i": 0x17,
    "o": 0x18, "p": 0x19, "lbracket": 0x1A, "rbracket": 0x1B, "enter": 0x1C,
    "lctrl": 0x1D, "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
    "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26, "semicolon": 0x27,
    "apostrophe": 0x28, "grave": 0x29, "lshift": 0x2A, "backslash": 0x2B,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31,
    "m": 0x32, "comma": 0x33, "period": 0x34, "slash": 0x35, "rshift": 0x36,
    "np*": 0x37, "lalt": 0x38, "space": 0x39, "capslock": 0x3A,
    "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F, "f6": 0x40,
    "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44, "f11": 0x57, "f12": 0x58,
    "np7": 0x47, "np8": 0x48, "np9": 0x49, "np-": 0x4A, "np4": 0x4B,
    "np5": 0x4C, "np6": 0x4D, "np+": 0x4E, "np1": 0x4F, "np2": 0x50,
    "np3": 0x51, "np0": 0x52, "np.": 0x53,
    "npenter": 0x11C, "rctrl": 0x11D, "np/": 0x135, "ralt": 0x138,
    "home": 0x147, "up": 0x148, "pgup": 0x149, "left": 0x14B, "right": 0x14D,
    "end": 0x14F, "down": 0x150, "pgdn": 0x151, "insert": 0x152, "delete": 0x153,
}
MODIFIERS = {"lalt", "ralt", "lctrl", "rctrl", "lshift", "rshift"}
# Mouse buttons (down flag, up flag) and wheel notches, usable in combos like lalt+lmb.
MOUSE_BUTTONS = {"lmb": (0x0002, 0x0004), "rmb": (0x0008, 0x0010), "mmb": (0x0020, 0x0040)}
MOUSE_WHEEL = {"wheelup": 120, "wheeldown": -120}

# ---------------------------------------------------------------- input ----

if IS_WINDOWS:
    from ctypes import wintypes

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    INPUT_KEYBOARD = 1
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)

    def _key(code, up):
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        if code >= 0x100:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(0, code & 0xFF, flags, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    INPUT_MOUSE = 0
    MOUSEEVENTF_WHEEL = 0x0800

    def _mouse(name, up):
        inp = INPUT(type=INPUT_MOUSE)
        if name in MOUSE_WHEEL:
            if up:
                return
            inp.u.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(MOUSE_WHEEL[name]).value, MOUSEEVENTF_WHEEL, 0, 0)
        else:
            inp.u.mi = MOUSEINPUT(0, 0, 0, MOUSE_BUTTONS[name][1 if up else 0], 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def foreground_title():
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
else:
    def _key(code, up):
        pass

    def _mouse(name, up):
        pass

    def foreground_title():
        return ""


SOUNDS_DIR = os.path.join(WEB_DIR, "sounds")


class SoundPlayer:
    """Plays the dashboard's sounds through the PC's speakers.

    Uses Windows MCI so several sounds can overlap and follow the dashboard's
    volume; falls back to winsound (one sound at a time) if MCI refuses.
    """

    CHANNELS = 6

    def __init__(self):
        self.q = queue.Queue()
        self.n = 0
        threading.Thread(target=self._run, daemon=True).start()

    def play(self, name, volume):
        path = os.path.join(SOUNDS_DIR, name + ".wav")
        if re.fullmatch(r"[a-z_]+", name or "") and os.path.exists(path):
            self.q.put((path, max(0.0, min(1.0, float(volume)))))
            return True
        return False

    def _run(self):
        if not IS_WINDOWS:
            while True:
                path, vol = self.q.get()
                print(f"  sound {os.path.basename(path)} at {int(vol * 100)}%  [not on Windows, not played]")
        mci = ctypes.windll.winmm.mciSendStringW
        mci.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p)
        import winsound
        while True:
            path, vol = self.q.get()
            alias = f"scdash{self.n % self.CHANNELS}"
            self.n += 1
            mci(f"close {alias}", None, 0, None)
            if mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None) == 0:
                mci(f"setaudio {alias} volume to {int(vol * 1000)}", None, 0, None)
                mci(f"play {alias}", None, 0, None)
            else:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


class KeySender:
    """Sends key combos one at a time on a worker thread so taps never overlap."""

    def __init__(self, dry_run):
        self.dry_run = dry_run or not IS_WINDOWS
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, combo, mode, hold_ms, count, label):
        self.q.put((combo, mode, hold_ms, count, label))

    def _run(self):
        while True:
            combo, mode, hold_ms, count, label = self.q.get()
            try:
                for i in range(count):
                    if mode == "down":  # latched: stays pressed until an "up"
                        self._down(combo)
                        break
                    if mode == "up":
                        self._up(combo)
                        break
                    if mode == "double":
                        self._press(combo, 40)
                        time.sleep(0.08)
                        self._press(combo, 40)
                    elif mode == "hold":
                        self._press(combo, hold_ms)
                    else:
                        self._press(combo, 45)
                    time.sleep(0.07)
                print(f"  sent {label}: {combo} ({mode}{' x%d' % count if count > 1 else ''})"
                      + ("  [dry run]" if self.dry_run else ""))
            except Exception as e:  # keep the worker alive
                print("  send failed:", e)

    @staticmethod
    def _send(k, up):
        if k in SCAN:
            _key(SCAN[k], up)
        else:
            _mouse(k, up)

    def _down(self, combo):
        mods = [k for k in combo if k in MODIFIERS]
        for k in mods + [k for k in combo if k not in MODIFIERS]:
            self._send(k, False)
            time.sleep(0.015)

    def _up(self, combo):
        mods = [k for k in combo if k in MODIFIERS]
        for k in reversed(mods + [k for k in combo if k not in MODIFIERS]):
            self._send(k, True)
            time.sleep(0.015)

    def _press(self, combo, hold_ms):
        self._down(combo)
        time.sleep(hold_ms / 1000)
        self._up(combo)


def parse_combo(text):
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    bad = [p for p in parts if p not in SCAN and p not in MOUSE_BUTTONS and p not in MOUSE_WHEEL]
    if bad:
        raise ValueError("unknown key: " + ", ".join(bad))
    return parts


# ---------------------------------------------------------- ship detect ----

# When you board a ship, Star Citizen joins you to the ship's chat channel and
# logs it, e.g. "You have joined channel 'RSI Hermes : PlayerName'". Leaving the
# ship logs "You have left the channel '...'". (Checked against 4.x logs.)
JOIN_RE = re.compile(r"You have joined channel '(.+?) : [^']*'")
LEAVE_RE = re.compile(r"You have left the channel '(.+?) : [^']*'")
MAKER_NAMES = {
    "Aegis": "AEGS", "Anvil": "ANVL", "Drake": "DRAK", "Origin": "ORIG", "RSI": "RSI", "Crusader": "CRUS",
    "MISC": "MISC", "Argo": "ARGO", "Consolidated Outland": "CNOU", "C.O.": "CNOU", "Esperia": "ESPR",
    "Banu": "BANU", "Kruger": "KRIG", "Mirai": "MRAI", "Gatac": "GAMA", "Tumbril": "TMBL", "Aopoa": "XIAN",
    "Greycat": "GRIN", "Grey's": "GRIN",
}


# Arena Commander and other spawn-in-ship modes don't join a ship channel. The
# player's ship is the vehicle spawned between these two respawn steps.
SPAWN_STEP_RE = re.compile(r"SpawnStateTransition>.*?next:(SpawnVehicle|ReviveInVehicle)")
VEHICLE_SPAWN_RE = re.compile(r"OnVehicleSpawned \d+ \(([A-Za-z0-9_]+?)_\d+\)")
TOKEN_RELEASE_RE = re.compile(r"releasing control token for '([A-Za-z0-9_]+?)_\d+'")
LEVEL_LOAD_RE = re.compile(r"=+ Loading level ")
# Who you are, and the lines that mean you died or your ship blew up (self destruct included).
HANDLE_RE = re.compile(r"User Login Success - Handle\[([^\]]+)\]|nickname=\"([^\"]+)\"")
DEATH_RE = re.compile(r"<Actor Death> CActor::Kill: '([^']+)'")
VEHICLE_DESTROY_RE = re.compile(r"<Vehicle Destruction>.*?Vehicle '([A-Za-z0-9_]+?)_\d+'.*?destroy level \d+ to (\d+)")
RESPAWN_RE = re.compile(r"ScheduleRespawn> .*?player:(\S+)")
MAKER_CODES = {}
for _maker, _code in MAKER_NAMES.items():
    MAKER_CODES.setdefault(_code, _maker)


def class_to_name(cls):
    """KRIG_L22_AlphaWolf -> ('KRIG', 'Kruger L22 Alpha Wolf', 'L22 Alpha Wolf')."""
    code, *rest = cls.split("_")
    model = " ".join(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p) for p in rest)
    return code, (MAKER_CODES.get(code, code) + " " + model).strip(), model


def split_maker(name):
    for maker, code in sorted(MAKER_NAMES.items(), key=lambda kv: -len(kv[0])):
        if name == maker or name.startswith(maker + " "):
            return code, name[len(maker):].strip()
    return "", name


class ShipWatcher:
    """Follows Game.log and keeps track of the ship you're aboard."""

    def __init__(self, log_path):
        self.path = log_path or next((p for p in LOG_CANDIDATES if os.path.exists(p)), None)
        self.ship = None
        self.spawning = False  # None while waiting for our spawned vehicle, else False
        self.handle = None  # your in-game name, read from the login line
        self.lives = 0  # bumped on death, so a respawned ship starts from its default pips
        self.cache = {}
        try:
            with open(SHIP_CACHE_PATH, encoding="utf-8") as f:
                self.cache = json.load(f)
        except Exception:
            pass
        if self.path:
            threading.Thread(target=self._follow, daemon=True).start()

    @property
    def active(self):
        return bool(self.path) and os.path.exists(self.path)

    def _gone(self, why):
        if self.ship:
            print(f"  ship: {why}, cleared " + self.ship["name"])
            self.lives += 1
        self.ship = None

    def _line(self, line):
        m = HANDLE_RE.search(line)
        if m:
            self.handle = m.group(1) or m.group(2)
            return
        m = DEATH_RE.search(line)
        if m:
            if m.group(1) == self.handle:
                self._gone("you died")
            return
        m = VEHICLE_DESTROY_RE.search(line)
        if m:
            # level 1 = disabled, 2 = blown apart
            if self.ship and self.ship["class"] == m.group(1) and int(m.group(2)) >= 2:
                self._gone("ship destroyed")
            return
        m = RESPAWN_RE.search(line)
        if m:
            # Arena Commander schedules a respawn when you die; spawning a new ship sets it again.
            if m.group(1) == self.handle and self.spawning is not None:
                self._gone("respawning")
            return
        m = SPAWN_STEP_RE.search(line)
        if m:
            if m.group(1) == "SpawnVehicle":
                self.spawning = None
            elif self.spawning:
                code, name, model = class_to_name(self.spawning)
                if not self.ship or self.ship["class"] != self.spawning:
                    self.ship = self._info(self.spawning, code, model, name)
                    print(f"  ship: {name}")
                self.spawning = False
            return
        m = VEHICLE_SPAWN_RE.search(line)
        if m:
            if self.spawning is None:
                self.spawning = m.group(1)
            return
        m = TOKEN_RELEASE_RE.search(line)
        if m and self.ship and self.ship["class"] == m.group(1):
            print("  ship: left " + self.ship["name"])
            self.ship = None
            return
        if LEVEL_LOAD_RE.search(line):
            self.ship, self.spawning = None, False
            return
        m = JOIN_RE.search(line)
        if m:
            code, model = split_maker(m.group(1))
            if code and (not self.ship or self.ship["class"] != m.group(1)):
                self.ship = self._info(m.group(1), code, model)
                print(f"  ship: {self.ship['name']}")
            return
        m = LEAVE_RE.search(line)
        if m and self.ship and self.ship["class"] == m.group(1):
            print("  ship: left " + m.group(1))
            self.ship = None

    def _follow(self):
        pos, inode = 0, None
        first = True
        while True:
            try:
                st = os.stat(self.path)
                if st.st_size < pos or (inode and st.st_ino != inode):
                    pos, self.ship = 0, None  # new game session rewrote the log
                inode = st.st_ino
                if first:
                    pos = max(0, st.st_size - 8_000_000)  # catch up on the current session
                    first = False
                if st.st_size > pos:
                    with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(pos)
                        for line in f:
                            self._line(line)
                        pos = f.tell()
            except FileNotFoundError:
                pass
            except Exception as e:
                print("  log read failed:", e)
            time.sleep(0.5)

    def _info(self, name, code, model, display=None):
        info = {"class": name, "name": display or name, "maker": code, "power": None, "life": self.lives}
        if name in self.cache:
            info["power"] = self.cache[name]
        else:
            threading.Thread(target=self._lookup, args=(name, model), daemon=True).start()
        return info

    def _lookup(self, name, model):
        """Fetch the ship's power layout from the community Star Citizen wiki API.

        The wiki is built from the game's own files and updated each patch. It
        gives the power plant size, each system's pip count, and per-component
        limits (coolers, radar, life support, quantum drive)."""
        try:
            data = {}
            # The wiki knows ships by class name (KRIG_L22_AlphaWolf) and by model name.
            for key in dict.fromkeys(k for k in (name, model) if k):
                try:
                    data = wiki_get("vehicles/" + urllib.parse.quote(key))
                    break
                except urllib.error.HTTPError:
                    continue
            power = power_from_wiki(data, lambda uuid: wiki_get("items/" + uuid))
            if not power.get("total"):
                print(f"  no pip data on the wiki for {name}; using your Setup values")
                return
            self.cache[name] = power
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SHIP_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            if self.ship and self.ship["class"] == name:
                self.ship = {**self.ship, "power": power}
            print(f"  ship data for {name}: {power}")
        except Exception as e:
            print(f"  no ship data for {name}: {e}")


def wiki_get(path):
    req = urllib.request.Request("https://api.star-citizen.wiki/api/v2/" + path,
                                 headers={"Accept": "application/json", "User-Agent": "sc-dashboard"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r).get("data", {}) or {}


def power_from_wiki(data, get_item):
    """Turn a wiki vehicle record into the dashboard's power layout:
    {"total": 14, "max": {...}, "min": {...}, "coolers": 2}."""
    pwr = data.get("power") or {}
    grouped = pwr.get("used_segments_grouped") or {}
    out = {"total": pwr.get("generation_segments"), "max": {}, "min": {}}
    for sys_id, key in (("weapons", "WeaponGun"), ("thrusters", "FlightController"), ("shields", "Shield")):
        if grouped.get(key):
            out["max"][sys_id] = math.ceil(grouped[key] - 1e-6)
    items = [it for relay in (data.get("relay_network") or {}).get("relays", []) or []
             for hp in relay.get("connected_hardpoints", []) or [] for it in hp.get("items", []) or []]
    usage_cache = {}

    def usage(it):
        uuid = it.get("uuid")
        if uuid not in usage_cache:
            try:
                u = ((get_item(uuid).get("resource_network") or {}).get("usage") or {}).get("power") or {}
                usage_cache[uuid] = (int(u.get("min") or 0), int(u.get("max") or 0))
            except Exception:
                usage_cache[uuid] = (0, 0)
        return usage_cache[uuid]

    def of_type(*names):
        return [it for it in items if (it.get("type") or "").lower() in names]

    coolers = of_type("cooler")[:4]
    out["coolers"] = len(coolers)
    for i, it in enumerate(coolers):
        lo, hi = usage(it)
        sys_id = "coolers" if i == 0 else f"coolers{i + 1}"
        if hi:
            out["max"][sys_id], out["min"][sys_id] = hi, lo
    for sys_id, names in (("radar", ("radar",)), ("lifesupport", ("lifesupportgenerator", "lifesupport")),
                          ("quantum", ("quantumdrive",))):
        found = of_type(*names)
        if found:
            lo, hi = usage(found[0])
            if hi:
                out["max"][sys_id], out["min"][sys_id] = hi, lo
    tractor = (data.get("power_pools") or {}).get("TractorBeam")
    if isinstance(tractor, dict):
        out["tractor"] = (tractor.get("size") or 0) > 0
    if grouped.get("Radar") and "radar" not in out["max"]:
        out["max"]["radar"] = math.ceil(grouped["Radar"])
    return out


# ------------------------------------------------------------ game binds ----

# Dashboard action -> Star Citizen action name (names checked in a 4.10 actionmaps.xml).
GAME_ACTIONS = {
    "pwr_weapons_toggle": "v_power_toggle_weapons",
    "pwr_shields_toggle": "v_power_toggle_shields",
    "pwr_thrusters_toggle": "v_power_toggle_thrusters",
    "flight_ready": "v_flightready",
    "vtol": "v_vtol_toggle",
    "landing_gear": "v_toggle_landing_system",
    "autoland": "v_autoland",
    "gsafe": "v_ifcs_toggle_gforce_safety",
    "esp": "v_ifcs_toggle_esp",
    "decoupled": "v_ifcs_vector_decoupling_toggle",
    "space_brake": "v_space_brake",
    "lights": "v_lights",
    "doors": "v_toggle_all_doors",
    "lock_doors": "v_toggle_all_doorlocks",
    # from community bind lists; not yet seen in Donn's own actionmaps.xml
    "eject": "v_eject",
    "self_destruct": "v_self_destruct",
}
SC_KEY_NAMES = {"escape": "esc", "np_add": "np+", "np_subtract": "np-", "np_multiply": "np*", "np_divide": "np/",
                "np_enter": "npenter", "np_period": "np.", "pageup": "pgup", "pagedown": "pgdn"}


class GameBinds:
    """Reads keyboard binds you changed in Star Citizen (actionmaps.xml) so the dashboard follows them."""

    def __init__(self, log_path):
        self.path = os.path.join(os.path.dirname(log_path), "user", "client", "0", "Profiles", "default",
                                 "actionmaps.xml") if log_path else None
        self.mtime, self.overrides = None, {}

    def get(self):
        try:
            mt = os.path.getmtime(self.path)
        except Exception:
            return {}
        if mt != self.mtime:
            self.mtime, self.overrides = mt, self._read()
            if self.overrides:
                print(f"  using {len(self.overrides)} keyboard binds from your game settings")
        return self.overrides

    def _read(self):
        import xml.etree.ElementTree as ET
        found = {}
        try:
            root = ET.parse(self.path).getroot()
        except Exception as e:
            print("  could not read actionmaps.xml:", e)
            return {}
        for act in root.iter("action"):
            for rb in act.findall("rebind"):
                inp = rb.get("input") or ""
                m = re.match(r"kb\d+_(.*)", inp)
                if m:
                    found[act.get("name")] = m.group(1).strip()
        out = {}
        for ours, theirs in GAME_ACTIONS.items():
            if theirs not in found:
                continue
            parts = [SC_KEY_NAMES.get(k, re.sub(r"^np_(\d)$", r"np\1", k)) for k in found[theirs].lower().split("+") if k]
            if all(k in SCAN for k in parts):
                out[ours] = "+".join(parts)  # empty means you cleared the keyboard bind in game
        return out


# --------------------------------------------------------------- server ----

GAME_BINDS = None


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def migrate_binds():
    """First run of this version: bring over keybinds saved by an older unzipped copy."""
    if os.path.exists(BINDS_PATH):
        return
    home = os.path.expanduser("~")
    found = [os.path.join(HERE, "keybinds.json")] if not hasattr(sys, "_MEIPASS") else []
    for base in (os.path.join(home, "Desktop"), os.path.join(home, "Downloads"), os.path.join(home, "Documents")):
        for root, dirs, files in os.walk(base):
            if root.count(os.sep) - base.count(os.sep) >= 4:
                dirs[:] = []
            if os.path.basename(root) == "companion" and "keybinds.json" in files and "sc_companion.py" in files:
                found.append(os.path.join(root, "keybinds.json"))
    found = [p for p in found if os.path.exists(p) and os.path.abspath(p) != os.path.abspath(DEFAULT_BINDS_PATH)]
    if not found:
        return
    newest = max(found, key=os.path.getmtime)
    actions = _read_json(newest, {}).get("actions")
    if isinstance(actions, dict):
        save_binds({"actions": actions})
        print(f"  brought over your keybinds from {newest}")


def load_binds():
    """The shipped defaults, with your own changes (saved in DATA_DIR) on top.
    New actions added by an update appear with their default keys."""
    data = _read_json(DEFAULT_BINDS_PATH, {"actions": {}})
    mine = _read_json(BINDS_PATH, {}).get("actions", {})
    for name, act in data.get("actions", {}).items():
        if name in mine:
            act.update({k: v for k, v in mine[name].items() if k in ("keys", "mode", "holdMs")})
    if GAME_BINDS:
        for name, keys in GAME_BINDS.get().items():
            if name in data.get("actions", {}):
                data["actions"][name].update(keys=keys, fromGame=True)
    return data


def save_binds(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = BINDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, BINDS_PATH)


class Handler(SimpleHTTPRequestHandler):
    sender = None
    watcher = None
    pin = ""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB_DIR, **kw)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")  # always pick up a new dashboard version
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return not self.pin or self.headers.get("X-Pin", "") == self.pin

    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._authorized():
                return self._json(401, {"error": "pin"})
            if self.path == "/api/status":
                title = foreground_title()
                return self._json(200, {
                    "ok": True,
                    "version": VERSION,
                    "windows": IS_WINDOWS,
                    "dryRun": self.sender.dry_run,
                    "gameFocused": "star citizen" in title.lower(),
                    "foreground": title[:80],
                    "detect": self.watcher.active,
                    "ship": self.watcher.ship,
                })
            if self.path == "/api/binds":
                return self._json(200, load_binds())
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def do_POST(self):
        if not self._authorized():
            return self._json(401, {"error": "pin"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})

        if self.path == "/api/press":
            actions = load_binds().get("actions", {})
            act = actions.get(data.get("action", ""))
            if not act:
                return self._json(404, {"error": "unknown action"})
            if not act.get("keys"):
                return self._json(409, {"error": "unbound"})
            try:
                combo = parse_combo(act["keys"])
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            count = max(1, min(int(data.get("count", 1)), 60))
            mode = data.get("state") if data.get("state") in ("down", "up") else act.get("mode", "tap")
            self.sender.submit(combo, mode,
                               int(act.get("holdMs", 800)), count, act.get("label", ""))
            return self._json(200, {"ok": True})

        if self.path == "/api/sound":
            ok = self.sounds.play(str(data.get("name", "")), data.get("volume", 0.6))
            return self._json(200 if ok else 404, {"ok": ok})

        if self.path == "/api/binds":
            actions = data.get("actions")
            if not isinstance(actions, dict):
                return self._json(400, {"error": "missing actions"})
            for name, act in actions.items():
                if act.get("keys"):
                    try:
                        parse_combo(act["keys"])
                    except ValueError as e:
                        return self._json(400, {"error": f"{act.get('label', name)}: {e}"})
            for act in actions.values():
                act.pop("fromGame", None)
            save_binds({"actions": actions})
            print("  keybinds saved")
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def start(port=8770, pin="", dry_run=False, log=""):
    """Start the companion. Returns (server, url); call server.serve_forever() to run it."""
    os.makedirs(DATA_DIR, exist_ok=True)
    migrate_binds()
    Handler.sender = KeySender(dry_run)
    Handler.sounds = SoundPlayer()
    Handler.pin = pin
    Handler.watcher = ShipWatcher(log)
    global GAME_BINDS
    GAME_BINDS = GameBinds(Handler.watcher.path)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    url = f"http://{lan_ip()}:{port}"
    print(f"Star Citizen Dashboard companion  (version {VERSION})")
    print(f"  Open this on your iPad:  {url}")
    print(f"  Settings folder: {DATA_DIR}")
    if pin:
        print(f"  PIN: {pin}")
    if Handler.watcher.path:
        print(f"  Ship detection: watching {Handler.watcher.path}")
    else:
        print("  Ship detection: Game.log not found. Start with --log \"<path to Game.log>\" to enable it.")
    if dry_run:
        print("  Dry run: presses are logged, no keys are sent.")
    return server, url


def main():
    ap = argparse.ArgumentParser(description="Star Citizen Dashboard companion")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--pin", default="", help="optional PIN the dashboard must send")
    ap.add_argument("--dry-run", action="store_true", help="log presses without sending keys")
    ap.add_argument("--log", default="", help="path to Star Citizen's Game.log (found automatically if installed in a usual place)")
    args = ap.parse_args()
    server, _ = start(args.port, args.pin, args.dry_run, args.log)
    print("  Keep Star Citizen as the focused window. Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

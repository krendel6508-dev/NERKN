#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NERKN
Скрывается в трей, без консоли, умный подбор с индикацией.

Интерфейс полностью переведён на веб-движок (pywebview + HTML/CSS/JS):
окно приложения рендерит настоящую веб-страницу (тот же движок, что и в
браузере на Chromium/WebView2) вместо классических виджетов Tkinter, за
счёт чего интерфейс выглядит и анимируется как современный сайт.
"""

import os
import sys
import json
import time
import math
import shlex
import ctypes
import queue
import socket
import asyncio
import logging
import traceback
import logging.handlers
import webbrowser
import subprocess
import threading
import importlib.util
import re
import shutil
import tempfile
from xml.sax.saxutils import escape as _xml_escape

# =============================================================================
# ПЕРЕХВАТ ВЫВОДА (Чтобы без консоли не было ошибок)
# =============================================================================
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# =============================================================================
# АВТО-АДМИН (ЗАПРАШИВАЕМ ПРАВА ПРИ ЗАПУСКЕ)
# =============================================================================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

if not is_admin():
    # Исключаем sys.argv[0] из параметров для скомпилированного EXE, чтобы избежать дублирования путей в установщике
    args = sys.argv[1:] if getattr(sys, 'frozen', False) else sys.argv
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in args), None, 1)
    sys.exit(0)

# =============================================================================
# ПУТИ И КОНФИГУРАЦИЯ
# =============================================================================
EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

if os.path.exists(os.path.join(EXE_DIR, 'bin', 'winws.exe')):
    ZAPRET_BASE_DIR = EXE_DIR
elif hasattr(sys, '_MEIPASS'):
    ZAPRET_BASE_DIR = sys._MEIPASS
else:
    ZAPRET_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BIN_DIR = os.path.join(ZAPRET_BASE_DIR, 'bin')
LISTS_DIR = os.path.join(ZAPRET_BASE_DIR, 'lists')
UTILS_DIR = os.path.join(ZAPRET_BASE_DIR, 'utils')
ZAPRETES_DIR = os.path.join(ZAPRET_BASE_DIR, 'zapretes')

WINWS_EXE = os.path.join(BIN_DIR, 'winws.exe')

CONFIG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'zapret-gui')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
GAME_FILTER_FILE = os.path.join(UTILS_DIR, 'game_filter.enabled')
DEBUG_LOG_FILE = os.path.join(CONFIG_DIR, 'zapret_debug.log')
TG_PROXY_LOG_FILE = os.path.join(CONFIG_DIR, 'tg_proxy.log')
TG_PROXY_PKG_DIR = os.path.join(ZAPRET_BASE_DIR, 'proxy')

# Резервное хранилище пользовательских данных (тема, домены, настройки).
# Лежит вне папки установки и вне профиля конкретного пользователя, поэтому
# переживает переустановку/обновление через Inno Setup и повышение прав
# под другой учётной записью (когда APPDATA у админа и пользователя разный).
BACKUP_DIR = os.path.join(os.environ.get('PROGRAMDATA', r'C:\ProgramData'), 'NERKN')
BACKUP_CONFIG_FILE = os.path.join(BACKUP_DIR, 'config.json')
BACKUP_LISTS_DIRS = [os.path.join(BACKUP_DIR, 'lists'), os.path.join(CONFIG_DIR, 'lists')]

# Автозапуск: задача планировщика с наивысшими правами. Ярлык в папке
# «Автозагрузка» для exe с requireAdministrator Windows молча игнорирует.
# Заполните адреса проекта перед выпуском. Пустая строка — ссылка ещё не задана.
PROJECT_LINKS = {"telegram": "https://t.me/nerknn", "github": ""}

AUTOSTART_TASK_NAME = 'NERKN_Autostart'
AUTOSTART_ARG = '--autostart'
AUTOSTART_LAUNCH = AUTOSTART_ARG in sys.argv   # запущено при входе в Windows -> стартуем скрыто в трее

def debug_log_reset():
    """Очищает отладочный файл в начале нового теста."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(DEBUG_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("")
    except Exception:
        pass

def debug_log(text: str):
    """Дописывает строку(и) в отладочный файл (не в окно лога)."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(text.rstrip('\n') + '\n')
    except Exception:
        pass

def debug_log_open():
    """Открывает отладочный файл в блокноте/текстовом редакторе по умолчанию."""
    try:
        os.startfile(DEBUG_LOG_FILE)
    except Exception:
        pass

IPSET_UPDATE_URL = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
IPSET_FILE = os.path.join(LISTS_DIR, 'ipset-all.txt')
IPSET_BACKUP_FILE = IPSET_FILE + '.backup'
IPSET_NONE_MARKER = '203.0.113.113/32'  # то же значение-заглушка, что и в оригинальном service.bat
LIST_GENERAL = os.path.join(LISTS_DIR, 'list-general.txt')
LIST_GOOGLE = os.path.join(LISTS_DIR, 'list-google.txt')
LIST_GENERAL_USER = os.path.join(LISTS_DIR, 'list-general-user.txt')
LIST_EXCLUDE_USER = os.path.join(LISTS_DIR, 'list-exclude-user.txt')
IPSET_EXCLUDE_FILE = os.path.join(LISTS_DIR, 'ipset-exclude.txt')
IPSET_EXCLUDE_USER_FILE = os.path.join(LISTS_DIR, 'ipset-exclude-user.txt')
LIST_EXCLUDE_FILE = os.path.join(LISTS_DIR, 'list-exclude.txt')
EXCLUDE_FILES = [LIST_EXCLUDE_USER, IPSET_EXCLUDE_FILE, IPSET_EXCLUDE_USER_FILE, LIST_EXCLUDE_FILE]
EXCLUDE_BACKUP_FILE = os.path.join(LISTS_DIR, 'exclude_backup.json')

# =============================================================================
# ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ
# =============================================================================
REQUIRED_PACKAGES = [
    ("psutil", "psutil"),
    ("requests", "requests"),
    ("webview", "pywebview"),
    ("pystray", "pystray"),
    ("PIL", "Pillow"),
    # нужны встроенному Telegram MTProto-прокси (tg-ws-proxy)
    ("certifi", "certifi"),
    ("cryptography", "cryptography"),
]

def _find_missing_packages():
    missing = []
    for mod_name, pip_name in REQUIRED_PACKAGES:
        try:
            found = importlib.util.find_spec(mod_name) is not None
        except Exception:
            found = False
        if not found:
            missing.append((mod_name, pip_name))
    return missing

def _pip_install(pip_name: str) -> bool:
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", pip_name],
            check=False, creationflags=flags,
        )
        return res.returncode == 0
    except Exception:
        return False

def _run_dependency_splash(missing_packages):
    import tkinter as tk

    root = tk.Tk()
    root.title("NERKN")
    try:
        root.overrideredirect(True)
    except Exception:
        pass
    root.configure(bg="#090c1a")
    w, h = 420, 264
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    canvas = tk.Canvas(root, width=w, height=h, bg="#090c1a", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    canvas.create_rectangle(0, 0, w, h, outline="#1a2040", width=2)
    canvas.create_text(w // 2, 26, text="NERKN", fill="#33e6a6", font=("Segoe UI", 16, "bold"))
    canvas.create_text(w // 2, 48, text="Готовим всё необходимое перед запуском...", fill="#9aa1c4", font=("Segoe UI", 10))

    status_text = canvas.create_text(w // 2, 196, text="Проверка зависимостей...", fill="#eef0fb", font=("Segoe UI", 10))

    bar_x0, bar_y0, bar_x1, bar_y1 = 36, 216, w - 36, 230
    canvas.create_rectangle(bar_x0, bar_y0, bar_x1, bar_y1, outline="#1a2040", fill="#12162c", width=1)
    bar_fill = canvas.create_rectangle(bar_x0, bar_y0, bar_x0, bar_y1, outline="", fill="#33e6a6")
    pct_text = canvas.create_text(w - 36, 240, anchor="e", text="0%", fill="#6d75a0", font=("Segoe UI", 9))

    mole_cx, mole_cy = w // 2, 122
    mole_items = []

    def draw_mole(tilt=0.0, bounce=0.0):
        for item_id in mole_items:
            canvas.delete(item_id)
        mole_items.clear()
        cy = mole_cy + bounce
        off = tilt * 7
        mole_items.append(canvas.create_oval(mole_cx - 36 + off * .3, cy - 24, mole_cx + 36 + off * .3, cy + 30, fill="#8b6bff", outline=""))
        mole_items.append(canvas.create_oval(mole_cx - 36, cy - 30, mole_cx - 22, cy - 16, fill="#8b6bff", outline=""))
        mole_items.append(canvas.create_oval(mole_cx + 22, cy - 30, mole_cx + 36, cy - 16, fill="#8b6bff", outline=""))
        mole_items.append(canvas.create_oval(mole_cx - 20 + off * .3, cy, mole_cx + 20 + off * .3, cy + 22, fill="#a98bff", outline=""))
        mole_items.append(canvas.create_oval(mole_cx - 5 + off * .3, cy + 12, mole_cx + 5 + off * .3, cy + 20, fill="#ff5c72", outline=""))
        mole_items.append(canvas.create_oval(mole_cx - 25 + off, cy - 8, mole_cx - 7 + off, cy + 8, fill="#090c1a", outline="#4fd1ff", width=2))
        mole_items.append(canvas.create_oval(mole_cx + 7 + off, cy - 8, mole_cx + 25 + off, cy + 8, fill="#090c1a", outline="#4fd1ff", width=2))
        mole_items.append(canvas.create_line(mole_cx - 7 + off, cy, mole_cx + 7 + off, cy, fill="#4fd1ff", width=2))
        mole_items.append(canvas.create_line(mole_cx - 25 + off, cy - 6, mole_cx - 34 + off, cy - 12, fill="#4fd1ff", width=2))

    state = {"angle": 0.0, "progress": 0.0, "target": 0.0, "label": "Проверка зависимостей...", "done": False}

    def animate():
        state["angle"] += 0.20
        tilt = math.sin(state["angle"])
        bounce = 3 * math.sin(state["angle"] * 1.3)
        draw_mole(tilt, bounce)

        state["progress"] += (state["target"] - state["progress"]) * 0.15
        fill_w = bar_x0 + (bar_x1 - bar_x0) * max(0.0, min(1.0, state["progress"]))
        canvas.coords(bar_fill, bar_x0, bar_y0, fill_w, bar_y1)
        canvas.itemconfigure(pct_text, text=f"{int(round(state['progress'] * 100))}%")
        canvas.itemconfigure(status_text, text=state["label"])

        if state["done"] and state["progress"] > 0.985:
            root.after(350, root.destroy)
            return
        root.after(33, animate)

    def install_worker():
        total = max(1, len(missing_packages))
        for i, (mod_name, pip_name) in enumerate(missing_packages):
            state["label"] = f"Устанавливаем {pip_name}..."
            _pip_install(pip_name)
            state["target"] = (i + 1) / total
        state["label"] = "Готово!"
        state["target"] = 1.0
        time.sleep(0.4)
        state["done"] = True

    threading.Thread(target=install_worker, daemon=True).start()
    animate()
    root.mainloop()

def ensure_dependencies():
    if getattr(sys, 'frozen', False):
        return

    missing = _find_missing_packages()
    if missing:
        try:
            _run_dependency_splash(missing)
        except Exception:
            for mod_name, pip_name in missing:
                _pip_install(pip_name)

    if not os.path.exists(WINWS_EXE):
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(
                "NERKN",
                "Не найден файл bin\\winws.exe.\n"
                "Похоже, установка повреждена или неполная — переустановите программу.",
            )
            r.destroy()
        except Exception:
            pass
        sys.exit(1)

ensure_dependencies()

os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--force-renderer-accessibility=off",
)

import psutil
import requests
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# УТИЛИТЫ И ЛОГИКА
# =============================================================================
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _read_json_file(path: str):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None

_CONFIG_LOCK = threading.RLock()

def _write_json_atomic(path: str, data: dict):
    ensure_dir(os.path.dirname(path))
    fd, tmp = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.05 * (attempt + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def load_config() -> dict:
    # User profile is authoritative; shared backup is recovery only.
    with _CONFIG_LOCK:
        for path in (CONFIG_FILE, BACKUP_CONFIG_FILE):
            data = _read_json_file(path)
            if data is not None:
                return data
    return {}

def save_config(cfg: dict):
    with _CONFIG_LOCK:
        snapshot = json.loads(json.dumps(cfg, allow_nan=False))
        _write_json_atomic(CONFIG_FILE, snapshot)
        try:
            _write_json_atomic(BACKUP_CONFIG_FILE, snapshot)
        except Exception as exc:
            debug_log(f"save_config: не удалось записать резервную копию: {exc}")

def copy_text_to_clipboard(text):
    """Unicode clipboard with explicit 64-bit-safe Win32 signatures."""
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [wintypes.HWND]
    user.OpenClipboard.restype = wintypes.BOOL
    user.EmptyClipboard.argtypes = []
    user.EmptyClipboard.restype = wintypes.BOOL
    user.CloseClipboard.argtypes = []
    user.CloseClipboard.restype = wintypes.BOOL
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.restype = wintypes.HGLOBAL
    # A hidden window owned by this calling thread; no dependency on foreground focus.
    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user.CreateWindowExW.restype = wintypes.HWND
    user.DestroyWindow.argtypes = [wintypes.HWND]
    user.DestroyWindow.restype = wintypes.BOOL
    owner = user.CreateWindowExW(0, 'STATIC', 'NERKN Clipboard', 0, 0, 0, 0, 0,
                                wintypes.HWND(-3), None, None, None)
    if not owner:
        raise ctypes.WinError(ctypes.get_last_error())
    data = (text + '\0').encode('utf-16-le')
    handle = kernel.GlobalAlloc(0x0002, len(data))
    if not handle:
        user.DestroyWindow(owner)
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel.GlobalUnlock(handle)
        for attempt in range(10):
            if user.OpenClipboard(owner):
                break
            time.sleep(.05)
        else:
            raise OSError("буфер занят другим приложением")
        try:
            if not user.EmptyClipboard() or not user.SetClipboardData(13, handle):
                raise ctypes.WinError(ctypes.get_last_error())
            handle = None  # Windows now owns the allocation.
        finally:
            user.CloseClipboard()
    finally:
        if handle:
            kernel.GlobalFree(handle)
        user.DestroyWindow(owner)


def normalize_scale(value):
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return 100
    return value if value in (80, 90, 100, 110, 125, 150) else 100

DEFAULT_GF_PORTS = "1024-65535"
_PORTS_RE = re.compile(r'\d{1,5}(-\d{1,5})?(,\d{1,5}(-\d{1,5})?)*')

def sanitize_ports(value):
    """Проверяет строку портов вида '1024-1934,1936-65535'.
    Пусто -> порты по умолчанию; некорректно -> None."""
    v = re.sub(r'\s+', '', str(value or ''))
    if not v:
        return DEFAULT_GF_PORTS
    if not _PORTS_RE.fullmatch(v):
        return None
    for part in v.split(','):
        nums = [int(x) for x in part.split('-')]
        if any(n < 1 or n > 65535 for n in nums) or (len(nums) == 2 and nums[0] > nums[1]):
            return None
    return v

THEME_KEYS = ("standard", "modern", "ios26", "custom")
LOOK_KEYS = ("standard", "modern", "ios26")
SCHEME_KEYS = ("classic", "black", "white")
DEFAULT_SCHEMES = {"standard": "classic", "modern": "black", "ios26": "classic"}
_LEGACY_TONES = {"dark": "black", "white": "white", "gray": "classic"}
IOS_PALETTES = ("photo", "aurora", "ocean", "sunset", "graphite")
_LEGACY_THEMES = {"default": "standard", "dark": "modern", "light": "modern"}
CUSTOM_COLOR_KEYS = ("bg", "panel", "term", "text", "border", "accent", "accent2", "accent3", "idle", "testing")
_HEX6_RE = re.compile(r'#[0-9a-fA-F]{6}')

def normalize_theme(name) -> str:
    """Старые значения (default/dark/light) переводим в новые темы."""
    name = _LEGACY_THEMES.get(name, name)
    return name if name in THEME_KEYS else "standard"

def get_schemes(cfg: dict) -> dict:
    """Цветовая схема (classic/black/white) для каждой темы."""
    out = dict(DEFAULT_SCHEMES)
    saved = cfg.get("schemes")
    if isinstance(saved, dict):
        for k, v in saved.items():
            if k in out and v in SCHEME_KEYS:
                out[k] = v
    else:
        legacy = _LEGACY_TONES.get(cfg.get("modern_tone"))
        if legacy:
            out["modern"] = legacy
        elif cfg.get("theme") == "light":
            out["modern"] = "white"
    return out

def sanitize_custom(raw):
    """Проверка «своей» темы из настроек/редактора. None - если данные неверны."""
    if not isinstance(raw, dict):
        return None
    base = raw.get("base") if raw.get("base") in LOOK_KEYS else "standard"
    scheme = raw.get("scheme") if raw.get("scheme") in SCHEME_KEYS else "classic"
    colors = raw.get("c") if isinstance(raw.get("c"), dict) else {}
    c = {}
    for key in CUSTOM_COLOR_KEYS:
        v = colors.get(key)
        if isinstance(v, str) and _HEX6_RE.fullmatch(v):
            c[key] = v.lower()
        else:
            return None
    def num(key, lo, hi, default):
        try:
            x = float(raw.get(key, default))
        except (TypeError, ValueError):
            x = default
        return max(lo, min(hi, x)) if math.isfinite(x) else default
    return {"base": base, "scheme": scheme, "c": c,
            "panelA": round(num("panelA", 0, 1, 1), 3), "borderA": round(num("borderA", 0, 1, .1), 3),
            "radius": int(num("radius", 0, 40, 20)), "blur": int(num("blur", 0, 60, 26))}

def get_game_filter_ports(cfg: dict = None) -> dict:
    cfg = cfg or {}
    return {
        "tcp": sanitize_ports(cfg.get("gf_tcp_ports")) or DEFAULT_GF_PORTS,
        "udp": sanitize_ports(cfg.get("gf_udp_ports")) or DEFAULT_GF_PORTS,
    }

def get_game_filter(cfg: dict = None) -> dict:
    """Режим из utils/game_filter.enabled + порты GameFilter TCP/UDP.
    С Flowseal 1.10.3 порты можно менять (например исключить RTMP:
    1024-1934,1936-65535) — задаются в настройках NERKN."""
    ports = get_game_filter_ports(cfg)
    tcp_p, udp_p = ports["tcp"], ports["udp"]
    all_p = tcp_p if tcp_p == udp_p else DEFAULT_GF_PORTS
    if not os.path.exists(GAME_FILTER_FILE):
        return {"mode": "disabled", "all": "12", "tcp": "12", "udp": "12"}
    with open(GAME_FILTER_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        mode = f.read().strip().lower()
    if mode == "all": return {"mode": "all", "all": all_p, "tcp": tcp_p, "udp": udp_p}
    elif mode == "tcp": return {"mode": "tcp", "all": tcp_p, "tcp": tcp_p, "udp": "12"}
    elif mode == "udp": return {"mode": "udp", "all": udp_p, "tcp": "12", "udp": udp_p}
    return {"mode": "disabled", "all": "12", "tcp": "12", "udp": "12"}

def set_game_filter_mode(mode: str) -> bool:
    """Пункт 4 меню service.bat: Game Filter — disabled/all/tcp/udp."""
    mode = (mode or "disabled").strip().lower()
    if mode not in ("disabled", "all", "tcp", "udp"):
        return False
    try:
        ensure_dir(UTILS_DIR)
        if mode == "disabled":
            if os.path.exists(GAME_FILTER_FILE):
                os.remove(GAME_FILTER_FILE)
        else:
            with open(GAME_FILTER_FILE, 'w', encoding='utf-8') as f:
                f.write(mode + "\n")
        return True
    except Exception:
        return False

def get_ipset_status() -> str:
    """Пункт 5 меню service.bat: none / any / loaded (тот же алгоритм)."""
    if not os.path.exists(IPSET_FILE):
        return "any"
    try:
        with open(IPSET_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l.strip() for l in f.read().splitlines()]
    except Exception:
        return "any"
    if not any(lines):
        return "any"
    if any(l == IPSET_NONE_MARKER for l in lines):
        return "none"
    return "loaded"

def cycle_ipset_status():
    """Переключает режим IPSet по кругу: loaded -> none -> any -> loaded.
    Возвращает (ok, новый_статус, текст_ошибки)."""
    ensure_dir(LISTS_DIR)
    status = get_ipset_status()
    try:
        if status == "loaded":
            if os.path.exists(IPSET_BACKUP_FILE):
                os.remove(IPSET_BACKUP_FILE)
            if os.path.exists(IPSET_FILE):
                os.replace(IPSET_FILE, IPSET_BACKUP_FILE)
            with open(IPSET_FILE, 'w', encoding='utf-8') as f:
                f.write(IPSET_NONE_MARKER + "\n")
            return True, "none", ""
        elif status == "none":
            with open(IPSET_FILE, 'w', encoding='utf-8') as f:
                f.write("")
            return True, "any", ""
        else:  # any
            if not os.path.exists(IPSET_BACKUP_FILE):
                return False, status, ("Нет резервной копии списка — сначала обновите "
                                       "IPSet из сети, потом можно будет вернуться к «loaded».")
            if os.path.exists(IPSET_FILE):
                os.remove(IPSET_FILE)
            os.replace(IPSET_BACKUP_FILE, IPSET_FILE)
            return True, "loaded", ""
    except Exception as exc:
        return False, status, f"Не удалось переключить режим IPSet: {exc}"

USER_PERSIST_FILES = [LIST_GENERAL_USER, LIST_EXCLUDE_USER, IPSET_EXCLUDE_USER_FILE, EXCLUDE_BACKUP_FILE]
_PLACEHOLDER_LINES = {"domain.example.abc", "203.0.113.113/32"}

def _meaningful_lines(path: str) -> list:
    out = []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                t = line.strip()
                if t and not t.startswith('#') and t not in _PLACEHOLDER_LINES:
                    out.append(t)
    except Exception:
        pass
    return out

def _newest_user_backup(name: str):
    best = None
    for d in BACKUP_LISTS_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            try:
                if best is None or os.path.getmtime(p) > os.path.getmtime(best):
                    best = p
            except OSError:
                pass
    return best

def backup_user_files():
    """Копирует пользовательские списки в ProgramData и APPDATA."""
    for src in USER_PERSIST_FILES:
        if not os.path.isfile(src):
            continue
        for d in BACKUP_LISTS_DIRS:
            try:
                ensure_dir(d)
                shutil.copy2(src, os.path.join(d, os.path.basename(src)))
            except Exception as exc:
                debug_log(f"backup_user_files: {src} -> {d}: {exc}")

def restore_user_files():
    """Если установщик затёр пользовательские списки (остались только
    заглушки или файла нет), а в резервной копии есть данные — возвращаем их."""
    ensure_dir(LISTS_DIR)
    for dst in USER_PERSIST_FILES:
        name = os.path.basename(dst)
        bak = _newest_user_backup(name)
        if not bak:
            continue
        try:
            if name.endswith('.json'):
                need = not os.path.isfile(dst)
            else:
                need = (not os.path.isfile(dst) or not _meaningful_lines(dst)) and bool(_meaningful_lines(bak))
            if need:
                shutil.copy2(bak, dst)
                debug_log(f"restore_user_files: восстановлен {name}")
        except Exception as exc:
            debug_log(f"restore_user_files: {name}: {exc}")

def ensure_user_lists():
    ensure_dir(LISTS_DIR)
    if not os.path.exists(IPSET_EXCLUDE_USER_FILE):
        with open(IPSET_EXCLUDE_USER_FILE, 'w', encoding='utf-8') as f: f.write(IPSET_NONE_MARKER + "\n")
    if not os.path.exists(LIST_EXCLUDE_USER):
        with open(LIST_EXCLUDE_USER, 'w', encoding='utf-8') as f: f.write("domain.example.abc\n")
    if not os.path.exists(LIST_GENERAL_USER):
        with open(LIST_GENERAL_USER, 'w', encoding='utf-8') as f:
            f.write("# Never leave this file empty\ndomain.example.abc\n")

def load_domains() -> list:
    domains = []
    seen = set()
    for path in (LIST_GENERAL, LIST_GOOGLE):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and line not in seen:
                        seen.add(line)
                        domains.append({"domain": line, "editable": False})
    if os.path.exists(LIST_GENERAL_USER):
        with open(LIST_GENERAL_USER, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and line not in seen:
                    seen.add(line)
                    domains.append({"domain": line, "editable": True})
    return domains

def save_user_domains(domains: list):
    ensure_dir(LISTS_DIR)
    with open(LIST_GENERAL_USER, 'w', encoding='utf-8') as f:
        f.write("# Never leave this file empty\n")
        for d in domains: f.write(d + "\n")

def load_exclude_backup() -> dict:
    if os.path.exists(EXCLUDE_BACKUP_FILE):
        try:
            with open(EXCLUDE_BACKUP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_exclude_backup(data: dict):
    ensure_dir(LISTS_DIR)
    with open(EXCLUDE_BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _remove_domain_lines(path: str, domain: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return False
    kept, removed = [], False
    for line in lines:
        if line.strip() == domain:
            removed = True
            continue
        kept.append(line)
    if removed:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(kept)
        except Exception:
            return False
    return removed

def _append_domain_line(path: str, domain: str):
    try:
        ensure_dir(os.path.dirname(path))
        existing = set()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                existing = {l.strip() for l in f}
        if domain in existing:
            return
        needs_newline_before = False
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, 'rb') as f:
                f.seek(-1, os.SEEK_END)
                needs_newline_before = f.read(1) != b'\n'
        with open(path, 'a', encoding='utf-8') as f:
            if needs_newline_before:
                f.write('\n')
            f.write(domain + '\n')
    except Exception:
        pass

def release_domain_from_excludes(domain: str):
    if not domain: return
    backup = load_exclude_backup()
    sources = list(backup.get(domain, []))
    for path in EXCLUDE_FILES:
        if _remove_domain_lines(path, domain) and path not in sources:
            sources.append(path)
    if sources:
        backup[domain] = sources
        save_exclude_backup(backup)

def restore_domain_to_excludes(domain: str):
    if not domain: return
    backup = load_exclude_backup()
    sources = backup.pop(domain, None)
    if not sources: return
    for path in sources:
        _append_domain_line(path, domain)
    save_exclude_backup(backup)

def scan_strategies() -> list:
    strategies = []
    if not os.path.isdir(ZAPRETES_DIR): return strategies
    for f in sorted(os.listdir(ZAPRETES_DIR)):
        if f.lower().endswith('.bat') and not f.lower().startswith('service'):
            strategies.append(f)
    return strategies

def _tokenize_winws_args(s: str) -> list:
    tokens = []
    cur = []
    in_quotes = False
    has_content = False
    for ch in s:
        if ch == '"':
            in_quotes = not in_quotes
            has_content = True
            continue
        if ch.isspace() and not in_quotes:
            if has_content:
                tokens.append(''.join(cur))
                cur = []
                has_content = False
            continue
        cur.append(ch)
        has_content = True
    if has_content:
        tokens.append(''.join(cur))
    return tokens

def parse_strategy_args(bat_filename: str, gf: dict) -> list:
    bat_path = os.path.join(ZAPRETES_DIR, bat_filename)
    if not os.path.exists(bat_path): return []

    try:
        with open(bat_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return []

    env_vars = {
        "BIN": BIN_DIR + '\\',
        "LISTS": LISTS_DIR + '\\',
        "GAMEFILTER": gf.get("all", "12"),
        "GAMEFILTERTCP": gf.get("tcp", "12"),
        "GAMEFILTERUDP": gf.get("udp", "12"),
        "~DP0": ZAPRET_BASE_DIR + '\\'
    }

    merged_lines = []
    current_line = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('::') or line.lower().startswith('rem ') or line.startswith('@'): continue

        if line.endswith('^'):
            current_line += line[:-1] + " "
        else:
            current_line += line
            merged_lines.append(current_line)
            current_line = ""

    if current_line:
        merged_lines.append(current_line)

    for line in merged_lines:
        if_match = re.search(r'(?i)\bif\s+(not\s+)?exist\s+"?([^"]+)"?\s+(.*)', line)
        if if_match:
            is_not = bool(if_match.group(1) and if_match.group(1).strip().lower() == 'not')
            target_path = if_match.group(2)
            rest = if_match.group(3)

            for _ in range(3):
                target_path = target_path.replace('%~dp0', ZAPRET_BASE_DIR + '\\')
                target_path = target_path.replace('%BIN%', BIN_DIR + '\\').replace('%%BIN%%', BIN_DIR + '\\')
                target_path = target_path.replace('%LISTS%', LISTS_DIR + '\\').replace('%%LISTS%%', LISTS_DIR + '\\')
                target_path = re.sub(r'%([a-zA-Z0-9_]+)%', lambda m: env_vars.get(m.group(1).upper(), ""), target_path, flags=re.IGNORECASE)

            if ('\\' in target_path or '/' in target_path) and not os.path.isabs(target_path):
                target_path = os.path.join(ZAPRET_BASE_DIR, target_path)

            exists = os.path.exists(target_path)
            if (exists and is_not) or (not exists and not is_not):
                continue
            line = rest

        for m in re.finditer(r'(?i)\bset\s+"(?P<key>[a-zA-Z0-9_]+)=(?P<val>[^"]*)"', line):
            k = m.group('key').strip().upper()
            v = m.group('val').strip()
            env_vars[k] = v

        for m in re.finditer(r'(?i)\bset\s+(?!"?)(?P<key>[a-zA-Z0-9_]+)=(?P<val>[^&"\n\r]*)(?:&|$|\))', line):
            k = m.group('key').strip().upper()
            v = m.group('val').strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            env_vars[k] = v

    for line in merged_lines:
        if 'winws.exe' not in line.lower():
            continue

        try:
            idx = line.lower().index('winws.exe')
        except ValueError:
            continue

        after = line[idx + len('winws.exe'):].strip()
        if after.startswith('"'):
            after = after[1:].strip()

        if not after:
            return []

        for _ in range(5):
            after = after.replace('%~dp0', ZAPRET_BASE_DIR + '\\')
            after = after.replace('%%BIN%%', BIN_DIR + '\\').replace('%BIN%', BIN_DIR + '\\')
            after = after.replace('%%LISTS%%', LISTS_DIR + '\\').replace('%LISTS%', LISTS_DIR + '\\')
            after = after.replace('%GameFilter%', gf.get("all", "12")).replace('%%GameFilter%%', gf.get("all", "12"))
            after = after.replace('%GameFilterTCP%', gf.get("tcp", "12")).replace('%%GameFilterTCP%%', gf.get("tcp", "12"))
            after = after.replace('%GameFilterUDP%', gf.get("udp", "12")).replace('%%GameFilterUDP%%', gf.get("udp", "12"))

            after = re.sub(r'%([a-zA-Z0-9_]+)%', lambda m: env_vars.get(m.group(1).upper(), ""), after, flags=re.IGNORECASE)
            after = re.sub(r'!([a-zA-Z0-9_]+)!', lambda m: env_vars.get(m.group(1).upper(), ""), after, flags=re.IGNORECASE)

        if not after.strip():
            return []

        args = _tokenize_winws_args(after)

        result = []
        for arg in args:
            arg = arg.strip()
            if not arg or arg == '^' or arg == '""' or arg == "''":
                continue

            unquoted = arg[1:-1] if (arg.startswith('"') and arg.endswith('"')) else arg
            unquoted = unquoted.strip()
            if not unquoted:
                continue

            unquoted = unquoted.replace('%%BIN%%', BIN_DIR + '\\').replace('%BIN%', BIN_DIR + '\\')
            unquoted = unquoted.replace('%%LISTS%%', LISTS_DIR + '\\').replace('%LISTS%', LISTS_DIR + '\\')
            unquoted = unquoted.replace('%GameFilter%', gf["all"]).replace('%%GameFilter%%', gf["all"])
            unquoted = unquoted.replace('%GameFilterTCP%', gf["tcp"]).replace('%%GameFilterTCP%%', gf["tcp"])
            unquoted = unquoted.replace('%GameFilterUDP%', gf["udp"]).replace('%%GameFilterUDP%%', gf["udp"])
            unquoted = unquoted.replace('%~dp0', ZAPRET_BASE_DIR + '\\')

            if '=' in unquoted:
                k, v = unquoted.split('=', 1)
                k = k.strip()
                v = v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1].strip()

                v = v.replace('%~dp0', ZAPRET_BASE_DIR + '\\')
                v = v.replace('%BIN%', BIN_DIR + '\\').replace('%%BIN%%', BIN_DIR + '\\')
                v = v.replace('%LISTS%', LISTS_DIR + '\\').replace('%%LISTS%%', LISTS_DIR + '\\')

                if ('\\' in v or '/' in v) and not os.path.isabs(v):
                    v = os.path.join(ZAPRET_BASE_DIR, v)

                if k.lower() in ('--hostlist', '--ipset', '--hostlist-exclude', '--ipset-exclude', '--qnumlist'):
                    if not os.path.exists(v):
                        continue

                unquoted = f"{k}={v}"
            else:
                if not unquoted.startswith('-') and ('\\' in unquoted or '/' in unquoted) and not os.path.isabs(unquoted):
                    unquoted = os.path.join(ZAPRET_BASE_DIR, unquoted)

            result.append(unquoted)
        return result
    return []

# =============================================================================
# СЛУЖБЫ И ПРОЦЕССЫ
# =============================================================================
def is_winws_process_running() -> bool:
    try:
        for proc in psutil.process_iter(['name']):
            try:
                if (proc.info.get('name') or '').lower() == 'winws.exe':
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False

def get_service_status() -> str:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        out = subprocess.check_output(["sc", "query", "zapret"], shell=False, text=True, errors="ignore", creationflags=flags)
        status = None
        for line in out.splitlines():
            if "STATE" in line:
                if "RUNNING" in line: status = "running"
                elif "STOPPED" in line: status = "stopped"
                elif "STOP_PENDING" in line: status = "stopping"
        status = status or "installed"
    except subprocess.CalledProcessError:
        status = "not_installed"

    if status != "running" and is_winws_process_running():
        return "running"
    return status

def service_exists() -> bool:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        return subprocess.run(["sc", "query", "zapret"], capture_output=True, creationflags=flags).returncode == 0
    except Exception:
        return False

def set_service_start_type(auto: bool) -> bool:
    """sc config zapret start= auto|demand (если служба уже установлена)."""
    if not service_exists():
        return True
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        res = subprocess.run(["sc", "config", "zapret", "start=", "auto" if auto else "demand"],
                             capture_output=True, text=True, creationflags=flags)
        if res.returncode != 0:
            debug_log(f"sc config zapret (код {res.returncode}): {res.stdout.strip()} {res.stderr.strip()}")
        return res.returncode == 0
    except Exception as exc:
        debug_log(f"sc config zapret: {exc}")
        return False

def start_installed_service():
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        res = subprocess.run(["sc", "start", "zapret"], capture_output=True, text=True, creationflags=flags)
        debug_log(f"autostart: sc start zapret -> код {res.returncode} {res.stdout.strip()}")
    except Exception as exc:
        debug_log(f"autostart: sc start zapret: {exc}")

def _autostart_exec():
    if getattr(sys, 'frozen', False):
        return sys.executable, AUTOSTART_ARG, os.path.dirname(sys.executable)
    return sys.executable, f'"{os.path.abspath(__file__)}" {AUTOSTART_ARG}', os.path.dirname(os.path.abspath(__file__))

def _legacy_startup_shortcut() -> str:
    return os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu',
                        'Programs', 'Startup', 'NERKN.lnk')

def autostart_app_enabled() -> bool:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        return subprocess.run(["schtasks", "/Query", "/TN", AUTOSTART_TASK_NAME],
                              capture_output=True, creationflags=flags).returncode == 0
    except Exception:
        return False

def set_autostart_app(enabled: bool):
    """Автозапуск приложения при входе в Windows через планировщик заданий
    (RunLevel=Highest, без UAC-окна). Возвращает (ok, текст_ошибки)."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        if not enabled:
            subprocess.run(["schtasks", "/Delete", "/TN", AUTOSTART_TASK_NAME, "/F"],
                           capture_output=True, creationflags=flags)
            return True, ""
        exe, args, workdir = _autostart_exec()
        user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip('\\')
        xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>NERKN autostart</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{_xml_escape(user)}</UserId><Delay>PT5S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{_xml_escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{_xml_escape(exe)}</Command><Arguments>{_xml_escape(args)}</Arguments><WorkingDirectory>{_xml_escape(workdir)}</WorkingDirectory></Exec></Actions>
</Task>
"""
        fd, tmp = tempfile.mkstemp(suffix='.xml')
        os.close(fd)
        try:
            with open(tmp, 'w', encoding='utf-16') as f:
                f.write(xml)
            res = subprocess.run(["schtasks", "/Create", "/TN", AUTOSTART_TASK_NAME, "/XML", tmp, "/F"],
                                 capture_output=True, text=True, errors="ignore", creationflags=flags)
        finally:
            try: os.remove(tmp)
            except OSError: pass
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            debug_log(f"schtasks /Create (код {res.returncode}): {err}")
            return False, err or "schtasks вернул ошибку"
        # старый ярлык из установщика не умеет запускаться с правами админа — убираем
        try:
            lnk = _legacy_startup_shortcut()
            if os.path.isfile(lnk):
                os.remove(lnk)
        except Exception:
            pass
        return True, ""
    except Exception as exc:
        debug_log(f"set_autostart_app: {exc}")
        return False, str(exc)

def install_service(bat_filename: str, gf: dict) -> bool:
    args = parse_strategy_args(bat_filename, gf)
    if not args:
        debug_log(f"install_service: Не удалось получить аргументы для {bat_filename}")
        return False

    args_str = subprocess.list2cmdline(args)
    safe_args_str = args_str.replace('"', '\\"')
    
    start_type = "auto" if load_config().get("autostart_service", True) else "demand"
    cmd = f'sc create zapret binPath= "\\"{WINWS_EXE}\\" {safe_args_str}" DisplayName= "zapret" start= {start_type}'

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    try:
        debug_log("Остановка и удаление старой службы...")
        subprocess.run("sc stop zapret", shell=True, capture_output=True, creationflags=flags)
        subprocess.run("sc delete zapret", shell=True, capture_output=True, creationflags=flags)

        debug_log(f"Создание новой службы. Команда:\n{cmd}")
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, creationflags=flags)
        
        if res.returncode != 0:
            debug_log(f"ОШИБКА sc create (код {res.returncode}):")
            debug_log(f"STDOUT: {res.stdout.strip()}")
            debug_log(f"STDERR: {res.stderr.strip()}")
            return False
        else:
            debug_log(f"Служба успешно создана. Ответ: {res.stdout.strip()}")

        subprocess.run('sc description zapret "Zapret DPI bypass software"', shell=True, capture_output=True, creationflags=flags)
        
        debug_log("Запуск службы zapret...")
        start_res = subprocess.run('sc start zapret', shell=True, capture_output=True, text=True, creationflags=flags)
        if start_res.returncode != 0:
            debug_log(f"ОШИБКА sc start (код {start_res.returncode}):")
            debug_log(f"STDOUT: {start_res.stdout.strip()}")
            debug_log(f"STDERR: {start_res.stderr.strip()}")
        else:
            debug_log("Служба успешно запущена.")

        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Services\zapret", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "zapret-discord-youtube", 0, winreg.REG_SZ, bat_filename)
        return True
    except Exception as e:
        debug_log(f"КРИТИЧЕСКАЯ ОШИБКА при установке службы: {e}")
        return False

def remove_service():
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.run("sc stop zapret", shell=True, capture_output=True, creationflags=flags)
    subprocess.run("sc delete zapret", shell=True, capture_output=True, creationflags=flags)
    subprocess.run("sc stop WinDivert", shell=True, capture_output=True, creationflags=flags)
    subprocess.run("sc delete WinDivert", shell=True, capture_output=True, creationflags=flags)

def start_standalone(bat_filename: str, gf: dict):
    args = parse_strategy_args(bat_filename, gf)
    if not args: return None
    cmd = [WINWS_EXE] + args
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=flags, cwd=ZAPRET_BASE_DIR
        )
    except Exception: return None

def stop_standalone(process):
    if process is None: return
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True): child.terminate()
        parent.terminate()
    except Exception: pass

def check_connection(url: str, timeout: float = 5.0) -> bool:
    try:
        with requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout) as response:
            # HTTP errors (including access-denied pages) do not prove bypass works.
            return 200 <= response.status_code < 400
    except requests.exceptions.RequestException:
        return False

def check_any_parallel(groups: dict) -> dict:
    results = {name: False for name in groups}
    with ThreadPoolExecutor(max_workers=max(4, sum(len(u) for u in groups.values()))) as pool:
        future_to_name = {}
        for name, urls in groups.items():
            for url in urls:
                future_to_name[pool.submit(check_connection, url)] = name
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            if results[name]:
                continue
            try:
                if future.result():
                    results[name] = True
            except Exception:
                pass
    return results

# =============================================================================
# ВСТРОЕННЫЙ TELEGRAM MTPROTO ПРОКСИ (tg-ws-proxy)
# =============================================================================
# Ожидается, что пакет tg-ws-proxy лежит рядом с main.py в папке "proxy":
#   <корень>/proxy/{__init__.py, tg_ws_proxy.py, config.py, bridge.py, ...}
# =============================================================================
_tg_log_ready = False

def _setup_tg_logging():
    """Подробный лог прокси пишем в отдельный файл, а не в окно программы."""
    global _tg_log_ready
    if _tg_log_ready:
        return
    try:
        ensure_dir(CONFIG_DIR)
        logger = logging.getLogger('tg-mtproto-proxy')
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for h in list(logger.handlers):
            logger.removeHandler(h)
        handler = logging.handlers.RotatingFileHandler(
            TG_PROXY_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=1, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s  %(levelname)-5s  %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(handler)
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        _tg_log_ready = True
    except Exception:
        pass


def tg_proxy_log_open():
    try:
        os.startfile(TG_PROXY_LOG_FILE)
    except Exception:
        pass


class TgProxyManager:
    """Запускает tg-ws-proxy в отдельном потоке с собственным asyncio-циклом.

    tg-ws-proxy изредка падает с необработанным исключением вскоре после
    старта (транзитная ошибка сети/сокета) — Telegram при этом успевает
    подключиться и работает пару секунд, а затем прокси тихо умирает.
    Чтобы это не выглядело как "включил и через 3-5 секунд снова выключено",
    менеджер сам поднимает прокси заново несколько раз подряд, если тот упал
    почти сразу после запуска, и только если перезапуски не помогают —
    показывает пользователю понятную ошибку с полным traceback в логе.
    """

    DEFAULT_PORT = 1443
    HOST = '127.0.0.1'
    MAX_AUTO_RESTARTS = 4          # сколько раз подряд пробуем поднять сами
    AUTO_RESTART_WINDOW = 25.0     # упал раньше этого срока -> считаем сбоем, а не штатной остановкой
    AUTO_RESTART_DELAY = 1.5       # пауза перед повторной попыткой, сек

    def __init__(self, config: dict, on_change=None):
        self.config = config
        self.on_change = on_change  # вызывается из фонового потока при изменении статуса
        self.thread = None
        self.loop = None
        self.stop_event = None
        self.running = False
        self.error = ""
        self.restarting = False
        self.restart_count = 0
        self._user_stop = True
        self._start_ts = 0.0
        self._lock = threading.Lock()
        self.port_conflict = None
        self._conflict_owners = []
        self.secret = str(config.get("tg_secret") or "").strip().lower()
        if len(self.secret) != 32:
            self.secret = os.urandom(16).hex()
            config["tg_secret"] = self.secret
        try:
            self.port = int(config.get("tg_port") or self.DEFAULT_PORT)
        except (TypeError, ValueError):
            self.port = self.DEFAULT_PORT

    # ---------- вспомогательное ----------
    def is_available(self) -> bool:
        return os.path.isfile(os.path.join(TG_PROXY_PKG_DIR, 'tg_ws_proxy.py'))

    def link(self) -> str:
        return (f"tg://proxy?server={self.HOST}"
                f"&port={self.port}"
                f"&secret=dd{self.secret}")

    def _port_listening(self) -> bool:
        try:
            with socket.create_connection((self.HOST, self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def status(self) -> dict:
        return {
            "available": self.is_available(),
            "running": bool(self.running),
            "restarting": bool(self.restarting),
            "restartCount": self.restart_count,
            "host": self.HOST,
            "port": self.port,
            "secret": self.secret,
            "link": self.link(),
            "error": self.error,
            "portConflict": self.port_conflict,
        }

    def _import_runner(self):
        if ZAPRET_BASE_DIR not in sys.path:
            sys.path.insert(0, ZAPRET_BASE_DIR)
        from proxy.tg_ws_proxy import _run as tg_run
        from proxy.config import proxy_config as tg_cfg
        return tg_run, tg_cfg

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def _port_conflict_message(self):
        return (f"Порт {self.port} занят. Возможно, уже запущен другой прокси для Telegram. "
                "Выберите действие в уведомлении: закрыть посторонний Telegram-прокси или отменить запуск.")

    def _port_owners(self):
        owners = {c.pid for c in psutil.net_connections(kind='tcp')
                  if c.status == psutil.CONN_LISTEN and c.laddr.port == self.port
                  and c.laddr.ip in (self.HOST, '0.0.0.0', '::', '::ffff:127.0.0.1') and c.pid}
        return [psutil.Process(pid) for pid in sorted(owners)]

    def _record_port_conflict(self):
        self.error = self._port_conflict_message()
        self._user_stop = True
        self.restarting = False
        self._conflict_owners = []
        try:
            self._conflict_owners = [(p.pid, p.create_time()) for p in self._port_owners()]
        except (psutil.Error, OSError):
            pass
        self.port_conflict = {"id": os.urandom(12).hex(), "port": self.port}
        self._notify()

    def resolve_port_conflict(self, token, close_proxy):
        with self._lock:
            if not self.port_conflict or token != self.port_conflict['id']:
                return False, "Запрос устарел. Попробуйте включить прокси снова."
            expected = self._conflict_owners
            self.port_conflict = None
            self._conflict_owners = []
            if not close_proxy:
                self._notify()
                return True, ""
            try:
                processes = self._port_owners()
                if processes:
                    current = [(p.pid, p.create_time()) for p in processes]
                    if current != expected:
                        return False, "Владелец порта изменился. Повторите запуск и подтвердите новый запрос."
                    for process in processes:
                        if process.pid == os.getpid() or process.name().lower() not in ('tgwsproxy_windows.exe', 'tgwsproxy.exe'):
                            return False, "Владелец порта не распознан как Telegram Bridge. Закройте его самостоятельно."
                    for process in processes:
                        process.terminate()
                    _, alive = psutil.wait_procs(processes, timeout=3)
                    if alive:
                        return False, "Посторонний прокси ещё не завершился. Попробуйте позже."
                if self._port_listening():
                    return False, "Порт всё ещё занят. Проверьте другое приложение."
            except (psutil.Error, OSError) as exc:
                return False, f"Не удалось закрыть посторонний прокси: {exc}"
        return self.start()

    # ---------- управление ----------
    def start(self, _is_auto_restart: bool = False):
        with self._lock:
            if self.running:
                return True, ""
            if not self.is_available():
                self.error = ("Папка «proxy» с модулем Telegram-прокси не найдена "
                              "рядом с программой.")
                return False, self.error

            if self._port_listening():
                self._record_port_conflict()
                return False, self.error
            self.port_conflict = None
            self._conflict_owners = []

            _setup_tg_logging()

            try:
                tg_run, tg_cfg = self._import_runner()
            except Exception as exc:
                self.error = f"Не удалось загрузить модуль Telegram-прокси: {exc}"
                debug_log(f"TG proxy import error: {exc!r}")
                return False, self.error

            tg_cfg.host = self.HOST
            tg_cfg.port = self.port
            tg_cfg.secret = self.secret
            tg_cfg.dc_redirects = {2: '149.154.167.220', 4: '149.154.167.220'}
            tg_cfg.buffer_size = 256 * 1024
            tg_cfg.pool_size = 4
            tg_cfg.fallback_cfproxy = True
            tg_cfg.cfproxy_user_domains = []
            tg_cfg.cfproxy_worker_domains = []
            tg_cfg.fake_tls_domain = ''
            tg_cfg.proxy_protocol = False
            tg_cfg.force_test_dc = False

            if not _is_auto_restart:
                self.restart_count = 0
            self._user_stop = False
            self.restarting = False
            self.error = ""
            started = threading.Event()

            def worker():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self.loop = loop
                self._start_ts = time.monotonic()
                try:
                    self.stop_event = asyncio.Event()
                    self.running = True
                    started.set()
                    loop.run_until_complete(tg_run(self.stop_event))
                except Exception as exc:
                    if isinstance(exc, OSError) and (getattr(exc, 'winerror', None) == 10048 or exc.errno in (10048, 98, 48)):
                        self._record_port_conflict()
                    else:
                        self.error = f"Прокси упал с ошибкой: {exc}"
                    debug_log("TG proxy runtime error:\n" + traceback.format_exc())
                finally:
                    was_running = self.running
                    self.running = False
                    started.set()
                    try:
                        loop.close()
                    except Exception:
                        pass
                    self.loop = None
                    self.stop_event = None
                    uptime = time.monotonic() - self._start_ts
                    self._maybe_auto_restart(was_running, uptime)
                    self._notify()

            self.thread = threading.Thread(target=worker, daemon=True, name='tg-ws-proxy')
            self.thread.start()
            started.wait(timeout=5)

            # ждём, пока сокет реально начнёт слушать порт
            for _ in range(30):
                if not self.running:
                    break
                if self._port_listening():
                    return True, ""
                time.sleep(0.1)

            if self.running:
                return True, ""
            return False, self.error or "Не удалось запустить Telegram-прокси."

    def _maybe_auto_restart(self, was_running: bool, uptime: float):
        """Если прокси упал почти сразу после старта сам по себе (не по
        просьбе пользователя) — тихо поднимаем его заново несколько раз."""
        if self._user_stop or not was_running:
            return
        if uptime >= self.AUTO_RESTART_WINDOW:
            return
        if self.restart_count >= self.MAX_AUTO_RESTARTS:
            if self.error:
                self.error += " Автоматический перезапуск не помог — попробуйте включить вручную."
            debug_log(f"TG proxy: {self.MAX_AUTO_RESTARTS} автоперезапусков подряд не помогли, сдаёмся.")
            return
        self.restart_count += 1
        self.restarting = True
        debug_log(f"TG proxy: неожиданная остановка через {uptime:.1f}с, "
                  f"автоперезапуск #{self.restart_count}/{self.MAX_AUTO_RESTARTS}")
        self._notify()

        def _delayed():
            time.sleep(self.AUTO_RESTART_DELAY)
            if self._user_stop:
                self.restarting = False
                self._notify()
                return
            self.start(_is_auto_restart=True)

        threading.Thread(target=_delayed, daemon=True, name='tg-ws-proxy-restart').start()

    def stop(self):
        self._user_stop = True
        self.restarting = False
        loop, ev = self.loop, self.stop_event
        if loop is not None and ev is not None:
            try:
                loop.call_soon_threadsafe(ev.set)
            except Exception:
                pass
        for _ in range(50):
            if not self.running:
                break
            time.sleep(0.1)
        self.running = False
        return True

    def open_in_telegram(self) -> bool:
        url = self.link()
        try:
            os.startfile(url)
            return True
        except Exception:
            pass
        try:
            return bool(webbrowser.open(url))
        except Exception:
            return False


# =============================================================================
# ВЕБ-ФРОНТЕНД (HTML/CSS/JS)
# =============================================================================
FRONTEND_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>NERKN — обход блокировок</title>
<script>window.__BOOT__=null;</script>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
<style>
  /* ============ ТЕМЫ ОФОРМЛЕНИЯ ============ */
  :root, html[data-theme="standard"]{
    --bg-0:#090c1a;
    --bg-1:#12162c;
    --bg-2:#1a2040;
    --border:rgba(255,255,255,.08);
    --border-soft:rgba(255,255,255,.05);
    --text-0:#eef0fb;
    --text-1:#9aa1c4;
    --text-2:#6d75a0;
    --accent-mint:#33e6a6;
    --accent-cyan:#4fd1ff;
    --accent-amber:#ffb648;
    --accent-coral:#ff5c72;
    --accent-violet:#8b6bff;
    --on-accent:#06111a;
    --bar-bg:linear-gradient(180deg, rgba(18,22,44,.9), rgba(18,22,44,.55));
    --bar-bg-up:linear-gradient(0deg, rgba(18,22,44,.9), rgba(18,22,44,.5));
    --overlay-bg:rgba(4,6,16,.6);
    --hover-soft:rgba(255,255,255,.06);
    --blob-1:.16; --blob-2:.14; --blob-3:.10; --grain-a:.025;
    --scroll-thumb-hover:#242c54;
  }
  html[data-theme="standard"][data-scheme="black"]{
    --bg-0:#000000; --bg-1:#0b0b0f; --bg-2:#17171d;
    --border:rgba(255,255,255,.10); --border-soft:rgba(255,255,255,.06);
    --text-0:#f5f5f7; --text-1:#a2a2ad; --text-2:#6d6d78;
    --accent-mint:#3ceaa8; --accent-cyan:#59d4ff; --accent-amber:#ffc061; --accent-coral:#ff6076; --accent-violet:#9b7dff;
    --on-accent:#05050a;
    --bar-bg:linear-gradient(180deg, rgba(10,10,14,.94), rgba(10,10,14,.6));
    --bar-bg-up:linear-gradient(0deg, rgba(10,10,14,.94), rgba(10,10,14,.55));
    --overlay-bg:rgba(0,0,0,.68); --hover-soft:rgba(255,255,255,.07);
    --blob-1:.10; --blob-2:.08; --blob-3:.06; --grain-a:.018; --scroll-thumb-hover:#2a2a33;
  }
  html[data-theme="standard"][data-scheme="white"]{
    --bg-0:#f2f5fb; --bg-1:#ffffff; --bg-2:#eaeef7;
    --border:rgba(16,24,48,.12); --border-soft:rgba(16,24,48,.08);
    --text-0:#111731; --text-1:#4e5675; --text-2:#828aa6;
    --accent-mint:#07a877; --accent-cyan:#0b8fcb; --accent-amber:#c07c07; --accent-coral:#df3d58; --accent-violet:#6a49ee;
    --on-accent:#ffffff;
    --bar-bg:linear-gradient(180deg, rgba(255,255,255,.95), rgba(255,255,255,.7));
    --bar-bg-up:linear-gradient(0deg, rgba(255,255,255,.95), rgba(255,255,255,.7));
    --overlay-bg:rgba(20,28,54,.34); --hover-soft:rgba(16,24,48,.05);
    --blob-1:.12; --blob-2:.10; --blob-3:.08; --grain-a:.012; --scroll-thumb-hover:#d3dbec;
  }

  :root{
    --font-display:'Space Grotesk','Segoe UI',system-ui,sans-serif;
    --font-body:'Inter','Segoe UI',system-ui,sans-serif;
    --font-mono:'JetBrains Mono','Cascadia Code',Consolas,monospace;
    --radius-lg:20px;
    --radius-md:14px;
    --radius-sm:9px;
    --ease:cubic-bezier(.2,.8,.2,1);
  }

  *,*::before,*::after{ box-sizing:border-box; }
  html,body{ height:100%; margin:0; }
  body{
    background:var(--bg-0);
    color:var(--text-0);
    transition:background .45s var(--ease), color .45s var(--ease);
    font-family:var(--font-body);
    display:flex;
    flex-direction:column;
    overflow:hidden;
    -webkit-font-smoothing:antialiased;
    position:relative;
  }
  ::selection{ background:var(--accent-cyan); color:var(--on-accent); }

  ::-webkit-scrollbar{ width:9px; height:9px; }
  ::-webkit-scrollbar-track{ background:transparent; }
  ::-webkit-scrollbar-thumb{ background:var(--bg-2); border-radius:99px; border:2px solid transparent; background-clip:padding-box; }
  ::-webkit-scrollbar-thumb:hover{ background:var(--scroll-thumb-hover); background-clip:padding-box; }

  a{ color:inherit; }
  button{ font-family:inherit; }
  :focus-visible{ outline:2px solid var(--accent-cyan); outline-offset:2px; border-radius:6px; }

  /* ---------------- ambient background ---------------- */
  .bg-blobs{ position:fixed; inset:0; overflow:hidden; z-index:0; pointer-events:none; }
  .blob{ position:absolute; border-radius:50%; filter:blur(90px); animation:drift 24s ease-in-out infinite; }
  .b1{ width:520px; height:520px; background:var(--accent-cyan); opacity:var(--blob-1); top:-200px; left:-160px; }
  .b2{ width:460px; height:460px; background:var(--accent-violet); opacity:var(--blob-2); bottom:-200px; right:-140px; animation-duration:28s; animation-delay:-6s; }
  .b3{ width:360px; height:360px; background:var(--accent-mint); opacity:var(--blob-3); top:38%; left:58%; animation-duration:32s; animation-delay:-13s; }
  .grain{ position:fixed; inset:0; z-index:0; pointer-events:none; opacity:var(--grain-a);
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"); }

  @keyframes drift{
    0%,100%{ transform:translate(0,0) scale(1); }
    33%{ transform:translate(26px,-22px) scale(1.06); }
    66%{ transform:translate(-22px,16px) scale(.96); }
  }

  /* ---------------- header ---------------- */
  .topbar{
    position:relative; z-index:10; flex:0 0 auto;
    display:flex; align-items:center; gap:14px;
    padding:14px 20px; border-bottom:1px solid var(--border-soft);
    background:var(--bar-bg);
    backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
    transition:background .45s var(--ease), border-color .45s var(--ease);
  }
  .brand{ display:flex; align-items:center; gap:9px; font-family:var(--font-display); font-weight:700; letter-spacing:.06em; font-size:15px; }
  .brand svg{ width:22px; height:22px; color:var(--accent-mint); filter:drop-shadow(0 0 8px rgba(51,230,166,.5)); }
  .admin-badge{ display:flex; align-items:center; gap:6px; font-size:12px; color:var(--accent-mint); background:rgba(51,230,166,.08); border:1px solid rgba(51,230,166,.25); padding:5px 10px; border-radius:99px; font-weight:600; }
  .admin-badge svg{ width:13px; height:13px; }

  .status-pill{
    margin-left:auto; display:flex; align-items:center; gap:8px;
    padding:7px 14px 7px 11px; border-radius:99px; border:1px solid var(--border);
    background:var(--bg-1); font-size:13px; font-weight:600; color:var(--text-1);
    transition:border-color .4s var(--ease), color .4s var(--ease);
  }
  .dot{ position:relative; width:8px; height:8px; border-radius:50%; background:var(--accent-coral); flex:0 0 auto; }
  .dot::after{ content:""; position:absolute; inset:-4px; border-radius:50%; background:var(--accent-coral); opacity:.6; animation:ringPulse 1.9s ease-out infinite; }
  @keyframes ringPulse{ 0%{ transform:scale(.4); opacity:.55; } 100%{ transform:scale(2.4); opacity:0; } }

  .status-pill.testing{ color:var(--accent-amber); border-color:rgba(255,182,72,.35); }
  .status-pill.testing .dot, .status-pill.testing .dot::after{ background:var(--accent-amber); }
  .status-pill.connected{ color:var(--accent-mint); border-color:rgba(51,230,166,.35); }
  .status-pill.connected .dot, .status-pill.connected .dot::after{ background:var(--accent-mint); }
  .status-pill.local{ color:var(--accent-cyan); border-color:rgba(79,209,255,.35); }
  .status-pill.local .dot, .status-pill.local .dot::after{ background:var(--accent-cyan); }
  .status-pill.idle{ color:var(--text-1); border-color:var(--border); }
  .status-pill.idle .dot, .status-pill.idle .dot::after{ background:var(--accent-coral); }

  .icon-btn{
    display:flex; align-items:center; justify-content:center;
    width:36px; height:36px; border-radius:10px; border:1px solid var(--border);
    background:var(--bg-1); color:var(--text-1); cursor:pointer;
    transition:transform .35s var(--ease), color .2s ease, border-color .2s ease, background .2s ease;
  }
  .icon-btn:hover{ color:var(--text-0); border-color:rgba(255,255,255,.18); background:var(--bg-2); }
  .icon-btn.gear:hover{ transform:none; }
  .icon-btn svg{ width:17px; height:17px; }
  .icon-btn.small{ width:28px; height:28px; border-radius:8px; }
  .icon-btn.palette:hover{ transform:none; }
  .icon-btn.gear svg, .icon-btn.palette svg{ display:block; transform-origin:50% 50%; transform-box:view-box; transition:transform .35s ease; }
  .icon-btn.gear:hover svg, .icon-btn.palette:hover svg{ transform:rotate(70deg); }

  /* ---------------- верхние вкладки разделов ---------------- */
  .view-tabs{
    position:relative; display:flex; gap:2px; padding:4px; flex:0 0 auto;
    border:1px solid var(--border); border-radius:99px; background:var(--bg-1);
    transition:background .45s var(--ease), border-color .45s var(--ease);
  }
  .view-tab{
    position:relative; z-index:1; border:none; background:none; cursor:pointer;
    padding:7px 16px; border-radius:99px; font-size:12.5px; font-weight:600;
    color:var(--text-1); white-space:nowrap; transition:color .3s var(--ease);
  }
  .view-tab:hover{ color:var(--text-0); }
  .view-tab.active{ color:var(--on-accent); }
  .view-tabs .glider{
    position:absolute; z-index:0; top:4px; bottom:4px; left:0; width:0;
    border-radius:99px; background:linear-gradient(120deg, var(--accent-mint), var(--accent-cyan));
    box-shadow:0 6px 18px -8px var(--accent-cyan);
    transition:transform .45s var(--ease), width .45s var(--ease);
  }

  /* ---------------- тумблер «Лучший поиск» ---------------- */
  .switch-wrap{
    display:inline-flex; align-items:center; gap:9px; cursor:pointer; user-select:none;
    padding:4px 8px 4px 6px; border-radius:99px;
    transition:background .2s ease, opacity .3s var(--ease), transform .3s var(--ease);
  }
  .switch-wrap:hover{ background:var(--hover-soft); }
  .switch{
    position:relative; flex:0 0 auto; width:42px; height:23px; border-radius:99px;
    background:var(--bg-2); border:1px solid var(--border);
    transition:background .35s var(--ease), border-color .35s var(--ease), box-shadow .35s var(--ease);
  }
  .switch::after{
    content:""; position:absolute; top:2px; left:2px; width:17px; height:17px; border-radius:50%;
    background:var(--text-2);
    transition:transform .38s cubic-bezier(.4,1.6,.5,1), background .3s var(--ease), box-shadow .3s var(--ease);
  }
  .switch-wrap.on .switch{ background:rgba(51,230,166,.16); border-color:var(--accent-mint); box-shadow:0 0 14px -4px var(--accent-mint); }
  .switch-wrap.on .switch::after{ transform:translateX(19px); background:var(--accent-mint); box-shadow:0 0 10px var(--accent-mint); }
  .switch-text{ display:flex; flex-direction:column; line-height:1.15; }
  .switch-text b{ font-size:12.5px; font-weight:600; color:var(--text-1); transition:color .3s var(--ease); }
  .switch-text small{ font-size:10.5px; color:var(--text-2); }
  .switch-wrap.on .switch-text b{ color:var(--accent-mint); }
  .only-main{ transition:opacity .3s var(--ease), transform .3s var(--ease); }
  body.view-tg .only-main{ opacity:0; pointer-events:none; transform:translateY(-6px); }

  /* ---------------- слайдер разделов ---------------- */
  .views{ position:relative; z-index:1; flex:1; min-height:0; overflow:hidden; }
  .view{
    position:absolute; inset:0; display:flex; flex-direction:column; gap:14px;
    padding:18px 22px 14px; overflow:hidden;
    transition:transform .5s var(--ease), opacity .38s var(--ease);
    will-change:transform, opacity;
  }
  .view.scroll{ overflow-y:auto; }
  .view[data-pos="center"]{ transform:translateX(0); opacity:1; pointer-events:auto; }
  .view[data-pos="left"]{ transform:translateX(-100%); opacity:0; pointer-events:none; }
  .view[data-pos="right"]{ transform:translateX(100%); opacity:0; pointer-events:none; }

  /* ---------------- раздел Telegram ---------------- */
  .cta.tg{ background:linear-gradient(120deg, var(--accent-cyan), var(--accent-violet) 55%, var(--accent-cyan)); background-size:220% 100%; box-shadow:0 10px 26px -10px rgba(79,209,255,.5); }
  .cta.tg.on{ background:linear-gradient(120deg, var(--accent-coral), var(--accent-amber) 55%, var(--accent-coral)); background-size:220% 100%; box-shadow:0 10px 26px -10px rgba(255,92,114,.5); }
  .tg-apply{
    position:relative; overflow:hidden; margin-top:14px;
    display:inline-flex; align-items:center; gap:9px;
    padding:11px 22px; border-radius:99px; cursor:pointer;
    border:1px solid rgba(79,209,255,.4); background:var(--bg-1); color:var(--accent-cyan);
    font-family:var(--font-body); font-size:13.5px; font-weight:600;
    transition:transform .2s var(--ease), box-shadow .3s var(--ease), background .3s var(--ease), color .25s ease, opacity .25s ease;
  }
  .tg-apply::before{
    content:""; position:absolute; inset:0; border-radius:99px;
    background:linear-gradient(120deg, transparent, rgba(79,209,255,.28), transparent);
    transform:translateX(-120%); transition:transform .7s var(--ease);
  }
  .tg-apply:hover::before{ transform:translateX(120%); }
  .tg-apply:hover:not(:disabled){ transform:translateY(-2px); box-shadow:0 12px 28px -12px var(--accent-cyan); }
  .tg-apply:active:not(:disabled){ transform:translateY(0) scale(.98); }
  .tg-apply:disabled{ opacity:.4; cursor:not-allowed; }
  .tg-apply svg{ width:16px; height:16px; }
  .tg-apply.pulse{ animation:tgPulse 2.1s var(--ease) infinite; }
  @keyframes tgPulse{ 0%,100%{ box-shadow:0 0 0 0 rgba(79,209,255,.4); } 50%{ box-shadow:0 0 0 12px rgba(79,209,255,0); } }

  .tg-info{ margin:20px auto 0; max-width:560px; display:flex; flex-direction:column; gap:9px; text-align:left; }
  .tg-row{ display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:12px; background:var(--bg-0); border:1px solid var(--border-soft); transition:background .45s var(--ease), border-color .45s var(--ease); }
  .tg-row .k{ font-size:12px; color:var(--text-2); min-width:78px; font-weight:600; }
  .tg-row .v{ font-family:var(--font-mono); font-size:12px; color:var(--text-0); word-break:break-all; }
  .tg-note{ margin:16px auto 0; max-width:560px; font-size:12.5px; color:var(--text-2); line-height:1.6; }

  /* ---------------- карточки тем ---------------- */
  .theme-grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:6px; }
  .theme-card{
    cursor:pointer; border:1px solid var(--border); border-radius:14px; padding:10px 10px 12px;
    background:var(--bg-0); text-align:center;
    transition:transform .22s var(--ease), border-color .25s ease, box-shadow .3s var(--ease);
  }
  .theme-card:hover{ transform:translateY(-3px); }
  .theme-card.active{ border-color:var(--accent-mint); box-shadow:0 10px 26px -14px var(--accent-mint); }
  .theme-prev{ height:46px; border-radius:10px; margin-bottom:8px; position:relative; overflow:hidden; border:1px solid rgba(127,127,160,.25); }
  .theme-prev::after{ content:""; position:absolute; left:8px; right:8px; bottom:9px; height:7px; border-radius:99px; }
  .theme-prev.p-standard{ background:linear-gradient(160deg,#12162c,#090c1a); }
  .theme-prev.p-standard::after{ background:linear-gradient(90deg,#33e6a6,#4fd1ff); }
  .theme-prev.p-modern{ background:#010101; border-color:#f5f5f5; border-radius:0; }
  .theme-prev.p-modern::after{ background:#f5f5f5; border-radius:0; height:5px; }
  .theme-prev.p-ios26{ background:radial-gradient(60% 90% at 0% 0%,#6a8fbd,transparent 70%),radial-gradient(60% 90% at 100% 40%,#f2352c,transparent 70%),radial-gradient(80% 70% at 40% 120%,#45bdb9,transparent 70%),#a98aa6; }
  .theme-prev.p-ios26::after{ background:rgba(255,255,255,.55); box-shadow:inset 0 1px 0 rgba(255,255,255,.8); }
  .theme-name{ font-size:12.5px; font-weight:600; color:var(--text-1); }
  .theme-card.active .theme-name{ color:var(--accent-mint); }

  /* ---------------- сегментированный переключатель (Game Filter) ---------------- */
  .seg-row{ display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap; }
  .seg-btn{
    flex:1; min-width:62px; padding:8px 10px; border-radius:9px; border:1px solid var(--border);
    background:var(--bg-0); color:var(--text-1); font-family:var(--font-body);
    font-size:12px; font-weight:600; cursor:pointer;
    transition:background .25s var(--ease), color .25s ease, border-color .25s ease, transform .15s ease;
  }
  .seg-btn:hover{ color:var(--text-0); border-color:rgba(255,255,255,.2); transform:translateY(-1px); }
  .seg-btn.active{ background:linear-gradient(120deg, var(--accent-mint), var(--accent-cyan)); color:var(--on-accent); border-color:transparent; }

  /* ---------------- layout ---------------- */
  .page{ position:relative; z-index:1; flex:1; min-height:0; display:flex; flex-direction:column; gap:14px; padding:18px 22px 14px; overflow:hidden; }
  .card{ background:var(--bg-1); border:1px solid var(--border-soft); border-radius:var(--radius-lg); transition:background .45s var(--ease), border-color .45s var(--ease); }

  .hero{ flex:0 0 auto; padding:26px 24px 22px; text-align:center; position:relative; overflow:hidden; }
  .eyebrow{ margin:0 0 8px; font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:var(--accent-cyan); font-weight:600; }
  .hero h1{ margin:0; font-family:var(--font-display); font-weight:700; font-size:clamp(22px,3vw,30px); line-height:1.15; letter-spacing:-.01em; }
  .hero .sub{ margin:10px auto 0; max-width:520px; color:var(--text-1); font-size:14px; line-height:1.55; }

  /* radar signature */
  .radar-wrap{ position:relative; width:150px; height:150px; margin:22px auto 4px; --state-color:var(--accent-coral); }
  .radar-ring{ position:absolute; inset:0; border-radius:50%; border:2px solid var(--state-color); box-shadow:0 0 38px 2px var(--state-color); opacity:.85; transition:border-color .5s ease, box-shadow .5s ease; }
  .radar-sweep{
    position:absolute; inset:0; border-radius:50%;
    background:conic-gradient(from 0deg, transparent 0deg, var(--state-color) 16deg, transparent 62deg);
    -webkit-mask:radial-gradient(closest-side, transparent 60%, black 61%, black 100%);
    mask:radial-gradient(closest-side, transparent 60%, black 61%, black 100%);
    animation:spin 2.6s linear infinite; opacity:.9; transition:opacity .4s ease;
  }
  .radar-core{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; }
  .radar-core svg{ width:46px; height:46px; color:var(--state-color); filter:drop-shadow(0 0 14px var(--state-color)); animation:breathe 3.2s ease-in-out infinite; transition:color .5s ease; }
  @keyframes spin{ to{ transform:rotate(360deg); } }
  @keyframes breathe{ 0%,100%{ transform:scale(1); } 50%{ transform:scale(1.07); } }

  .radar-wrap.state-idle{ --state-color:var(--accent-coral); }
  .radar-wrap.state-idle .radar-sweep{ animation-play-state:paused; opacity:.28; }
  .radar-wrap.state-testing{ --state-color:var(--accent-amber); }
  .radar-wrap.state-testing .radar-sweep{ animation-duration:1s; opacity:1; }
  .radar-wrap.state-connected{ --state-color:var(--accent-mint); }
  .radar-wrap.state-connected .radar-sweep{ animation-play-state:paused; opacity:.55; }
  .radar-wrap.state-local{ --state-color:var(--accent-cyan); }
  .radar-wrap.state-local .radar-sweep{ animation-play-state:paused; opacity:.5; }

  .cta{
    position:relative; overflow:hidden; margin-top:6px;
    border:none; cursor:pointer; padding:16px 30px; border-radius:14px;
    font-family:var(--font-display); font-weight:600; font-size:16px; color:var(--on-accent);
    background:linear-gradient(120deg, var(--accent-mint), var(--accent-cyan) 55%, var(--accent-mint));
    background-size:220% 100%; background-position:0% 0%;
    box-shadow:0 10px 26px -10px rgba(51,230,166,.5);
    transition:background-position .55s ease, transform .18s ease, box-shadow .3s ease, opacity .2s ease;
    display:inline-flex; align-items:center; gap:10px;
  }
  .cta:hover:not(:disabled){ background-position:100% 0%; transform:translateY(-2px); box-shadow:0 14px 32px -8px rgba(51,230,166,.6); }
  .cta:active:not(:disabled){ transform:translateY(0) scale(.98); }
  .cta:disabled{ opacity:.72; cursor:not-allowed; }
  .cta .ripple{ position:absolute; border-radius:50%; background:rgba(255,255,255,.55); transform:scale(0); pointer-events:none; animation:rip .6s ease-out forwards; }
  @keyframes rip{ to{ transform:scale(3.4); opacity:0; } }
  .spinner{ width:15px; height:15px; border-radius:50%; border:2px solid currentColor; border-top-color:transparent; opacity:.8; animation:spin .7s linear infinite; }

  .auto-status{ margin:12px 0 0; font-size:13px; font-weight:600; color:var(--text-1); transition:color .3s ease; min-height:18px; }

  .link-inline{ margin-top:16px; background:none; border:none; cursor:pointer; color:var(--text-1); font-size:13px; font-family:var(--font-body); display:inline-flex; align-items:center; gap:5px; padding:6px 10px; border-radius:8px; transition:color .2s ease, background .2s ease; }
  .link-inline:hover{ color:var(--accent-cyan); background:rgba(79,209,255,.08); }
  .link-inline svg{ width:13px; height:13px; transition:transform .2s ease; }
  .link-inline:hover svg{ transform:translateX(3px); }

  /* terminal */
  .terminal{ flex:1; min-height:0; display:flex; flex-direction:column; overflow:hidden; }
  .terminal-head{ flex:0 0 auto; display:flex; align-items:center; gap:8px; padding:11px 16px; border-bottom:1px solid var(--border-soft); }
  .tdot{ width:9px; height:9px; border-radius:50%; opacity:.7; }
  .tdot.r{ background:var(--accent-coral); } .tdot.y{ background:var(--accent-amber); } .tdot.g{ background:var(--accent-mint); }
  .term-title{ margin-left:6px; font-family:var(--font-mono); font-size:12px; color:var(--text-2); }
  .terminal-body{
    flex:1; min-height:0; overflow-y:auto; padding:14px 18px 18px;
    font-family:var(--font-mono); font-size:12.5px; line-height:1.7; color:var(--text-1);
    background:var(--term-bg, radial-gradient(140% 100% at 0% 0%, rgba(79,209,255,.03), transparent 60%));
  }
  .log-line{ opacity:0; transform:translateY(4px); animation:lineIn .35s ease forwards; white-space:pre-wrap; word-break:break-word; }
  @keyframes lineIn{ to{ opacity:1; transform:none; } }
  .log-line.ok{ color:var(--accent-mint); }
  .log-line.err{ color:var(--accent-coral); }
  .log-line.warn{ color:var(--accent-amber); }
  .log-empty{ color:var(--text-2); font-style:italic; }
  .cursor-blink{ display:inline-block; width:7px; height:14px; margin-left:2px; background:var(--accent-mint); animation:blink 1s step-end infinite; vertical-align:-2px; }
  @keyframes blink{ 50%{ opacity:0; } }

  /* footer */
  .footbar{ position:relative; z-index:10; flex:0 0 auto; display:flex; gap:10px; padding:14px 22px; border-top:1px solid var(--border-soft); background:var(--bar-bg-up); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }
  .pill-btn{
    display:inline-flex; align-items:center; gap:8px; padding:10px 16px; border-radius:11px;
    font-size:13px; font-weight:600; cursor:pointer; border:1px solid var(--border); background:var(--bg-1); color:var(--text-1);
    transition:transform .18s var(--ease), border-color .2s ease, color .2s ease, box-shadow .25s ease, background .2s ease;
  }
  .pill-btn:hover{ transform:translateY(-2px); }
  .pill-btn:active{ transform:translateY(0); }
  .pill-btn.danger:hover{ color:var(--accent-coral); border-color:rgba(255,92,114,.4); box-shadow:0 8px 20px -10px rgba(255,92,114,.5); }
  .pill-btn.violet:hover{ color:var(--accent-violet); border-color:rgba(139,107,255,.4); box-shadow:0 8px 20px -10px rgba(139,107,255,.5); }
  .pill-btn.cyan:hover{ color:var(--accent-cyan); border-color:rgba(79,209,255,.4); box-shadow:0 8px 20px -10px rgba(79,209,255,.5); }
  .pill-btn.last{ margin-left:auto; }

  /* ---------------- overlay / drawers / modals ---------------- */
  .overlay{ position:fixed; inset:0; background:var(--overlay-bg); backdrop-filter:blur(5px); -webkit-backdrop-filter:blur(5px); opacity:0; pointer-events:none; transition:opacity .3s ease; z-index:40; }
  .overlay.show{ opacity:1; pointer-events:auto; }

  .drawer{
    position:fixed; top:0; right:0; height:100%; width:min(380px,92%);
    background:var(--bg-1); border-left:1px solid var(--border); z-index:50;
    display:flex; flex-direction:column; transform:translateX(100%);
    transition:transform .38s var(--ease); box-shadow:-24px 0 60px -20px rgba(0,0,0,.5);
  }
  .drawer.wide{ width:min(440px,92%); }
  .drawer.show{ transform:translateX(0); }
  .drawer-head{ flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; padding:18px 20px; border-bottom:1px solid var(--border-soft); }
  .drawer-head h3{ margin:0; font-family:var(--font-display); font-size:16px; font-weight:700; }
  .drawer-body{ flex:1; min-height:0; overflow-y:auto; padding:18px 20px 24px; }

  .hint{ margin:0 0 16px; font-size:13px; color:var(--text-1); line-height:1.6; }

  .domain-form{ display:flex; gap:8px; margin-bottom:16px; }
  .domain-form input{
    flex:1; background:var(--bg-0); border:1px solid var(--border); color:var(--text-0);
    border-radius:10px; padding:11px 13px; font-family:var(--font-mono); font-size:13px;
    transition:border-color .2s ease, box-shadow .2s ease;
  }
  .domain-form input:focus{ outline:none; border-color:var(--accent-cyan); box-shadow:0 0 0 3px rgba(79,209,255,.15); }
  .domain-form button{ width:42px; border-radius:10px; border:none; background:var(--accent-mint); color:var(--on-accent); font-size:19px; font-weight:700; cursor:pointer; transition:filter .2s ease, transform .15s ease; }
  .domain-form button:hover{ filter:brightness(1.08); transform:translateY(-1px); }

  .chk-row{ display:flex; align-items:flex-start; gap:10px; margin:0 0 12px; cursor:pointer; color:var(--text-0); font-size:14px; line-height:1.4; }
  .chk-row input{ width:18px; height:18px; margin:1px 0 0; accent-color:var(--accent-mint); cursor:pointer; flex:none; }
  .chk-row small{ display:block; color:var(--text-2); font-size:12px; margin-top:2px; }
  .ports-grid{ display:grid; grid-template-columns:auto 1fr; gap:8px 10px; align-items:center; margin-bottom:10px; }
  .ports-grid label{ font-size:12px; color:var(--text-1); font-weight:600; }
  .ports-grid input{
    background:var(--bg-0); border:1px solid var(--border); color:var(--text-0);
    border-radius:10px; padding:9px 12px; font-family:var(--font-mono); font-size:13px;
    transition:border-color .2s ease, box-shadow .2s ease; min-width:0;
  }
  .ports-grid input:focus{ outline:none; border-color:var(--accent-cyan); box-shadow:0 0 0 3px rgba(79,209,255,.15); }

  .chip-list{ display:flex; flex-wrap:wrap; gap:8px; }
  .chip{
    display:flex; align-items:center; gap:7px; background:var(--bg-2); border:1px solid var(--border);
    border-radius:99px; padding:7px 8px 7px 13px; font-family:var(--font-mono); font-size:12.5px;
    animation:chipIn .25s var(--ease); transition:opacity .2s ease, transform .2s ease;
  }
  .chip.removing{ opacity:0; transform:scale(.85); }
  @keyframes chipIn{ from{ opacity:0; transform:scale(.85); } to{ opacity:1; transform:scale(1); } }
  .chip button{ width:18px; height:18px; border-radius:50%; border:none; background:rgba(255,255,255,.08); color:var(--text-1); cursor:pointer; font-size:12px; line-height:1; display:flex; align-items:center; justify-content:center; transition:background .2s ease, color .2s ease; }
  .chip button:hover{ background:var(--accent-coral); color:#fff; }
  .empty-note{ color:var(--text-2); font-size:13px; font-style:italic; }

  .tabs{ position:relative; display:flex; flex:0 0 auto; padding:0 20px; border-bottom:1px solid var(--border-soft); }
  .tab{ flex:1; text-align:center; padding:13px 4px; font-size:13px; font-weight:600; color:var(--text-1); cursor:pointer; transition:color .25s ease; }
  .tab.active{ color:var(--text-0); }
  .tab-indicator{ position:absolute; bottom:-1px; height:2px; background:var(--accent-cyan); border-radius:2px; transition:transform .32s var(--ease), width .32s var(--ease); box-shadow:0 0 10px var(--accent-cyan); }

  .tab-panel{ display:none; animation:fadeUp .3s var(--ease); }
  .tab-panel.active{ display:block; }
  @keyframes fadeUp{ from{ opacity:0; transform:translateY(6px); } to{ opacity:1; transform:none; } }

  .field-label{ display:block; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--text-2); margin:0 0 8px; font-weight:600; }
  .select{
    width:100%; background:var(--bg-0); border:1px solid var(--border); color:var(--text-0);
    padding:11px 13px; border-radius:10px; font-family:var(--font-mono); font-size:12.5px; margin-bottom:16px;
    transition:border-color .2s ease;
  }
  .select:focus{ outline:none; border-color:var(--accent-cyan); }

  .btn-row{ display:flex; gap:10px; flex-wrap:wrap; }
  .btn{ flex:1; min-width:130px; padding:11px 14px; border-radius:10px; border:1px solid var(--border); background:var(--bg-2); color:var(--text-0); font-size:13px; font-weight:600; cursor:pointer; transition:transform .15s ease, border-color .2s ease, box-shadow .25s ease; }
  .btn:hover{ transform:translateY(-1px); }
  .btn.success{ border-color:rgba(51,230,166,.35); } .btn.success:hover{ box-shadow:0 8px 20px -10px rgba(51,230,166,.5); color:var(--accent-mint); }
  .btn.danger{ border-color:rgba(255,92,114,.35); } .btn.danger:hover{ box-shadow:0 8px 20px -10px rgba(255,92,114,.5); color:var(--accent-coral); }
  .btn.info{ border-color:rgba(79,209,255,.35); } .btn.info:hover{ box-shadow:0 8px 20px -10px rgba(79,209,255,.5); color:var(--accent-cyan); }
  .btn.violet{ border-color:rgba(139,107,255,.35); } .btn.violet:hover{ box-shadow:0 8px 20px -10px rgba(139,107,255,.5); color:var(--accent-violet); }

  .divider{ border:none; border-top:1px solid var(--border-soft); margin:22px 0; }

  .modal{
    position:fixed; top:50%; left:50%; width:min(560px,90%); max-height:78vh;
    background:var(--bg-1); border:1px solid var(--border); border-radius:18px; z-index:55;
    transform:translate(-50%,-46%) scale(.96); opacity:0; pointer-events:none;
    transition:transform .32s var(--ease), opacity .25s ease; overflow:hidden;
    display:flex; flex-direction:column; box-shadow:0 30px 80px -20px rgba(0,0,0,.6);
  }
  .modal.show{ transform:translate(-50%,-50%) scale(1); opacity:1; pointer-events:auto; }
  .modal-head{ flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; padding:18px 22px; border-bottom:1px solid var(--border-soft); }
  .modal-head h3{ margin:0; font-family:var(--font-display); font-size:17px; }
  .modal-body{ flex:1; min-height:0; overflow-y:auto; padding:20px 22px 26px; font-size:13.5px; line-height:1.75; color:var(--text-1); }
  .modal-body h4{ margin:20px 0 8px; color:var(--text-0); font-size:14px; font-family:var(--font-display); }
  .modal-body h4:first-child{ margin-top:0; }
  .modal-body ul{ margin:6px 0; padding-left:20px; }
  .modal-body li{ margin:4px 0; }
  .modal-body strong{ color:var(--text-0); }
  .modal-body p.warn-box{ margin-top:18px; padding:12px 14px; border-radius:10px; background:rgba(255,182,72,.08); border:1px solid rgba(255,182,72,.25); color:var(--accent-amber); font-size:12.5px; }
  .reveal{ opacity:0; transform:translateY(8px); animation:revealIn .4s var(--ease) forwards; }
  @keyframes revealIn{ to{ opacity:1; transform:none; } }

  /* toasts */
  .toasts{ pointer-events:none; position:fixed; bottom:64px; left:16px; z-index:70; display:flex; flex-direction:column; gap:10px; max-width:min(320px, calc(100vw - 32px)); }
  .toast{
    background:var(--bg-2); border:1px solid var(--border); padding:12px 15px; border-radius:12px;
    font-size:12.5px; color:var(--text-0); box-shadow:0 16px 34px -12px rgba(0,0,0,.55);
    display:flex; align-items:center; gap:9px;
    animation:toastIn .25s ease both;
  }
  .toast .tdotc{ width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
  .toast.success .tdotc{ background:var(--accent-mint); box-shadow:0 0 8px var(--accent-mint); }
  .toast.error .tdotc{ background:var(--accent-coral); box-shadow:0 0 8px var(--accent-coral); }
  .toast.info .tdotc{ background:var(--accent-cyan); box-shadow:0 0 8px var(--accent-cyan); }
  @keyframes toastIn{ from{ transform:translateX(120%); opacity:0; } to{ transform:translateX(0); opacity:1; } }
  @keyframes toastOut{ to{ transform:translateX(120%); opacity:0; } }

  @media (prefers-reduced-motion: reduce){
    *{ animation-duration:.001ms !important; animation-iteration-count:1 !important; transition-duration:.001ms !important; }
    .blob{ display:none; }
  }

  /* ======================= КОМПАКТНЫЙ РЕЖИМ ======================= */
  .topbar{ gap:10px; padding:8px 14px; }
  .brand{ font-size:14px; }
  .brand svg{ width:19px; height:19px; }
  .status-pill{ padding:5px 12px 5px 10px; font-size:12px; }
  .icon-btn{ width:30px; height:30px; border-radius:9px; }
  .icon-btn svg{ width:15px; height:15px; }
  .view-tabs{ padding:3px; }
  .view-tab{ padding:5px 13px; font-size:12px; }
  .view-tabs .glider{ top:3px; bottom:3px; }

  .view{ gap:10px; padding:10px 14px 8px; overflow-y:auto; overflow-x:hidden; }
  .card{ border-radius:16px; }

  /* герой: радар слева, всё остальное справа */
  .hero{
    display:grid; grid-template-columns:auto minmax(0,1fr); column-gap:22px; row-gap:6px;
    align-items:center; justify-items:start; text-align:left; padding:14px 20px; flex:0 0 auto;
  }
  .hero > .radar-wrap{ grid-column:1; grid-row:1 / span 7; margin:0; width:112px; height:112px; }
  .hero > :not(.radar-wrap){ grid-column:2; margin-top:0; margin-bottom:0; }
  .radar-core svg{ width:36px; height:36px; }
  .radar-ring{ box-shadow:0 0 26px 1px var(--state-color); }
  .eyebrow{ display:none; }
  .hero h1{ font-size:clamp(18px,2.4vw,23px); }
  .hero h1 br{ display:none; }
  .cta{ margin-top:2px; padding:11px 24px; font-size:14.5px; border-radius:12px; }
  .auto-status{ margin:0; font-size:12.5px; min-height:0; }
  .link-inline{ margin-top:0; padding:3px 8px 3px 0; font-size:12px; }
  .tg-apply{ margin-top:0; padding:8px 18px; font-size:12.5px; }

  /* раскрывающиеся блоки «Подробнее» */
  details.more{ width:100%; }
  details.more > summary{
    list-style:none; cursor:pointer; display:inline-flex; align-items:center; gap:6px;
    font-size:12px; color:var(--text-2); padding:2px 0; user-select:none; transition:color .2s ease;
  }
  details.more > summary::-webkit-details-marker{ display:none; }
  details.more > summary::before{ content:"▸"; font-size:10px; transition:transform .2s var(--ease); }
  details.more[open] > summary::before{ transform:rotate(90deg); }
  details.more > summary:hover{ color:var(--accent-cyan); }
  details.more .sub{ margin:4px 0 0; max-width:none; font-size:12.5px; line-height:1.5; color:var(--text-1); }
  .tg-info{ margin:8px 0 0; max-width:none; gap:6px; }
  .tg-row{ padding:6px 11px; border-radius:10px; }
  .tg-note{ margin:8px 0 0; max-width:none; font-size:12px; line-height:1.5; }

  /* лог */
  .terminal{ flex:1 1 auto; min-height:110px; }
  .terminal-head{ padding:6px 12px; }
  .terminal-body{ padding:8px 14px 10px; font-size:12px; line-height:1.55; }

  /* нижняя панель */
  .footbar{ gap:8px; padding:7px 14px; }
  .pill-btn{ padding:6px 12px; font-size:12px; border-radius:9px; gap:6px; }

  /* боковые панели */
  .drawer{ width:min(340px,92%); }
  .drawer.wide{ width:min(380px,92%); }
  .drawer-head{ padding:11px 16px; }
  .drawer-body{ padding:12px 16px 16px; }
  .hint{ font-size:12px; line-height:1.5; margin:0 0 10px; }
  .hint code{ font-family:var(--font-mono); color:var(--accent-cyan); }
  .divider{ margin:14px 0; }
  .field-label{ margin:0 0 6px; font-size:11px; }
  .theme-prev{ height:30px; margin-bottom:6px; }
  .theme-card{ padding:7px 7px 8px; border-radius:11px; }
  .theme-name{ font-size:12px; }
  .domain-form{ margin-bottom:10px; }
  .chk-row{ margin:0 0 9px; font-size:13px; }
  .switch-wrap{ padding:2px 6px 2px 0; margin-bottom:6px; }

  /* низкие экраны (ноутбуки 1366x768 и ниже, 13xx x 7xx) */
  @media (max-height:700px){
    .topbar{ padding:6px 12px; }
    .hero{ padding:10px 16px; row-gap:4px; }
    .hero > .radar-wrap{ width:92px; height:92px; }
    .radar-core svg{ width:30px; height:30px; }
    .cta{ padding:9px 22px; font-size:14px; }
    .terminal{ min-height:90px; }
    .footbar{ padding:5px 12px; }
    .view{ padding:8px 12px 6px; gap:8px; }
  }
  @media (max-height:560px){
    .hero > .radar-wrap{ width:72px; height:72px; }
    .radar-core svg{ width:26px; height:26px; }
  }
  /* узкие окна */
  @media (max-width:860px){
    .brand span{ display:none; }
    .hero{ column-gap:14px; padding-left:14px; padding-right:14px; }
    .hero > .radar-wrap{ width:84px; height:84px; }
  }


  /* ----- раздел «Оформление» ----- */
  .theme-grid{ grid-template-columns:1fr; gap:8px; margin-bottom:12px; }
  .theme-card{ display:flex; align-items:center; gap:14px; text-align:left; padding:8px 12px 8px 8px; }
  .theme-card .theme-prev{ flex:0 0 76px; width:76px; height:46px; margin:0; }
  .theme-card .theme-meta{ display:flex; flex-direction:column; gap:2px; min-width:0; }
  .theme-card .theme-desc{ font-size:11.5px; color:var(--text-2); }
  .variant-row{ margin:4px 0 12px; }
  .swatches{ display:flex; flex-wrap:wrap; gap:10px; }
  .swatch{ display:flex; flex-direction:column; align-items:center; gap:5px; background:none; border:none; padding:0; cursor:pointer; color:var(--text-2); font-family:inherit; }
  .swatch .sw{ width:40px; height:40px; border-radius:50%; border:2px solid var(--border-soft); transition:transform .2s var(--ease), box-shadow .2s ease; }
  .swatch:hover .sw{ transform:scale(1.07); }
  .swatch small{ font-size:10.5px; }
  .swatch.active .sw{ box-shadow:0 0 0 2px var(--bg-0), 0 0 0 4px var(--text-0); }
  .swatch.active{ color:var(--text-0); }
  .sw-photo{ background:radial-gradient(60% 60% at 0% 0%,#6a8fbd,transparent 70%),radial-gradient(60% 70% at 100% 40%,#f2352c,transparent 70%),radial-gradient(80% 60% at 40% 120%,#45bdb9,transparent 70%),#a98aa6; }
  .sw-aurora{ background:radial-gradient(60% 60% at 0% 0%,#2a6cf0,transparent 70%),radial-gradient(60% 70% at 100% 40%,#2fe3a0,transparent 70%),radial-gradient(80% 60% at 40% 120%,#8a5cf0,transparent 70%),#0f2a2e; }
  .sw-ocean{ background:radial-gradient(60% 60% at 0% 0%,#1e6fe0,transparent 70%),radial-gradient(60% 70% at 100% 40%,#2fb6ff,transparent 70%),radial-gradient(80% 60% at 40% 120%,#12c7c0,transparent 70%),#0a2a4a; }
  .sw-sunset{ background:radial-gradient(60% 60% at 0% 0%,#ff8a3d,transparent 70%),radial-gradient(60% 70% at 100% 40%,#ff3d5a,transparent 70%),radial-gradient(80% 60% at 40% 120%,#d6409f,transparent 70%),#6a2a52; }
  .sw-graphite{ background:radial-gradient(60% 60% at 0% 0%,#5a5a62,transparent 70%),radial-gradient(60% 70% at 100% 40%,#8e8e93,transparent 70%),radial-gradient(80% 60% at 40% 120%,#4a4a52,transparent 70%),#2b2b30; }
  .b4, .b5{ display:none; }

  /* ======================= ТЕМА «МОДЕРН 010101» ======================= */
  html[data-theme="modern"]{
    --bg-0:#010101; --bg-1:#010101; --bg-2:#151515;
    --ink:#f5f5f5; --border:#f5f5f5; --border-soft:rgba(245,245,245,.16);
    --text-0:#f5f5f5; --text-1:#b4b4b4; --text-2:#777777;
    --accent-mint:#f5f5f5; --accent-cyan:#f5f5f5; --accent-amber:#b4b4b4; --accent-coral:#f5f5f5; --accent-violet:#f5f5f5;
    --on-accent:#010101; --bar-bg:#010101; --bar-bg-up:#010101;
    --overlay-bg:rgba(0,0,0,.75); --hover-soft:rgba(245,245,245,.08); --scroll-thumb-hover:#f5f5f5;
    --font-display:'Space Grotesk','Bahnschrift','Segoe UI',system-ui,sans-serif;
    --font-body:'Inter','Segoe UI',system-ui,sans-serif;
    --radius-lg:0; --radius-md:0; --radius-sm:0;
  }
  html[data-theme="modern"][data-scheme="white"]{
    --bg-0:#ffffff; --bg-1:#ffffff; --bg-2:#f1f1ef;
    --ink:#0a0a0a; --border:#0a0a0a; --border-soft:rgba(10,10,10,.14);
    --text-0:#0a0a0a; --text-1:#454545; --text-2:#8a8a8a;
    --accent-mint:#0a0a0a; --accent-cyan:#0a0a0a; --accent-amber:#454545; --accent-coral:#0a0a0a; --accent-violet:#0a0a0a;
    --on-accent:#ffffff; --bar-bg:#ffffff; --bar-bg-up:#ffffff;
    --overlay-bg:rgba(10,10,10,.5); --hover-soft:rgba(10,10,10,.06); --scroll-thumb-hover:#0a0a0a;
  }
  html[data-theme="modern"][data-scheme="classic"]{
    --bg-0:#e7e7e4; --bg-1:#e7e7e4; --bg-2:#d9d9d5;
    --ink:#0a0a0a; --border:#0a0a0a; --border-soft:rgba(10,10,10,.18);
    --text-0:#0a0a0a; --text-1:#3d3d3d; --text-2:#777771;
    --accent-mint:#0a0a0a; --accent-cyan:#0a0a0a; --accent-amber:#3d3d3d; --accent-coral:#0a0a0a; --accent-violet:#0a0a0a;
    --on-accent:#e7e7e4; --bar-bg:#e7e7e4; --bar-bg-up:#e7e7e4;
    --overlay-bg:rgba(10,10,10,.5); --hover-soft:rgba(10,10,10,.07); --scroll-thumb-hover:#0a0a0a;
  }
  html[data-theme="modern"] .bg-blobs,
  html[data-theme="modern"] .grain{ display:none; }
  html[data-theme="modern"] *{ border-radius:0; }
  html[data-theme="modern"] .view-tab,
  html[data-theme="modern"] .view-tabs,
  html[data-theme="modern"] .card,
  html[data-theme="modern"] .hero,
  html[data-theme="modern"] .terminal,
  html[data-theme="modern"] .terminal-body,
  html[data-theme="modern"] .btn,
  html[data-theme="modern"] .pill-btn,
  html[data-theme="modern"] .cta,
  html[data-theme="modern"] .tg-apply,
  html[data-theme="modern"] .icon-btn,
  html[data-theme="modern"] .drawer,
  html[data-theme="modern"] .modal,
  html[data-theme="modern"] .toast,
  html[data-theme="modern"] .chip,
  html[data-theme="modern"] .select,
  html[data-theme="modern"] .theme-card,
  html[data-theme="modern"] .theme-prev,
  html[data-theme="modern"] .seg-btn,
  html[data-theme="modern"] .tab-indicator,
  html[data-theme="modern"] .tg-row,
  html[data-theme="modern"] .icon-btn.small,
  html[data-theme="modern"] .icon-btn.gear,
  html[data-theme="modern"] .icon-btn.palette{ border-radius:0; }
  html[data-theme="modern"] .dot,
  html[data-theme="modern"] .dot::after,
  html[data-theme="modern"] .radar-wrap,
  html[data-theme="modern"] .radar-wrap *,
  html[data-theme="modern"] .spinner,
  html[data-theme="modern"] .tdot,
  html[data-theme="modern"] .cta .ripple{ border-radius:50%; }
  html[data-theme="modern"] ::-webkit-scrollbar{ width:8px; height:8px; }
  html[data-theme="modern"] ::-webkit-scrollbar-thumb{ background:var(--text-2); border:none; border-radius:0; }
  html[data-theme="modern"] ::-webkit-scrollbar-thumb:hover{ background:var(--ink); }
  html[data-theme="modern"] :focus-visible{ outline:2px solid var(--ink); outline-offset:2px; border-radius:0; }
  html[data-theme="modern"] ::selection{ background:var(--ink); color:var(--on-accent); }
  html[data-theme="modern"] .btn,
  html[data-theme="modern"] .pill-btn,
  html[data-theme="modern"] .toast,
  html[data-theme="modern"] .terminal-body,
  html[data-theme="modern"] .modal-body{ -webkit-filter:grayscale(1); filter:grayscale(1); }
  html[data-theme="modern"] .topbar{ height:52px; padding:0 22px; gap:30px; background:var(--bg-0); border-bottom:1px solid var(--border); backdrop-filter:none; -webkit-backdrop-filter:none; }
  html[data-theme="modern"] .brand{ font-size:14px; letter-spacing:.24em; font-weight:700; }
  html[data-theme="modern"] .brand svg{ width:18px; height:18px; color:var(--ink); filter:none; }
  html[data-theme="modern"] .view-tabs{ align-self:stretch; padding:0; gap:24px; border:none; background:none; }
  html[data-theme="modern"] .view-tabs .glider{ display:none; }
  html[data-theme="modern"] .view-tab{ height:100%; padding:0; background:none; font-size:11.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--text-2); box-shadow:inset 0 -3px 0 transparent; transition:color .2s ease, box-shadow .25s var(--ease); }
  html[data-theme="modern"] .view-tab:hover{ color:var(--text-0); }
  html[data-theme="modern"] .view-tab.active{ color:var(--text-0); box-shadow:inset 0 -3px 0 var(--ink); }
  html[data-theme="modern"] .status-pill,
  html[data-theme="modern"] .status-pill.idle,
  html[data-theme="modern"] .status-pill.testing,
  html[data-theme="modern"] .status-pill.connected,
  html[data-theme="modern"] .status-pill.local{
    padding:0; border:none; background:none; gap:9px; color:var(--text-0);
    font-size:11px; letter-spacing:.14em; text-transform:uppercase; font-weight:600;
  }
  html[data-theme="modern"] .status-pill .dot{ width:9px; height:9px; background:transparent; border:1.5px solid var(--text-2); }
  html[data-theme="modern"] .status-pill .dot::after{ inset:-5px; background:transparent; border:1px solid var(--ink); opacity:0; animation:none; }
  html[data-theme="modern"] .status-pill.idle .dot,
  html[data-theme="modern"] .status-pill.idle .dot::after{ background:transparent; }
  html[data-theme="modern"] .status-pill.testing .dot{ background:var(--ink); border-color:var(--ink); }
  html[data-theme="modern"] .status-pill.testing .dot::after{ background:transparent; opacity:.7; animation:ringPulse 1.4s ease-out infinite; }
  html[data-theme="modern"] .status-pill.connected .dot,
  html[data-theme="modern"] .status-pill.connected .dot::after{ background:var(--ink); border-color:var(--ink); }
  html[data-theme="modern"] .status-pill.connected .dot::after{ background:transparent; opacity:0; }
  html[data-theme="modern"] .status-pill.local .dot{ background:var(--ink); border-color:var(--ink); border-radius:0; }
  html[data-theme="modern"] .status-pill.local .dot::after{ background:transparent; opacity:0; border-radius:0; }
  html[data-theme="modern"] .icon-btn{ width:30px; height:30px; background:none; border:1px solid var(--border); color:var(--ink); }
  html[data-theme="modern"] .icon-btn:hover{ background:var(--ink); color:var(--on-accent); border-color:var(--ink); }
  html[data-theme="modern"] .icon-btn.gear:hover{ transform:none; }
  html[data-theme="modern"] .view{ padding:0 22px; gap:0; }
  html[data-theme="modern"] .card{ background:none; border:none; }
  html[data-theme="modern"] .hero{
    display:grid; grid-template-columns:minmax(0,1fr) auto; column-gap:36px; row-gap:10px;
    align-items:center; justify-items:start; text-align:left;
    padding:22px 0 20px; border-bottom:1px solid var(--border);
  }
  html[data-theme="modern"] .hero > .radar-wrap{ grid-column:2; grid-row:1 / span 7; width:124px; height:124px; margin:0 6px 0 0; }
  html[data-theme="modern"] .hero > :not(.radar-wrap){ grid-column:1; }
  html[data-theme="modern"] .eyebrow{ display:block; margin:0; font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:var(--text-2); font-weight:600; }
  html[data-theme="modern"] .hero h1{ font-size:clamp(26px,6.2vh,46px); line-height:1.04; letter-spacing:-.025em; font-weight:700; max-width:none; text-wrap:balance; }
  html[data-theme="modern"] details.more > summary{ font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--text-2); }
  html[data-theme="modern"] details.more > summary:hover{ color:var(--ink); }
  html[data-theme="modern"] details.more .sub{ font-size:13px; max-width:46em; }
  html[data-theme="modern"] .cta,
  html[data-theme="modern"] .cta.tg,
  html[data-theme="modern"] .cta.tg.on{
    margin-top:6px; padding:15px 26px; border:1px solid var(--ink); border-radius:0;
    background:var(--ink); color:var(--on-accent); box-shadow:none;
    font-family:var(--font-body); font-size:12px; font-weight:600; letter-spacing:.16em; text-transform:uppercase;
    transition:background .2s ease, color .2s ease, transform .15s ease;
  }
  html[data-theme="modern"] .cta::after{ content:"→"; font-size:15px; letter-spacing:0; transition:transform .25s var(--ease); }
  html[data-theme="modern"] .cta:hover:not(:disabled),
  html[data-theme="modern"] .cta.tg:hover:not(:disabled){ background:transparent; color:var(--ink); transform:none; box-shadow:none; }
  html[data-theme="modern"] .cta:hover:not(:disabled)::after{ transform:translateX(5px); }
  html[data-theme="modern"] .cta:active:not(:disabled){ transform:scale(.99); }
  html[data-theme="modern"] .cta.tg.on{ background:transparent; color:var(--ink); }
  html[data-theme="modern"] .cta.tg.on:hover:not(:disabled){ background:var(--ink); color:var(--on-accent); }
  html[data-theme="modern"] .cta .ripple{ background:rgba(128,128,128,.45); }
  html[data-theme="modern"] .auto-status{ font-size:12.5px; font-weight:500; color:var(--text-1); }
  html[data-theme="modern"] .link-inline{ font-size:12px; color:var(--text-1); padding:3px 0; text-decoration:underline; text-underline-offset:4px; text-decoration-color:var(--border-soft); }
  html[data-theme="modern"] .link-inline:hover{ color:var(--ink); background:none; text-decoration-color:var(--ink); }
  html[data-theme="modern"] .tg-apply{ margin-top:0; border:1px solid var(--ink); background:none; color:var(--ink); padding:10px 20px; font-size:11.5px; letter-spacing:.12em; text-transform:uppercase; box-shadow:none; }
  html[data-theme="modern"] .tg-apply::before{ display:none; }
  html[data-theme="modern"] .tg-apply:hover:not(:disabled){ background:var(--ink); color:var(--on-accent); transform:none; box-shadow:none; }
  html[data-theme="modern"] .tg-apply.pulse{ animation:none; }
  html[data-theme="modern"] .tg-row{ background:none; border:none; border-bottom:1px solid var(--border-soft); padding:7px 0; }
  html[data-theme="modern"] .tg-row .k{ text-transform:uppercase; letter-spacing:.12em; font-size:10.5px; }
  html[data-theme="modern"] .radar-wrap::before{ content:""; position:absolute; inset:20px; border:1px solid var(--border-soft); border-radius:50%; }
  html[data-theme="modern"] .radar-wrap.state-idle{ --state-color:var(--text-2); }
  html[data-theme="modern"] .radar-wrap.state-testing,
  html[data-theme="modern"] .radar-wrap.state-connected,
  html[data-theme="modern"] .radar-wrap.state-local{ --state-color:var(--ink); }
  html[data-theme="modern"] .radar-ring{ border:1px solid var(--state-color); box-shadow:none; opacity:1; }
  html[data-theme="modern"] .radar-wrap.state-idle .radar-ring{ border-style:dashed; }
  html[data-theme="modern"] .radar-sweep{ background:conic-gradient(from 0deg, transparent 0deg, var(--ink) 14deg, transparent 50deg); }
  html[data-theme="modern"] .radar-wrap.state-idle .radar-sweep{ opacity:.12; }
  html[data-theme="modern"] .radar-core svg{ filter:none; width:38px; height:38px; }
  html[data-theme="modern"] .radar-wrap.state-connected .radar-core svg,
  html[data-theme="modern"] .radar-wrap.state-local .radar-core svg{ fill:currentColor; }
  html[data-theme="modern"] .terminal{ flex:1 1 auto; min-height:110px; }
  html[data-theme="modern"] .terminal-head{ padding:12px 0 8px; border:none; }
  html[data-theme="modern"] .tdot{ display:none; }
  html[data-theme="modern"] .term-title{ margin:0; font-family:var(--font-body); font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:var(--text-2); }
  html[data-theme="modern"] .terminal-body{ border:1px solid var(--border); background:none; padding:10px 14px; margin-bottom:12px; color:var(--text-2); }
  html[data-theme="modern"] .log-line.ok{ color:var(--text-0); }
  html[data-theme="modern"] .log-line.err{ color:var(--text-0); font-weight:700; background:var(--bg-2); box-shadow:-14px 0 0 var(--bg-2), 14px 0 0 var(--bg-2); }
  html[data-theme="modern"] .log-line.warn{ color:var(--text-1); font-style:italic; }
  html[data-theme="modern"] .cursor-blink{ background:var(--ink); border-radius:0; }
  html[data-theme="modern"] .footbar{ height:40px; padding:0 22px; gap:26px; align-items:center; background:var(--bg-0); border-top:1px solid var(--border); backdrop-filter:none; -webkit-backdrop-filter:none; }
  html[data-theme="modern"] .pill-btn,
  html[data-theme="modern"] .pill-btn.danger,
  html[data-theme="modern"] .pill-btn.violet,
  html[data-theme="modern"] .pill-btn.cyan{
    padding:0; border:none; background:none; box-shadow:none; color:var(--text-1);
    font-size:11px; letter-spacing:.14em; text-transform:uppercase; font-weight:600;
  }
  html[data-theme="modern"] .pill-btn:hover,
  html[data-theme="modern"] .pill-btn.danger:hover,
  html[data-theme="modern"] .pill-btn.violet:hover,
  html[data-theme="modern"] .pill-btn.cyan:hover{
    color:var(--ink); border:none; box-shadow:none; transform:none; text-decoration:underline; text-underline-offset:6px;
  }
  html[data-theme="modern"] .overlay{ backdrop-filter:none; -webkit-backdrop-filter:none; }
  html[data-theme="modern"] .drawer{ background:var(--bg-0); border-left:1px solid var(--border); box-shadow:none; }
  html[data-theme="modern"] .drawer-head,
  html[data-theme="modern"] .modal-head{ border-bottom:1px solid var(--border); }
  html[data-theme="modern"] .drawer-head h3,
  html[data-theme="modern"] .modal-head h3{ font-size:13px; letter-spacing:.18em; text-transform:uppercase; }
  html[data-theme="modern"] .modal{ background:var(--bg-0); border:1px solid var(--border); box-shadow:none; }
  html[data-theme="modern"] .modal-body p.warn-box{ background:none; border:1px dashed var(--ink); color:var(--ink); }
  html[data-theme="modern"] .tabs{ border-bottom:1px solid var(--border); }
  html[data-theme="modern"] .tab{ font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--text-2); }
  html[data-theme="modern"] .tab.active{ color:var(--text-0); }
  html[data-theme="modern"] .tab-indicator{ height:3px; background:var(--ink); box-shadow:none; border-radius:0; }
  html[data-theme="modern"] .field-label{ font-size:10.5px; letter-spacing:.18em; color:var(--text-2); }
  html[data-theme="modern"] .hint{ color:var(--text-1); }
  html[data-theme="modern"] .divider{ border-top:1px solid var(--border-soft); }
  html[data-theme="modern"] .btn,
  html[data-theme="modern"] .btn.success,
  html[data-theme="modern"] .btn.danger,
  html[data-theme="modern"] .btn.info,
  html[data-theme="modern"] .btn.violet{
    background:none; color:var(--ink); border:1px solid var(--ink); box-shadow:none;
    font-size:11.5px; letter-spacing:.1em; text-transform:uppercase;
    transition:background .2s ease, color .2s ease;
  }
  html[data-theme="modern"] .btn.danger{ border-style:dashed; }
  html[data-theme="modern"] .btn:hover,
  html[data-theme="modern"] .btn.success:hover,
  html[data-theme="modern"] .btn.danger:hover,
  html[data-theme="modern"] .btn.info:hover,
  html[data-theme="modern"] .btn.violet:hover{
    background:var(--ink); color:var(--on-accent); transform:none; box-shadow:none;
  }
  html[data-theme="modern"] .select,
  html[data-theme="modern"] .domain-form input,
  html[data-theme="modern"] .ports-grid input{ background:none; border:1px solid var(--ink); color:var(--text-0); }
  html[data-theme="modern"] .select:focus,
  html[data-theme="modern"] .domain-form input:focus,
  html[data-theme="modern"] .ports-grid input:focus{ border-color:var(--ink); box-shadow:inset 0 0 0 1px var(--ink); outline:none; }
  html[data-theme="modern"] .domain-form button{ background:var(--ink); color:var(--on-accent); border:1px solid var(--ink); }
  html[data-theme="modern"] .domain-form button:hover{ background:transparent; color:var(--ink); filter:none; transform:none; }
  html[data-theme="modern"] .ports-grid label{ text-transform:uppercase; letter-spacing:.12em; font-size:10.5px; }
  html[data-theme="modern"] .chip{ background:none; border:1px solid var(--ink); }
  html[data-theme="modern"] .chip button{ background:none; color:var(--ink); border:none; }
  html[data-theme="modern"] .chip button:hover{ background:var(--ink); color:var(--on-accent); }
  html[data-theme="modern"] .chk-row input{ accent-color:var(--ink); }
  html[data-theme="modern"] .switch{ width:38px; height:20px; border-radius:0; background:none; border:1px solid var(--ink); }
  html[data-theme="modern"] .switch::after{ top:3px; left:3px; width:12px; height:12px; border-radius:0; background:var(--ink); }
  html[data-theme="modern"] .switch-wrap.on .switch{ background:var(--ink); border-color:var(--ink); box-shadow:none; }
  html[data-theme="modern"] .switch-wrap.on .switch::after{ transform:translateX(18px); background:var(--on-accent); box-shadow:none; }
  html[data-theme="modern"] .switch-text b{ font-size:12.5px; }
  html[data-theme="modern"] .switch-wrap.on .switch-text b{ color:var(--ink); }
  html[data-theme="modern"] .theme-card{ border:1px solid var(--border-soft); background:none; }
  html[data-theme="modern"] .theme-card:hover{ transform:none; border-color:var(--ink); }
  html[data-theme="modern"] .theme-card.active{ border-color:var(--ink); box-shadow:inset 0 0 0 1px var(--ink); }
  html[data-theme="modern"] .theme-prev{ border:1px solid rgba(128,128,128,.5); }
  html[data-theme="modern"] .theme-prev::after{ border-radius:0; height:5px; }
  html[data-theme="modern"] .theme-card.active .theme-name{ color:var(--ink); }
  html[data-theme="modern"] .seg-btn{ background:none; border:1px solid var(--ink); color:var(--ink); text-transform:uppercase; letter-spacing:.08em; font-size:11px; }
  html[data-theme="modern"] .seg-btn:hover{ transform:none; border-color:var(--ink); }
  html[data-theme="modern"] .seg-btn.active{ background:var(--ink); color:var(--on-accent); }
  html[data-theme="modern"] .toast{ background:var(--bg-0); border:1px solid var(--ink); box-shadow:none; }
  html[data-theme="modern"] .toast.success .tdotc,
  html[data-theme="modern"] .toast.error .tdotc,
  html[data-theme="modern"] .toast.info .tdotc{ box-shadow:none; border-radius:0; }
  html[data-theme="modern"] .toast.success .tdotc{ background:var(--ink); }
  html[data-theme="modern"] .toast.info .tdotc{ background:transparent; border:1.5px solid var(--ink); }
  html[data-theme="modern"] .toast.error .tdotc{ background:var(--ink); transform:rotate(45deg); }


  @media (max-height:700px){
  html[data-theme="modern"] .hero{ padding:14px 0 14px; row-gap:7px; }
  html[data-theme="modern"] .hero > .radar-wrap{ width:100px; height:100px; }
  html[data-theme="modern"] .radar-wrap::before{ inset:16px; }
  html[data-theme="modern"] .radar-core svg{ width:30px; height:30px; }
  html[data-theme="modern"] .cta,
  html[data-theme="modern"] .cta.tg,
  html[data-theme="modern"] .cta.tg.on{ padding:12px 22px; }
  html[data-theme="modern"] .topbar{ height:46px; }
  html[data-theme="modern"] .footbar{ height:36px; }

  }

  @media (max-width:860px){
  html[data-theme="modern"] .hero{ column-gap:20px; }
  html[data-theme="modern"] .hero > .radar-wrap{ width:88px; height:88px; margin-right:0; }
  html[data-theme="modern"] .topbar{ gap:18px; padding:0 14px; }
  html[data-theme="modern"] .view{ padding:0 14px; }
  html[data-theme="modern"] .footbar{ padding:0 14px; }

  }



  /* ======================= ТЕМА «IOS26» · LIQUID GLASS ======================= */
  html[data-theme="ios26"]{
    --p0:#a98aa6; --p1:#5f86b6; --p2:#f1342b; --p3:#43bbb7; --p4:#ee4a8f; --p5:#8a3fb2; --p6:#14060b;
    --bg-0:#2a2433; --bg-1:rgba(255,255,255,.14); --bg-2:rgba(255,255,255,.22);
    --border:rgba(255,255,255,.38); --border-soft:rgba(255,255,255,.2);
    --text-0:#ffffff; --text-1:rgba(255,255,255,.84); --text-2:rgba(255,255,255,.6);
    --accent-mint:#e5e5ea; --accent-cyan:#e5e5ea; --accent-violet:#e5e5ea; --accent-amber:#d1d1d6; --accent-coral:#f2f2f7;
    --gray:#8e8e93; --on-accent:#1c1c1e;
    --bar-bg:transparent; --bar-bg-up:transparent;
    --overlay-bg:rgba(20,16,28,.42); --hover-soft:rgba(255,255,255,.14); --scroll-thumb-hover:rgba(255,255,255,.55);
    --glass:linear-gradient(180deg, rgba(255,255,255,.2), rgba(255,255,255,.06)), rgba(30,26,40,.3);
    --glass-edge:inset 0 1px 0 rgba(255,255,255,.6), inset 0 -1px 0 rgba(255,255,255,.12), inset 0 0 0 1px rgba(255,255,255,.1), 0 10px 34px -10px rgba(0,0,0,.35);
    --font-display:'Inter','SF Pro Display','Segoe UI Variable Display','Segoe UI',system-ui,sans-serif;
    --font-body:'Inter','SF Pro Text','Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;
    --radius-lg:26px; --radius-md:18px; --radius-sm:12px;
    --cta-text:#ffffff; --knob:#ffffff; --hi:#ffffff; --hi-soft:rgba(255,255,255,.7);
    --tshadow:0 1px 10px rgba(0,0,0,.22); --glass-blur:26px; --select-bg:#2a2433;
    --panel:linear-gradient(180deg, rgba(255,255,255,.16), rgba(255,255,255,.05)), rgba(34,28,46,.58);
    --field-bg:rgba(18,14,26,.32); --term-bg:rgba(18,14,26,.34); --term-err:rgba(0,0,0,.35);
  }
  html[data-theme="ios26"][data-scheme="classic"][data-ios="aurora"]{ --p0:#0f2a2e; --p1:#2a6cf0; --p2:#2fe3a0; --p3:#8a5cf0; --p4:#1fb5c9; --p5:#3a2a7a; --p6:#05121a; }
  html[data-theme="ios26"][data-scheme="classic"][data-ios="ocean"]{ --p0:#0a2a4a; --p1:#1e6fe0; --p2:#2fb6ff; --p3:#12c7c0; --p4:#5a8bff; --p5:#123a8a; --p6:#031428; }
  html[data-theme="ios26"][data-scheme="classic"][data-ios="sunset"]{ --p0:#6a2a52; --p1:#ff8a3d; --p2:#ff3d5a; --p3:#d6409f; --p4:#ffb347; --p5:#6a2fb0; --p6:#2a0a24; }
  html[data-theme="ios26"][data-scheme="classic"][data-ios="graphite"]{ --p0:#2b2b30; --p1:#5a5a62; --p2:#8e8e93; --p3:#4a4a52; --p4:#6e6e75; --p5:#1f1f24; --p6:#0d0d10; }

  html[data-theme="ios26"][data-scheme="black"]{
    --p0:#060607; --p1:#262833; --p2:#383844; --p3:#1c1d24; --p4:#2d2e38; --p5:#15151a; --p6:#000000;
    --bg-0:#060607; --overlay-bg:rgba(0,0,0,.62); --select-bg:#16161a;
  }
  html[data-theme="ios26"][data-scheme="white"]{
    --p0:#e8e8f0; --p1:#bcd3f4; --p2:#f6c1cb; --p3:#bfeee6; --p4:#f3d0ea; --p5:#d3cbf4; --p6:#f6f6fb;
    --bg-0:#e8e8f0; --bg-1:rgba(255,255,255,.6); --bg-2:rgba(255,255,255,.8);
    --border:rgba(255,255,255,.9); --border-soft:rgba(28,28,30,.12);
    --text-0:#1c1c1e; --text-1:rgba(28,28,30,.78); --text-2:rgba(28,28,30,.55);
    --accent-mint:#636366; --accent-cyan:#636366; --accent-violet:#636366; --accent-amber:#8e8e93; --accent-coral:#3a3a3c;
    --on-accent:#ffffff; --overlay-bg:rgba(60,60,90,.28); --hover-soft:rgba(28,28,30,.07); --scroll-thumb-hover:rgba(28,28,30,.45);
    --glass:linear-gradient(180deg, rgba(255,255,255,.78), rgba(255,255,255,.42)), rgba(255,255,255,.2);
    --glass-edge:inset 0 1px 0 rgba(255,255,255,1), inset 0 -1px 0 rgba(0,0,0,.06), inset 0 0 0 1px rgba(255,255,255,.5), 0 10px 30px -12px rgba(30,30,70,.28);
    --panel:linear-gradient(180deg, rgba(255,255,255,.86), rgba(255,255,255,.66)), rgba(255,255,255,.3);
    --field-bg:rgba(255,255,255,.65); --term-bg:rgba(255,255,255,.5); --term-err:rgba(28,28,30,.12);
    --hi:#1c1c1e; --hi-soft:rgba(28,28,30,.55); --tshadow:none; --select-bg:#ffffff;
  }
  /* фон: цветные размытые пятна в духе фото */
  html[data-theme="ios26"] body{ background:var(--p0); }
  html[data-theme="ios26"] .blob{ filter:blur(70px); opacity:.95; border-radius:50%; will-change:transform; }
  html[data-theme="ios26"] .b1{ width:70vw; height:72vh; top:-30%; left:-18%; background:var(--p1); }
  html[data-theme="ios26"] .b2{ width:56vw; height:78vh; top:6%; right:-18%; left:auto; background:var(--p2); }
  html[data-theme="ios26"] .b3{ width:96vw; height:56vh; bottom:-32%; top:auto; left:6%; background:var(--p3); }
  html[data-theme="ios26"] .b4{ display:block; width:46vw; height:36vh; top:40%; left:-12%; background:var(--p4); animation-duration:30s; animation-delay:-9s; }
  html[data-theme="ios26"] .b5{ display:block; width:52vw; height:30vh; bottom:0; left:-14%; background:var(--p5); animation-duration:34s; animation-delay:-17s; }
  html[data-theme="ios26"] .bg-blobs::after{ content:""; position:absolute; inset:0; background:radial-gradient(44% 48% at 100% 0%, var(--p6) 0%, transparent 72%); }
  html[data-theme="ios26"] .grain{ opacity:.03; }

  /* стекло */
  html[data-theme="ios26"] .card,
  html[data-theme="ios26"] .topbar,
  html[data-theme="ios26"] .footbar,
  html[data-theme="ios26"] .status-pill,
  html[data-theme="ios26"] .icon-btn,
  html[data-theme="ios26"] .pill-btn,
  html[data-theme="ios26"] .view-tabs,
  html[data-theme="ios26"] .terminal-body,
  html[data-theme="ios26"] .btn,
  html[data-theme="ios26"] .chip,
  html[data-theme="ios26"] .toast,
  html[data-theme="ios26"] .theme-card,
  html[data-theme="ios26"] .seg-btn,
  html[data-theme="ios26"] .tg-row,
  html[data-theme="ios26"] .tg-apply{
    background:var(--glass); border:1px solid var(--border); box-shadow:var(--glass-edge);
    -webkit-backdrop-filter:blur(var(--glass-blur,26px)) saturate(180%); backdrop-filter:blur(var(--glass-blur,26px)) saturate(180%);
    color:var(--text-0);
  }
  html[data-theme="ios26"] .topbar{ margin:10px 14px 0; padding:7px 12px; border-radius:24px; gap:12px; }
  html[data-theme="ios26"] .footbar{ margin:0 14px 10px; padding:6px 10px; border-radius:22px; }
  html[data-theme="ios26"] .view{ padding:10px 14px 8px; }
  html[data-theme="ios26"] .card{ border-radius:28px; }
  html[data-theme="ios26"] .hero{ padding:14px 22px; }
  html[data-theme="ios26"] .hero h1, html[data-theme="ios26"] .auto-status, html[data-theme="ios26"] .brand{ text-shadow:var(--tshadow); }
  html[data-theme="ios26"] .hero h1{ letter-spacing:-.02em; font-weight:700; }
  html[data-theme="ios26"] .brand svg{ color:var(--text-0); filter:drop-shadow(0 0 8px rgba(255,255,255,.5)); }

  html[data-theme="ios26"] .view-tabs{ border-radius:99px; padding:3px; box-shadow:var(--glass-edge); }
  html[data-theme="ios26"] .view-tabs .glider{
    background:linear-gradient(180deg, rgba(255,255,255,.5), rgba(255,255,255,.26));
    box-shadow:inset 0 1px 0 rgba(255,255,255,.8), 0 4px 14px -4px rgba(0,0,0,.35);
  }
  html[data-theme="ios26"] .view-tab{ color:var(--text-1); }
  html[data-theme="ios26"] .view-tab.active{ color:var(--text-0); text-shadow:var(--tshadow); }

  html[data-theme="ios26"] .status-pill, html[data-theme="ios26"] .status-pill.idle,
  html[data-theme="ios26"] .status-pill.testing, html[data-theme="ios26"] .status-pill.connected,
  html[data-theme="ios26"] .status-pill.local{ color:var(--text-0); border-color:var(--border); }
  html[data-theme="ios26"] .status-pill .dot{ background:transparent; border:1.5px solid var(--hi-soft); }
  html[data-theme="ios26"] .status-pill .dot::after{ background:transparent; border:1px solid var(--hi); opacity:0; animation:none; }
  html[data-theme="ios26"] .status-pill.testing .dot{ background:var(--hi); border-color:var(--text-0); }
  html[data-theme="ios26"] .status-pill.testing .dot::after{ opacity:.7; animation:ringPulse 1.4s ease-out infinite; }
  html[data-theme="ios26"] .status-pill.connected .dot, html[data-theme="ios26"] .status-pill.local .dot{ background:var(--hi); border-color:var(--text-0); box-shadow:0 0 10px rgba(255,255,255,.8); }
  html[data-theme="ios26"] .status-pill.connected .dot::after, html[data-theme="ios26"] .status-pill.local .dot::after, html[data-theme="ios26"] .status-pill.idle .dot::after{ background:transparent; opacity:0; }

  html[data-theme="ios26"] .icon-btn{ border-radius:50%; color:var(--text-0); }
  html[data-theme="ios26"] .icon-btn:hover{ background:linear-gradient(180deg, rgba(255,255,255,.34), rgba(255,255,255,.14)), rgba(30,26,40,.2); border-color:rgba(255,255,255,.6); }
  html[data-theme="ios26"] .pill-btn, html[data-theme="ios26"] .pill-btn.danger, html[data-theme="ios26"] .pill-btn.violet, html[data-theme="ios26"] .pill-btn.cyan{ border-radius:99px; color:var(--text-0); padding:7px 15px; }
  html[data-theme="ios26"] .pill-btn:hover, html[data-theme="ios26"] .pill-btn.danger:hover, html[data-theme="ios26"] .pill-btn.violet:hover, html[data-theme="ios26"] .pill-btn.cyan:hover{
    color:var(--text-0); border-color:rgba(255,255,255,.65); box-shadow:var(--glass-edge); filter:brightness(1.15);
  }

  /* главная кнопка — графитовое стекло (серый акцент) */
  html[data-theme="ios26"] .cta, html[data-theme="ios26"] .cta.tg, html[data-theme="ios26"] .cta.tg.on{
    background:linear-gradient(180deg, rgba(150,150,158,.78), rgba(84,84,92,.82));
    color:var(--cta-text); border:1px solid rgba(255,255,255,.5); border-radius:99px; padding:12px 28px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.65), inset 0 -1px 0 rgba(0,0,0,.18), 0 12px 28px -10px rgba(0,0,0,.45);
    -webkit-backdrop-filter:blur(18px) saturate(160%); backdrop-filter:blur(18px) saturate(160%);
    text-shadow:0 1px 3px rgba(0,0,0,.35);
  }
  html[data-theme="ios26"] .cta:hover:not(:disabled), html[data-theme="ios26"] .cta.tg:hover:not(:disabled){
    background:linear-gradient(180deg, rgba(172,172,180,.85), rgba(98,98,106,.88)); transform:translateY(-1px);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.75), 0 16px 34px -10px rgba(0,0,0,.5);
  }
  html[data-theme="ios26"] .cta.tg.on{ background:linear-gradient(180deg, rgba(255,255,255,.34), rgba(255,255,255,.14)), rgba(30,26,40,.3); }
  html[data-theme="ios26"] .cta .ripple{ background:rgba(255,255,255,.5); }
  html[data-theme="ios26"] .tg-apply{ border-radius:99px; color:var(--text-0); box-shadow:var(--glass-edge); }
  html[data-theme="ios26"] .tg-apply::before{ background:linear-gradient(120deg, transparent, rgba(255,255,255,.35), transparent); }
  html[data-theme="ios26"] .tg-apply:hover:not(:disabled){ box-shadow:var(--glass-edge); }
  html[data-theme="ios26"] .link-inline:hover{ background:rgba(255,255,255,.14); color:var(--text-0); }
  html[data-theme="ios26"] .tg-row{ border-radius:14px; }

  /* радар — стеклянная линза */
  html[data-theme="ios26"] .radar-wrap{ --state-color:var(--text-0); }
  html[data-theme="ios26"] .radar-wrap.state-idle{ --state-color:var(--hi-soft); }
  html[data-theme="ios26"] .radar-wrap.state-testing, html[data-theme="ios26"] .radar-wrap.state-connected, html[data-theme="ios26"] .radar-wrap.state-local{ --state-color:var(--text-0); }
  html[data-theme="ios26"] .radar-ring{
    border:1px solid var(--hi-soft); opacity:1;
    background:radial-gradient(circle at 30% 25%, rgba(255,255,255,.35), rgba(255,255,255,.06) 55%, rgba(255,255,255,.12));
    box-shadow:inset 0 1px 0 rgba(255,255,255,.7), inset 0 0 26px rgba(255,255,255,.18), 0 10px 34px -8px rgba(0,0,0,.4);
    -webkit-backdrop-filter:blur(8px); backdrop-filter:blur(8px);
  }
  html[data-theme="ios26"] .radar-wrap.state-idle .radar-ring{ border-style:dashed; }
  html[data-theme="ios26"] .radar-sweep{ background:conic-gradient(from 0deg, transparent 0deg, var(--hi) 14deg, transparent 56deg); }
  html[data-theme="ios26"] .radar-core svg{ filter:drop-shadow(0 2px 8px rgba(0,0,0,.35)); }
  html[data-theme="ios26"] .radar-wrap.state-connected .radar-core svg, html[data-theme="ios26"] .radar-wrap.state-local .radar-core svg{ fill:currentColor; }

  /* лог */
  html[data-theme="ios26"] .terminal.card{ padding:0; overflow:hidden; }
  html[data-theme="ios26"] .terminal-head{ border-bottom:1px solid var(--border-soft); }
  html[data-theme="ios26"] .tdot{ background:rgba(255,255,255,.55); opacity:1; }
  html[data-theme="ios26"] .terminal-body{ background:var(--term-bg); border:none; border-radius:0; box-shadow:none; -webkit-backdrop-filter:none; backdrop-filter:none; color:var(--text-1); }
  html[data-theme="ios26"] .log-line.ok{ color:var(--text-0); font-weight:600; }
  html[data-theme="ios26"] .log-line.err{ color:var(--text-0); font-weight:700; background:var(--term-err); box-shadow:-14px 0 0 var(--term-err), 14px 0 0 var(--term-err); }
  html[data-theme="ios26"] .log-line.warn{ color:var(--text-1); font-style:italic; }
  html[data-theme="ios26"] .cursor-blink{ background:var(--hi); }

  /* панели и окна */
  html[data-theme="ios26"] .drawer{
    background:var(--panel);
    -webkit-backdrop-filter:blur(calc(var(--glass-blur,26px) * 1.5)) saturate(190%); backdrop-filter:blur(calc(var(--glass-blur,26px) * 1.5)) saturate(190%);
    border-left:1px solid var(--border); border-radius:28px 0 0 28px;
    box-shadow:inset 1px 0 0 rgba(255,255,255,.35), -24px 0 60px -20px rgba(0,0,0,.45);
  }
  html[data-theme="ios26"] .modal{
    background:var(--panel);
    -webkit-backdrop-filter:blur(calc(var(--glass-blur,26px) * 1.5)) saturate(190%); backdrop-filter:blur(calc(var(--glass-blur,26px) * 1.5)) saturate(190%);
    border:1px solid var(--border); border-radius:28px; box-shadow:var(--glass-edge), 0 30px 80px -20px rgba(0,0,0,.55);
  }
  html[data-theme="ios26"] .drawer-head, html[data-theme="ios26"] .modal-head, html[data-theme="ios26"] .tabs{ border-bottom:1px solid var(--border-soft); }
  html[data-theme="ios26"] .tab{ color:var(--text-2); }
  html[data-theme="ios26"] .tab.active{ color:var(--text-0); }
  html[data-theme="ios26"] .tab-indicator{ background:var(--hi); box-shadow:0 0 12px rgba(255,255,255,.6); }
  html[data-theme="ios26"] .modal-body p.warn-box{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.3); color:var(--text-0); border-radius:14px; }
  html[data-theme="ios26"] .modal-body strong, html[data-theme="ios26"] .modal-body h4{ color:var(--text-0); }

  html[data-theme="ios26"] .btn, html[data-theme="ios26"] .btn.success, html[data-theme="ios26"] .btn.danger, html[data-theme="ios26"] .btn.info, html[data-theme="ios26"] .btn.violet{
    border-radius:14px; color:var(--text-0); border:1px solid var(--border); box-shadow:var(--glass-edge);
  }
  html[data-theme="ios26"] .btn:hover, html[data-theme="ios26"] .btn.success:hover, html[data-theme="ios26"] .btn.danger:hover, html[data-theme="ios26"] .btn.info:hover, html[data-theme="ios26"] .btn.violet:hover{
    color:var(--text-0); filter:brightness(1.18); box-shadow:var(--glass-edge); transform:translateY(-1px);
  }
  html[data-theme="ios26"] .select, html[data-theme="ios26"] .domain-form input, html[data-theme="ios26"] .ports-grid input{
    background:var(--field-bg); border:1px solid var(--border); color:var(--text-0); border-radius:13px;
  }
  html[data-theme="ios26"] .select:focus, html[data-theme="ios26"] .domain-form input:focus, html[data-theme="ios26"] .ports-grid input:focus{
    border-color:rgba(255,255,255,.75); box-shadow:0 0 0 3px rgba(255,255,255,.16);
  }
  html[data-theme="ios26"] .select option{ background:var(--select-bg); color:var(--text-0); }
  html[data-theme="ios26"] .domain-form button{ background:linear-gradient(180deg, rgba(150,150,158,.85), rgba(84,84,92,.9)); color:var(--cta-text); border:1px solid rgba(255,255,255,.4); border-radius:13px; }
  html[data-theme="ios26"] .chip{ border-radius:99px; }
  html[data-theme="ios26"] .chip button{ background:rgba(255,255,255,.2); color:var(--text-0); }
  html[data-theme="ios26"] .chip button:hover{ background:rgba(255,255,255,.45); color:#1c1c1e; }
  html[data-theme="ios26"] .chk-row input{ accent-color:#aeaeb2; }

  /* переключатель — серый «iOS» */
  html[data-theme="ios26"] .switch{ background:rgba(120,120,128,.4); border:1px solid rgba(255,255,255,.3); box-shadow:inset 0 1px 3px rgba(0,0,0,.25); }
  html[data-theme="ios26"] .switch::after{ background:var(--knob); box-shadow:0 2px 6px rgba(0,0,0,.35); }
  html[data-theme="ios26"] .switch-wrap.on .switch{ background:#aeaeb2; border-color:rgba(255,255,255,.7); box-shadow:inset 0 1px 3px rgba(0,0,0,.2); }
  html[data-theme="ios26"] .switch-wrap.on .switch::after{ background:var(--knob); box-shadow:0 2px 8px rgba(0,0,0,.4); }
  html[data-theme="ios26"] .switch-wrap.on .switch-text b{ color:var(--text-0); }

  html[data-theme="ios26"] .theme-card{ border-radius:18px; }
  html[data-theme="ios26"] .theme-card:hover{ transform:none; border-color:rgba(255,255,255,.6); }
  html[data-theme="ios26"] .theme-card.active{ border-color:var(--text-0); box-shadow:var(--glass-edge), 0 0 0 1px var(--hi); }
  html[data-theme="ios26"] .theme-card.active .theme-name{ color:var(--text-0); }
  html[data-theme="ios26"] .theme-prev{ border-radius:11px; }
  html[data-theme="ios26"] .seg-btn{ border-radius:12px; color:var(--text-0); }
  html[data-theme="ios26"] .seg-btn:hover{ border-color:rgba(255,255,255,.6); }
  html[data-theme="ios26"] .seg-btn.active{ background:linear-gradient(180deg, rgba(170,170,178,.9), rgba(100,100,108,.92)); color:var(--cta-text); border-color:rgba(255,255,255,.55); }
  html[data-theme="ios26"] .swatch.active .sw{ box-shadow:0 0 0 2px rgba(0,0,0,.25), 0 0 0 4px var(--hi); }

  html[data-theme="ios26"] .toast{ border-radius:18px; background:var(--panel); }
  html[data-theme="ios26"] .toast .tdotc, html[data-theme="ios26"] .toast.success .tdotc, html[data-theme="ios26"] .toast.error .tdotc, html[data-theme="ios26"] .toast.info .tdotc{ background:var(--hi); box-shadow:0 0 8px rgba(255,255,255,.7); }
  html[data-theme="ios26"] .toast.error .tdotc{ background:transparent; border:2px solid var(--hi); box-shadow:none; }
  html[data-theme="ios26"] ::-webkit-scrollbar-thumb{ background:rgba(255,255,255,.35); }
  html[data-theme="ios26"] ::selection{ background:rgba(255,255,255,.6); color:#1c1c1e; }
  html[data-theme="ios26"] .hint code{ color:var(--text-0); }

  @media (max-height:700px){
    html[data-theme="ios26"] .topbar{ margin-top:8px; padding:5px 10px; }
    html[data-theme="ios26"] .footbar{ margin-bottom:8px; padding:4px 8px; }
    html[data-theme="ios26"] .hero{ padding:10px 18px; }
  }
  @media (prefers-reduced-motion: reduce){
    html[data-theme="ios26"] .blob{ display:block; animation:none; }
  }

  /* ======================= СВОЯ ТЕМА + РЕДАКТОР ======================= */
  .theme-prev.p-custom{ background:conic-gradient(from 200deg, #ff5c72, #ffb648, #33e6a6, #4fd1ff, #8b6bff, #ff5c72); }
  .theme-prev.p-custom::after{ background:rgba(255,255,255,.75); }
  .overlay.see-through{ background:transparent; backdrop-filter:none; -webkit-backdrop-filter:none; }
  .editor{ margin:6px 0 14px; padding-top:12px; border-top:1px solid var(--border-soft); }
  .ed-block{ margin:0 0 12px; }
  .ed-sub{ display:block; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--text-2); margin:0 0 6px; }
  .ed-row{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:5px 0; font-size:13px; color:var(--text-0); cursor:pointer; }
  .ed-row > span{ flex:1; min-width:0; }
  .ed-hex{ font-family:var(--font-mono); font-size:11px; color:var(--text-2); }
  .ed-row input[type=color]{ -webkit-appearance:none; appearance:none; width:38px; height:24px; padding:0; border:1px solid var(--border); border-radius:7px; background:none; cursor:pointer; flex:none; }
  .ed-row input[type=color]::-webkit-color-swatch-wrapper{ padding:2px; }
  .ed-row input[type=color]::-webkit-color-swatch{ border:none; border-radius:5px; }
  .ed-slider{ display:grid; grid-template-columns:1fr auto; gap:2px 10px; margin:0 0 10px; font-size:13px; color:var(--text-0); }
  .ed-slider b{ font-weight:600; font-family:var(--font-mono); font-size:11.5px; color:var(--text-1); }
  .ed-slider input[type=range]{ grid-column:1 / -1; width:100%; accent-color:var(--accent-cyan); }
  .ed-json{ width:100%; min-height:70px; margin:6px 0; background:var(--bg-0); color:var(--text-0); border:1px solid var(--border); border-radius:10px; padding:8px; font-family:var(--font-mono); font-size:11px; resize:vertical; }
  html[data-custom="1"] .card, html[data-custom="1"] .modal, html[data-custom="1"] .theme-card, html[data-custom="1"] .toast{ border-radius:var(--c-radius); }
  html[data-custom="1"] .drawer{ border-radius:var(--c-radius) 0 0 var(--c-radius); }
  html[data-custom="1"] .btn, html[data-custom="1"] .cta, html[data-custom="1"] .cta.tg, html[data-custom="1"] .cta.tg.on,
  html[data-custom="1"] .pill-btn, html[data-custom="1"] .tg-apply, html[data-custom="1"] .seg-btn, html[data-custom="1"] .select,
  html[data-custom="1"] .domain-form input, html[data-custom="1"] .ports-grid input, html[data-custom="1"] .chip,
  html[data-custom="1"] .icon-btn, html[data-custom="1"] .status-pill, html[data-custom="1"] .view-tabs,
  html[data-custom="1"] .topbar, html[data-custom="1"] .footbar{ border-radius:calc(var(--c-radius) * .7); }
  html[data-custom="1"] .terminal-body{ background:var(--term-bg); }
  #bestSearchToggle{ align-self:center; justify-self:start; margin:4px 0 0; padding:5px 0; gap:9px; }
  #bestSearchToggle .switch-text{ display:flex; gap:8px; align-items:baseline; }
  .view[data-view="main"]{ overflow-y:auto; }
  .topbar .icon-btn{ flex-shrink:0; }
  .topbar{ flex-wrap:wrap; }
  #bestSearchToggle .switch-text{ flex-direction:row; flex-wrap:wrap; }

  .theme-grid{ grid-template-columns:repeat(2,minmax(0,1fr)); }
  .theme-card{ flex-direction:column; gap:6px; padding:10px; align-items:flex-start; }
  .theme-card .theme-prev{ width:100%; height:28px; flex-basis:28px; }
  .theme-card .theme-desc{ display:none; }
  .theme-section{ border-top:1px solid var(--border); padding:12px 0; }
  .theme-section summary{ cursor:pointer; font-weight:600; font-size:13px; color:var(--text-1); }
  .theme-section[open] summary{ margin-bottom:14px; }
  .compact-colors{ margin-top:12px; }
  .toast{ pointer-events:auto; position:relative; align-items:flex-start; }
  .toast-content{ flex:1; min-width:0; overflow-wrap:anywhere; }
  .toast-count{ font-weight:700; margin-left:7px; color:var(--accent-cyan); white-space:nowrap; }
  .toast-actions{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  .toast-actions button{ padding:7px 10px; font-size:12px; cursor:pointer; }
  .toast.bump{ animation:toastShake .28s ease both; }
  .toast.leaving{ animation:toastOut .2s ease forwards; }
  .toasts{ max-height:calc(100vh - 160px); overflow:auto; }
  @keyframes toastShake{ 0%,100%{transform:translateX(0)} 25%{transform:translateX(-3px)} 75%{transform:translateX(3px)} }
  .smooth-disclosure > button{ display:flex; gap:8px; align-items:center; color:var(--text-2); background:none; border:0; padding:6px 0; font:inherit; cursor:pointer; }
  .smooth-disclosure > button::before{ content:'›'; display:inline-block; transition:transform .25s ease; }
  .smooth-disclosure.open > button::before{ transform:rotate(90deg); }
  .disclosure-body{ display:grid; grid-template-rows:0fr; opacity:0; transition:grid-template-rows .3s ease, opacity .25s ease; }
  .smooth-disclosure.open .disclosure-body{ grid-template-rows:1fr; opacity:1; }
  .disclosure-inner{ overflow:hidden; min-height:0; }
  .social-links{ display:flex; gap:7px; margin-left:auto; }
  .social-link{ width:32px; height:32px; border-radius:10px; background:var(--bg-1); color:var(--text-1); border:1px solid var(--border); display:grid; place-items:center; cursor:pointer; transition:color .2s, background .2s; }
  .social-link svg{ width:18px; height:18px; }
  .social-link:hover{ color:var(--accent-cyan); background:var(--bg-2); }
  .footbar .last{ margin-left:0; }

</style>
</head>
<body>

  <div class="bg-blobs" aria-hidden="true"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div><div class="blob b4"></div><div class="blob b5"></div></div>
  <div class="grain" aria-hidden="true"></div>

  <header class="topbar">
    <div class="brand">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2l8 3.5v6c0 5-3.4 8.7-8 10.5-4.6-1.8-8-5.5-8-10.5v-6L12 2z"/><path d="M9 12l2 2 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>NERKN</span>
    </div>
    <div class="view-tabs" id="viewTabs">
      <span class="glider"></span>
      <button class="view-tab active" data-view="main">Обход блокировок</button>
      <button class="view-tab" data-view="tg">Telegram прокси</button>
    </div>

    <div class="status-pill idle" id="statusPill"><span class="dot"></span><span class="label">В ожидании</span></div>
    <button class="icon-btn palette" id="btnTheme" title="Сменить тему оформления">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3a9 9 0 100 18c.8 0 1.5-.7 1.5-1.5 0-.4-.2-.8-.4-1-.3-.3-.4-.6-.4-1 0-.8.7-1.5 1.5-1.5H16a5 5 0 005-5c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="9.8" cy="7.8" r="1.2" fill="currentColor" stroke="none"/><circle cx="14.4" cy="7.4" r="1.2" fill="currentColor" stroke="none"/><circle cx="17.3" cy="11" r="1.2" fill="currentColor" stroke="none"/></svg>
    </button>
    <button class="icon-btn gear" id="btnSettings" title="Настройки">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
    </button>
  </header>

  <main class="views" id="views">
  <section class="view" data-view="main" data-pos="center">
    <section class="hero card">
      <p class="eyebrow">01 — Умная защита соединения</p>
      <h1>Обход блокировок в один клик</h1>
      <details class="more"><summary>Подробнее</summary><p class="sub">Автоматически подберём рабочий метод обхода для Discord, YouTube и других сервисов и включим его в фоне — служба останется активной даже после перезагрузки.</p></details>

      <div class="radar-wrap state-idle" id="radar">
        <div class="radar-ring"></div>
        <div class="radar-sweep"></div>
        <div class="radar-core">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 2l8 3.5v6c0 5-3.4 8.7-8 10.5-4.6-1.8-8-5.5-8-10.5v-6L12 2z"/></svg>
        </div>
      </div>

      <button class="cta" id="btnMagic">
        <span class="cta-label">Найти и включить обход</span>
        <span class="spinner" hidden></span>
      </button>
        <div class="switch-wrap" id="bestSearchToggle" role="switch" aria-checked="false" tabindex="0" title="Проверять все стратегии и выбирать самую лучшую, а не первую рабочую">
      <span class="switch"></span>
      <span class="switch-text"><b>Лучший поиск</b><small>дольше, но точнее</small></span>
    </div>
      <p class="auto-status" id="autoStatus">Статус: в ожидании действий</p>

      <button class="link-inline" id="btnDomains">
        Не открывается сайт? Добавить домен
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </section>

    <section class="terminal card">
      <div class="terminal-head">
        <span class="tdot r"></span><span class="tdot y"></span><span class="tdot g"></span>
        <span class="term-title">bypass.log</span>
      </div>
      <div class="terminal-body" id="log">
        <div class="log-line log-empty">Здесь появится ход подбора метода обхода...</div>
      </div>
    </section>
  </section>

  <section class="view scroll" data-view="tg" data-pos="right">
    <section class="hero card">
      <p class="eyebrow">02 — Telegram MTProto</p>
      <h1>Свой Telegram-прокси прямо на этом компьютере</h1>
      <details class="more"><summary>Подробнее</summary><p class="sub">Локальный MTProto-прокси поднимает мост до серверов Telegram через WebSocket и Cloudflare. Включите его и примените ссылку в Telegram — мессенджер снова заработает без VPN.</p></details>

      <div class="radar-wrap state-idle" id="tgRadar">
        <div class="radar-ring"></div>
        <div class="radar-sweep"></div>
        <div class="radar-core">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21.5 4.3L2.9 11.4c-1.1.4-1.1 1 .1 1.3l4.7 1.5 1.8 5.5c.2.6.1.9.8.9.5 0 .7-.2 1-.5l2.4-2.3 4.9 3.6c.9.5 1.5.2 1.7-.8l3.2-15c.3-1.2-.5-1.8-1.3-1.5z" stroke-linejoin="round"/></svg>
        </div>
      </div>

      <button class="cta tg" id="btnTgPower">
        <span class="cta-label">Включить Telegram-прокси</span>
        <span class="spinner" hidden></span>
      </button>
      <p class="auto-status" id="tgStatusText">Прокси выключен</p>

      <button class="tg-apply" id="btnTgApply" disabled>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M21.5 4.3L2.9 11.4c-1.1.4-1.1 1 .1 1.3l4.7 1.5 1.8 5.5c.2.6.1.9.8.9.5 0 .7-.2 1-.5l2.4-2.3 4.9 3.6c.9.5 1.5.2 1.7-.8l3.2-15c.3-1.2-.5-1.8-1.3-1.5z" stroke-linejoin="round"/></svg>
        Применить в телеграм
      </button>

      <div class="more tg-more smooth-disclosure" id="tgDetails"><button id="tgDetailsToggle" aria-expanded="false" aria-controls="tgDetailsBody">Данные подключения</button><div class="disclosure-body" id="tgDetailsBody" inert><div class="disclosure-inner">
      <div class="tg-info">
        <div class="tg-row"><span class="k">Адрес</span><span class="v" id="tgHost">127.0.0.1</span></div>
        <div class="tg-row"><span class="k">Порт</span><span class="v" id="tgPort">1443</span></div>
        <div class="tg-row"><span class="k">Ссылка</span><span class="v" id="tgLink">—</span></div>
      </div>
      <p class="tg-note">После нажатия «Применить в телеграм» откроется Telegram и сам предложит подключить внешний прокси — останется нажать «Подключить». Пока программа полностью закрыта, прокси не работает.</p>
      </div></div></div>
    </section>
  </section>
  </main>

  <footer class="footbar">
    <button class="pill-btn danger" id="btnRemoveAll">Удалить все обходы</button>
    <button class="pill-btn violet" id="btnCredits">Авторство</button>
    <div class="social-links" aria-label="Ссылки проекта">
      <button class="social-link" id="socialTelegram" aria-label="Telegram проекта" title="Telegram проекта"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21.5 4.3 2.9 11.4c-1.1.4-1.1 1 .1 1.3l4.7 1.5 1.8 5.5c.2.6.1.9.8.9.5 0 .7-.2 1-.5l2.4-2.3 4.9 3.6c.9.5 1.5.2 1.7-.8l3.2-15c.3-1.2-.5-1.8-1.3-1.5ZM9.2 14l9-6.1-7.2 7-.5 3.2Z"/></svg></button>
      <button class="social-link" id="socialGithub" aria-label="GitHub проекта" title="GitHub проекта"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.86c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.64-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02A9.6 9.6 0 0 1 12 6.83c.85 0 1.71.12 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.58 4.94.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2Z"/></svg></button>
    </div>
    <button class="pill-btn cyan last" id="btnHelp">Помощь</button>
  </footer>

  <!-- overlay -->
  <div class="overlay" id="overlay"></div>

  <!-- domains drawer -->
  <aside class="drawer" id="drawerDomains">
    <div class="drawer-head"><h3>Мои домены</h3><button class="icon-btn small" data-close>✕</button></div>
    <div class="drawer-body">
      <p class="hint">Добавьте сайт, который у вас не открывается — он будет включён в проверку и обход при следующем подборе.</p>
      <form class="domain-form" id="domainForm">
        <input type="text" id="domainInput" placeholder="instagram.com" autocomplete="off" spellcheck="false" />
        <button type="submit">+</button>
      </form>
      <div class="chip-list" id="chipList"></div>
    </div>
  </aside>

  <!-- settings drawer -->
  <aside class="drawer wide" id="drawerSettings">
    <div class="drawer-head"><h3>Настройки</h3><button class="icon-btn small" data-close>✕</button></div>
    <div class="tabs" id="settingsTabs">
      <div class="tab active" data-tab="manage">Управление</div>
      <div class="tab" data-tab="service">Служба</div>
      <div class="tab" data-tab="look">Оформление</div>
      <div class="tab-indicator"></div>
    </div>
    <div class="drawer-body">
      <div class="tab-panel active" data-panel="manage">

        <span class="field-label">Ручной выбор</span>
        <select class="select" id="strategySelect"></select>
        <p class="hint">Выберите стратегию и нажмите «Принудить», чтобы запустить её без подбора. «Остановить» завершает ручной запуск. Для работы после выхода установите службу на соседней вкладке.</p>
        <div class="btn-row">
          <button class="btn success" id="btnStartLocal">Принудить</button>
          <button class="btn danger" id="btnStopLocal">Остановить</button>
        </div>
        <hr class="divider" />
        <span class="field-label">Автозапуск</span>
        <label class="chk-row"><input type="checkbox" id="chkAutoApp" />
          <span>Приложение — запускать вместе с Windows<small>Откроется свёрнутым в трей, без окна UAC.</small></span></label>
        <label class="chk-row"><input type="checkbox" id="chkAutoService" />
          <span>Служба обхода — стартовать вместе с Windows и при запуске приложения<small>Если служба уже установлена и остановлена, она будет запущена автоматически.</small></span></label>
        <label class="chk-row"><input type="checkbox" id="chkAutoProxy" />
          <span>Telegram-прокси — включать при запуске приложения<small>Ждёт появления сети и сам повторяет попытку, если не получилось с первого раза.</small></span></label>
      </div>
      <div class="tab-panel" data-panel="service">
        <p class="hint">Установите системную службу, чтобы обход работал всегда в фоне и запускался вместе с Windows. Стратегия берётся с вкладки «Управление».</p>
        <div class="btn-row">
          <button class="btn info" id="btnInstallService">Установить службу</button>
          <button class="btn danger" id="btnRemoveAll2">Удалить всё</button>
        </div>
        <hr class="divider" />
        <span class="field-label">Game Filter — фильтр игровых портов</span>
        <div class="seg-row" id="gameFilterSeg">
          <button class="seg-btn active" data-mode="disabled">Выкл</button>
          <button class="seg-btn" data-mode="all">TCP+UDP</button>
          <button class="seg-btn" data-mode="tcp">TCP</button>
          <button class="seg-btn" data-mode="udp">UDP</button>
        </div>
        <p class="hint">Расширяет обход на игровые порты — полезно, если не открываются игры. Требует перезапуска обхода.</p>
        <span class="field-label">Порты Game Filter</span>
        <div class="ports-grid">
          <label for="gfTcpPorts">TCP</label><input type="text" id="gfTcpPorts" placeholder="1024-65535" autocomplete="off" spellcheck="false" />
          <label for="gfUdpPorts">UDP</label><input type="text" id="gfUdpPorts" placeholder="1024-65535" autocomplete="off" spellcheck="false" />
        </div>
        <div class="btn-row">
          <button class="btn info" id="btnSavePorts">Сохранить порты</button>
          <button class="btn violet" id="btnResetPorts">Сбросить</button>
        </div>
        <p class="hint">Пример для исключения RTMP: <code>1024-1934,1936-65535</code>. Пустое поле = 1024-65535.</p>
        <hr class="divider" />
        <span class="field-label">IPSet — списки блокировок РФ</span>
        <div class="btn-row">
          <button class="btn violet" id="btnUpdateIpset">Обновить IPSet из сети</button>
          <button class="btn info" id="btnCycleIpset">Режим: <span id="ipsetStatusLabel">—</span></button>
        </div>
        <p class="hint" id="ipsetHint">«loaded» — обход применяется только к адресам из списка РФ, «none» — список отключён (заглушка), «any» — обход применяется ко всем адресам без фильтра. Нажатие переключает режим по кругу.</p>
      </div>
      <div class="tab-panel" data-panel="look">
        <label class="field-label" for="uiScale">Масштаб окна (DPI)</label>
        <select class="select" id="uiScale"><option>80</option><option>90</option><option selected>100</option><option>110</option><option>125</option><option>150</option></select>
        <p class="hint">Проценты относительно масштаба Windows. Применяется сразу.</p>
        <span class="field-label">Тема оформления</span>
        <div class="theme-grid" id="themeGrid">
          <div class="theme-card" data-theme="standard"><div class="theme-prev p-standard"></div><div class="theme-meta"><div class="theme-name">Стандарт</div><div class="theme-desc">Тёмный фон и яркие акценты</div></div></div>
          <div class="theme-card" data-theme="modern"><div class="theme-prev p-modern"></div><div class="theme-meta"><div class="theme-name">Модерн 010101</div><div class="theme-desc">Минимализм в стиле сайта</div></div></div>
          <div class="theme-card" data-theme="ios26"><div class="theme-prev p-ios26"></div><div class="theme-meta"><div class="theme-name">IOS26</div><div class="theme-desc">Liquid glass, серый акцент</div></div></div>
          <div class="theme-card" data-theme="custom"><div class="theme-prev p-custom"></div><div class="theme-meta"><div class="theme-name">Своя тема</div><div class="theme-desc">Редактор: красьте любые элементы</div></div></div>
        </div>
        <div class="variant-row" id="schemeBox">
          <span class="field-label">Цветовая схема</span>
          <div class="seg-row" id="schemeRow">
            <button class="seg-btn" data-scheme="classic">Классика</button>
            <button class="seg-btn" data-scheme="black">Чёрная</button>
            <button class="seg-btn" data-scheme="white">Белая</button>
          </div>
        </div>
        <div class="variant-row" id="variantIos" hidden>
          <span class="field-label">Фон IOS26 (схема «Классика»)</span>
          <div class="swatches" id="iosRow">
            <button class="swatch" data-ios="photo" title="Как на фото"><span class="sw sw-photo"></span><small>Фото</small></button>
            <button class="swatch" data-ios="aurora" title="Аврора"><span class="sw sw-aurora"></span><small>Аврора</small></button>
            <button class="swatch" data-ios="ocean" title="Океан"><span class="sw sw-ocean"></span><small>Океан</small></button>
            <button class="swatch" data-ios="sunset" title="Закат"><span class="sw sw-sunset"></span><small>Закат</small></button>
            <button class="swatch" data-ios="graphite" title="Графит"><span class="sw sw-graphite"></span><small>Графит</small></button>
          </div>
        </div>
        <div class="editor" id="themeEditor" hidden>
          <label class="field-label" for="themePreset">Готовый набор</label>
          <select class="select" id="themePreset"><option value="" selected disabled>Выбрать набор…</option><option value="ocean">Океан</option><option value="plum">Слива</option><option value="paper">Бумага</option><option value="ember">Уголь и янтарь</option></select>
          <button id="applyPreset" hidden>Применить</button>
          <div class="ed-block compact-colors">            <label class="ed-row"><span>Фон окна</span><code class="ed-hex" data-hex="bg"></code><input type="color" data-k="bg" /></label>
            <label class="ed-row"><span>Текст</span><code class="ed-hex" data-hex="text"></code><input type="color" data-k="text" /></label>
            <label class="ed-row"><span>Акцент 1: кнопки, «подключено»</span><code class="ed-hex" data-hex="accent"></code><input type="color" data-k="accent" /></label>
          </div>
          <details class="theme-section"><summary>Все цвета и форма</summary>
          <div class="ed-block"><span class="ed-sub">Основа</span>
            <div class="seg-row" id="edBase">
              <button class="seg-btn" data-base="standard">Стандарт</button>
              <button class="seg-btn" data-base="modern">Модерн</button>
              <button class="seg-btn" data-base="ios26">IOS26</button>
            </div>
          </div>
          <div class="ed-block">
            <div class="seg-row" id="edScheme">
              <button class="seg-btn" data-scheme="classic">Классика</button>
              <button class="seg-btn" data-scheme="black">Чёрная</button>
              <button class="seg-btn" data-scheme="white">Белая</button>
            </div>
          </div>
          <div class="ed-block"><span class="ed-sub">Фон и панели</span>
            <label class="ed-row"><span>Панели и карточки</span><code class="ed-hex" data-hex="panel"></code><input type="color" data-k="panel" /></label>
            <label class="ed-row"><span>Фон лога</span><code class="ed-hex" data-hex="term"></code><input type="color" data-k="term" /></label>
          </div>
          <div class="ed-block"><span class="ed-sub">Текст и рамки</span>
            <label class="ed-row"><span>Рамки</span><code class="ed-hex" data-hex="border"></code><input type="color" data-k="border" /></label>
          </div>
          <div class="ed-block"><span class="ed-sub">Акценты</span>
            <label class="ed-row"><span>Акцент 2: вкладки, ссылки</span><code class="ed-hex" data-hex="accent2"></code><input type="color" data-k="accent2" /></label>
            <label class="ed-row"><span>Акцент 3: подсветка фона</span><code class="ed-hex" data-hex="accent3"></code><input type="color" data-k="accent3" /></label>
          </div>
          <div class="ed-block"><span class="ed-sub">Статусы</span>
            <label class="ed-row"><span>Ожидание</span><code class="ed-hex" data-hex="idle"></code><input type="color" data-k="idle" /></label>
            <label class="ed-row"><span>Идёт подбор</span><code class="ed-hex" data-hex="testing"></code><input type="color" data-k="testing" /></label>
          </div>
          <div class="ed-block"><span class="ed-sub">Форма</span>
            <label class="ed-slider"><span>Скругление углов</span><b data-val="radius"></b><input type="range" min="0" max="40" step="1" data-sl="radius" /></label>
            <label class="ed-slider"><span>Прозрачность панелей</span><b data-val="panelA"></b><input type="range" min="0" max="100" step="1" data-sl="panelA" /></label>
            <label class="ed-slider"><span>Яркость рамок</span><b data-val="borderA"></b><input type="range" min="0" max="100" step="1" data-sl="borderA" /></label>
            <label class="ed-slider"><span>Размытие стекла</span><b data-val="blur"></b><input type="range" min="0" max="60" step="1" data-sl="blur" /></label>
          </div>
          <div class="btn-row"><button class="btn info" id="edReset">Сбросить цвета</button><button class="btn violet" id="newTheme">Новая тема</button></div>
          </details>
          <details class="theme-section" id="savedThemes"><summary>Мои темы · 5 слотов</summary>
          <select class="select" id="themeSlot"><option value="0">Слот 1</option><option value="1">Слот 2</option><option value="2">Слот 3</option><option value="3">Слот 4</option><option value="4">Слот 5</option></select>
          <div class="btn-row"><button class="btn info" id="saveSlot">Сохранить</button><button class="btn violet" id="loadSlot">Загрузить</button></div>
          <p class="hint">Сохранение заменяет тему в выбранном слоте.</p>
          </details>
          <details class="theme-section" id="shareTheme"><summary>Поделиться или импортировать</summary>
          <div class="btn-row"><button class="btn info" id="edCopy">Копировать код</button><button class="btn violet" id="exportTheme">Сохранить файл</button><button class="btn violet" id="importTheme">Открыть файл</button></div>
          <input type="file" id="themeFile" accept=".rknth,.json" hidden />
          <textarea class="ed-json" id="edJson" spellcheck="false" placeholder="Или вставьте код темы сюда"></textarea>
          <button class="btn info" id="edImport">Применить код</button>
          </details>
        </div>
        <p class="hint">Тема применяется мгновенно и запоминается — при следующем запуске программа откроется в том же оформлении. Быстро переключить можно кнопкой 🎨 в шапке.</p>
        <hr class="divider" />
        <span class="field-label">Диагностика</span>
        <div class="btn-row">
          <button class="btn info" id="btnOpenDebugLog">Лог подбора</button>
          <button class="btn violet" id="btnOpenTgLog">Лог Telegram-прокси</button>
        </div>
      </div>
    </div>
  </aside>

  <!-- help modal -->
  <div class="modal" id="modalHelp">
    <div class="modal-head"><h3>Помощь по использованию</h3><button class="icon-btn small" data-close>✕</button></div>
    <div class="modal-body" id="helpBody"></div>
  </div>

  <!-- credits modal -->
  <div class="modal" id="modalCredits">
    <div class="modal-head"><h3>Авторство и благодарности</h3><button class="icon-btn small" data-close>✕</button></div>
    <div class="modal-body" id="creditsBody"></div>
  </div>

  <div class="toasts" id="toasts"></div>

<script>
(function(){
  'use strict';

  const $ = id => document.getElementById(id);
  const radar = $('radar');
  const statusPill = $('statusPill');
  const statusLabel = statusPill.querySelector('.label');
  const autoStatus = $('autoStatus');
  const btnMagic = $('btnMagic');
  const ctaLabel = btnMagic.querySelector('.cta-label');
  const spinner = btnMagic.querySelector('.spinner');
  const logBox = $('log');
  const overlay = $('overlay');

  const state = { testing:false };

  const STATE_META = {
    idle:      { cls:'idle',      pill:'idle',      short:'В ожидании',  text:'Статус: в ожидании действий', cta:'Найти и включить обход' },
    testing:   { cls:'testing',   pill:'testing',   short:'Проверка...', text:'Идёт проверка и подбор метода...', cta:'Идёт проверка...' },
    connected: { cls:'connected', pill:'connected', short:'Включено',    text:'Включено, интернет свободен и открыт', cta:'Всё готово! Хотите перепроверить?' },
    local:     { cls:'local',     pill:'local',     short:'Включено',    text:'Включено, интернет свободен и открыт', cta:'Всё готово! Хотите перепроверить?' },
  };

  function setConnectionState(key){
    const meta = STATE_META[key] || STATE_META.idle;
    radar.className = 'radar-wrap state-' + meta.cls;
    statusPill.className = 'status-pill ' + meta.pill;
    statusLabel.textContent = meta.short;
    autoStatus.textContent = meta.text;
    if(!state.testing){
      ctaLabel.textContent = meta.cta;
      btnMagic.disabled = false;
      spinner.hidden = true;
    }
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function logLine(text){
    if(logBox.querySelector('.log-empty')) logBox.innerHTML = '';
    const line = document.createElement('div');
    let cls = 'log-line';
    if(text.includes('✅') || text.includes('🎉')) cls += ' ok';
    else if(text.includes('❌')) cls += ' err';
    else if(text.includes('⚠️')) cls += ' warn';
    line.className = cls;
    line.textContent = text;
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
  }

  function clearLog(){
    logBox.innerHTML = '';
  }

  const activeToasts = new Map();
  function toast(message, kind, options={}){
    kind = kind || 'info';
    const key = options.key || kind + ':' + message;
    let entry = activeToasts.get(key);
    const arm = () => {
      clearTimeout(entry.timer);
      if(!options.persistent) entry.timer = setTimeout(entry.close, options.duration || 4500);
    };
    if(entry){
      entry.count++;
      entry.badge.textContent = 'x' + entry.count;
      entry.el.classList.remove('bump'); void entry.el.offsetWidth; entry.el.classList.add('bump');
      arm(); return entry;
    }
    // Keep at most three transient notices; action requests stay until answered.
    const regular = [...activeToasts.values()].filter(e => !e.persistent);
    if(!options.persistent && regular.length >= 3) regular[0].close();
    const t = document.createElement('div'); t.className = 'toast ' + kind;
    t.setAttribute('role', options.persistent ? 'alertdialog' : 'status');
    t.setAttribute('aria-label', message);
    const dot=document.createElement('span'); dot.className='tdotc';
    const body=document.createElement('div'); body.className='toast-content';
    const label=document.createElement('span'); label.textContent=message;
    const badge=document.createElement('span'); badge.className='toast-count';
    body.append(label,badge); t.append(dot,body);
    entry={el:t,badge,count:1,persistent:!!options.persistent,timer:null,
      close:() => { clearTimeout(entry.timer); if(activeToasts.get(key)===entry) activeToasts.delete(key); t.classList.add('leaving'); setTimeout(()=>t.remove(),200); }};
    if(options.actions){
      const row=document.createElement('div'); row.className='toast-actions';
      for(const action of options.actions){
        const button=document.createElement('button'); button.className='btn'; button.textContent=action.label;
        button.addEventListener('click',async()=>{
          row.querySelectorAll('button').forEach(b=>b.disabled=true);
          try { await action.run(); } finally { entry.close(); }
        }); row.appendChild(button);
      } body.appendChild(row);
    }
    activeToasts.set(key,entry); $('toasts').appendChild(t); arm(); return entry;
  }

  window.zapretPush = {
    log: logLine,
    clearLog: clearLog,
    toast: toast,
    status: function(payload){
      if(payload.isTesting){ setConnectionState('testing'); return; }
      if(payload.serviceStatus === 'running'){ setConnectionState('connected'); return; }
      if(payload.hasLocalProcess){ setConnectionState('local'); return; }
      setConnectionState('idle');
    },
    testFinished: function(){
      state.testing = false;
      btnMagic.disabled = false;
      spinner.hidden = true;
    },
    tgStatus: function(payload){ renderTgStatus(payload); }
  };

  const hasBridge = () => !!(window.pywebview && window.pywebview.api);

  const mockDomains = [
    { domain:'youtube.com', editable:false },
    { domain:'discord.com', editable:false },
    { domain:'instagram.com', editable:true }
  ];
  const mockStrategies = ['general (ALT2).bat','general (ALT3).bat','general (ALT4).bat','discord.bat'];
  let mockConnected = false;
  let mockTgOn = false;
  let mockGameFilter = 'disabled';
  let mockIpset = 'loaded';
  let mockPorts = { tcp:'1024-65535', udp:'1024-65535' };
  let mockAuto = { app:false, service:true, proxy:false };
  const mockTg = () => ({ available:true, running:mockTgOn, restarting:false, restartCount:0, host:'127.0.0.1', port:1443,
    secret:'00112233445566778899aabbccddeeff',
    link:'tg://proxy?server=127.0.0.1&port=1443&secret=dd00112233445566778899aabbccddeeff', error:'' });

  const mock = {
    get_init_data: async () => ({ strategies:mockStrategies, lastStrategy:mockStrategies[0], domains:mockDomains, serviceStatus:mockConnected?'running':'stopped', hasLocalProcess:false, theme:'standard', schemes:{}, custom:null, iosPalette:'photo', bestSearch:false, tg:mockTg(), gameFilterMode:mockGameFilter, gameFilterPorts:mockPorts, ipsetStatus:mockIpset, autostart:mockAuto }),
    set_ui_scale: async (scale) => ({ok:true,scale}),
    set_theme_slot: async (slot,data) => { themeSlots[slot]=data; return {ok:true, slots:themeSlots}; },
    export_theme: async () => { toast('Экспорт файла доступен в приложении', 'info'); return {ok:false}; },
    set_theme: async () => ({ok:true}),
    set_variant: async () => ({ok:true}),
    set_scheme: async () => ({ok:true}),
    set_custom_theme: async () => ({ok:true}),
    set_best_search: async () => ({ok:true}),
    open_debug_log: async () => ({ok:true}),
    open_tg_log: async () => ({ok:true}),
    tg_status: async () => mockTg(),
    tg_start: async () => { mockTgOn = true; return {ok:true, status:mockTg()}; },
    tg_stop: async () => { mockTgOn = false; return {ok:true, status:mockTg()}; },
    tg_open_telegram: async () => ({ok:true}),
    set_game_filter: async (m) => { mockGameFilter = m; return {ok:true, mode:m}; },
    set_game_filter_ports: async (t,u) => { mockPorts = { tcp:t||'1024-65535', udp:u||'1024-65535' }; return {ok:true, error:'', ports:mockPorts}; },
    get_autostart: async () => mockAuto,
    set_autostart: async (k,v) => { mockAuto[k] = !!v; return {ok:true, error:'', autostart:mockAuto}; },
    get_ipset_status: async () => mockIpset,
    cycle_ipset: async () => { mockIpset = mockIpset==='loaded'?'none':(mockIpset==='none'?'any':'loaded'); return {ok:true, status:mockIpset, error:''}; },
    get_status: async () => ({ serviceStatus:mockConnected?'running':'stopped', hasLocalProcess:false, isTesting:state.testing }),
    get_domains: async () => mockDomains,
    add_domain: async (d) => { if(!mockDomains.find(x=>x.domain===d)) mockDomains.push({domain:d, editable:true}); return {ok:true}; },
    remove_domain: async (d) => { const i = mockDomains.findIndex(x=>x.domain===d); if(i>-1) mockDomains.splice(i,1); return {ok:true}; },
    remove_all_bypasses: async () => { mockConnected = false; return {ok:true}; },
    start_local: async () => ({ok:true}),
    stop_local: async () => ({ok:true}),
    install_service_manual: async () => { mockConnected = true; return {ok:true}; },
    update_ipset: async () => ({ok:true}),
    get_help_text: async () => MOCK_HELP_HTML,
    get_credits_text: async () => MOCK_CREDITS_HTML,
    start_auto_test: async () => {
      state.testing = true;
      const lines = [
        'Начинаем автоматический подбор метода обхода блокировки...',
        '1. Остановка текущих процессов и служб NERKN...',
        '\n[1/4] Тестируем метод: general (ALT2).bat ...',
        '  Проверка соединения с иностранными сайтами (cloudflare)...',
        '  Проверка соединения с Discord...',
        '  Проверка соединения с YouTube...',
        '⚠️ Метод работает частично.',
        '\n[2/4] Тестируем метод: general (ALT3).bat ...',
        '  Проверка соединения с иностранными сайтами (cloudflare)...',
        '  Проверка соединения с Discord...',
        '  Проверка соединения с YouTube...',
        '  Проверка Остальных сайтов (SoundCloud, Patreon, Roblox)...',
        '✅ Этот метод отлично работает для всех сервисов!',
        '\n⚙️ Идеальный метод найден (general (ALT3).bat)! Устанавливаем системную службу...',
        '🎉 ГОТОВО! Обход включен и будет запускаться вместе с Windows.'
      ];
      clearLog();
      let i = 0;
      const step = () => {
        if(i < lines.length){ logLine(lines[i]); i++; setTimeout(step, 420); }
        else {
          state.testing = false;
          mockConnected = true;
          window.zapretPush.testFinished(true);
          window.zapretPush.status({serviceStatus:'running', hasLocalProcess:false, isTesting:false});
        }
      };
      setTimeout(step, 350);
      return {ok:true};
    }
  };

  let mutationQueue = Promise.resolve();
  const bridgeReady = new Promise(resolve => {
    if(hasBridge()) resolve();
    else window.addEventListener('pywebviewready', resolve, {once:true});
  });
  async function call(method, ...args){
    if(window.__BOOT__ && !hasBridge()) await bridgeReady;
    if(hasBridge()) {
      const invoke = async () => {
        try { return await window.pywebview.api[method](...args); }
        catch(e){ toast('Не удалось выполнить действие: ' + String(e), 'error'); return {ok:false, error:String(e)}; }
      };
      if(method.startsWith('set_')) {
        const pending = mutationQueue.then(invoke);
        mutationQueue = pending.catch(() => {});
        return pending;
      }
      return invoke();
    }
    if(mock[method]) return mock[method](...args);
    return null;
  }

  function openPanel(el){ overlay.classList.add('show'); el.classList.add('show'); }
  function closeAllPanels(){
    overlay.classList.remove('show'); overlay.classList.remove('see-through');
    document.querySelectorAll('.drawer.show, .modal.show').forEach(e => e.classList.remove('show'));
  }
  overlay.addEventListener('click', closeAllPanels);
  document.addEventListener('keydown', e => { if(e.key === 'Escape') closeAllPanels(); });
  document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', closeAllPanels));

  $('btnSettings').addEventListener('click', () => { openPanel($('drawerSettings')); updateSeeThrough(); });
  $('btnDomains').addEventListener('click', async () => { await refreshDomains(); openPanel($('drawerDomains')); });
  $('btnHelp').addEventListener('click', async () => {
    const html = await call('get_help_text');
    if(html) $('helpBody').innerHTML = html;
    staggerReveal('#helpBody');
    openPanel($('modalHelp'));
  });
  $('btnCredits').addEventListener('click', async () => {
    const html = await call('get_credits_text');
    if(html) $('creditsBody').innerHTML = html;
    staggerReveal('#creditsBody');
    openPanel($('modalCredits'));
  });

  function staggerReveal(containerSel){
    const nodes = document.querySelectorAll(containerSel + ' > *');
    nodes.forEach((n, i) => {
      n.classList.remove('reveal');
      void n.offsetWidth;
      n.style.animationDelay = (i * 45) + 'ms';
      n.classList.add('reveal');
    });
  }

  const tabs = document.querySelectorAll('#settingsTabs .tab');
  const indicator = document.querySelector('#settingsTabs .tab-indicator');
  function positionIndicator(tabEl){
    indicator.style.width = tabEl.offsetWidth + 'px';
    indicator.style.transform = 'translateX(' + tabEl.offsetLeft + 'px)';
  }
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    positionIndicator(t);
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === t.dataset.tab));
    updateSeeThrough();
  }));

  async function refreshDomains(){
    const domains = await call('get_domains');
    renderDomains(domains || []);
  }
  function renderDomains(domains){
    const list = $('chipList');
    list.innerHTML = '';
    const editable = domains.filter(d => d.editable);
    if(!editable.length){ list.innerHTML = '<p class="empty-note">Список пуст. Добавьте домен выше.</p>'; return; }
    editable.forEach(d => {
      const chip = document.createElement('div');
      chip.className = 'chip';
      chip.innerHTML = '<span>' + escapeHtml(d.domain) + '</span><button aria-label="Удалить">✕</button>';
      chip.querySelector('button').addEventListener('click', async () => {
        chip.classList.add('removing');
        await call('remove_domain', d.domain);
        setTimeout(() => chip.remove(), 200);
      });
      list.appendChild(chip);
    });
  }
  $('domainForm').addEventListener('submit', async e => {
    e.preventDefault();
    const input = $('domainInput');
    const v = input.value.trim().toLowerCase();
    if(!v || /\s/.test(v)) return;
    await call('add_domain', v);
    input.value = '';
    await refreshDomains();
  });

  function renderStrategies(list, selected){
    const sel = $('strategySelect');
    sel.innerHTML = '';
    (list || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      if(s === selected) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  $('btnStartLocal').addEventListener('click', async () => {
    const button = $('btnStartLocal');
    button.disabled = true;
    try {
      const r = await call('start_local', $('strategySelect').value);
      toast(r && r.ok ? 'Локальный запуск включён' : ((r && r.error) || 'Не удалось запустить'), r && r.ok ? 'success' : 'error');
    } finally { button.disabled = false; }
  });
  $('btnStopLocal').addEventListener('click', async () => {
    const r = await call('stop_local');
    toast(r && r.ok ? 'Локальный запуск остановлен' : ((r && r.error) || 'Не удалось остановить процесс'), r && r.ok ? 'info' : 'error');
  });
  $('btnInstallService').addEventListener('click', async () => {
    const r = await call('install_service_manual', $('strategySelect').value);
    toast(r && r.ok ? 'Служба установлена' : 'Ошибка установки службы', r && r.ok ? 'success' : 'error');
    const s = await call('get_status');
    if(s) window.zapretPush.status(s);
  });
  [$('btnRemoveAll'), $('btnRemoveAll2')].forEach(b => b.addEventListener('click', async () => {
    await call('remove_all_bypasses');
    toast('Все обходы удалены', 'info');
    setConnectionState('idle');
  }));
  $('btnUpdateIpset').addEventListener('click', async () => {
    const r = await call('update_ipset');
    toast(r && r.ok ? 'IPSet обновлён' : 'Ошибка обновления IPSet', r && r.ok ? 'success' : 'error');
    if(r && r.ok) renderIpset(await call('get_ipset_status'));
  });

  /* ---------------- Game Filter ---------------- */
  const gameFilterSeg = $('gameFilterSeg');
  function renderGameFilter(mode){
    const m = mode || 'disabled';
    gameFilterSeg.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === m));
  }
  gameFilterSeg.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const prev = gameFilterSeg.querySelector('.seg-btn.active');
      renderGameFilter(btn.dataset.mode);
      const r = await call('set_game_filter', btn.dataset.mode);
      if(r && r.ok){
        toast('Game Filter: ' + btn.textContent.trim() + ' — перезапустите обход для применения', 'success');
      } else {
        toast('Не удалось изменить Game Filter', 'error');
        renderGameFilter(prev ? prev.dataset.mode : 'disabled');
      }
    });
  });

  /* ---------------- порты Game Filter ---------------- */
  const gfTcpPorts = $('gfTcpPorts'), gfUdpPorts = $('gfUdpPorts');
  function renderGfPorts(p){
    gfTcpPorts.value = (p && p.tcp) || '1024-65535';
    gfUdpPorts.value = (p && p.udp) || '1024-65535';
  }
  async function saveGfPorts(tcp, udp){
    const r = await call('set_game_filter_ports', tcp, udp);
    if(r && r.ok){
      renderGfPorts(r.ports);
      toast('Порты Game Filter сохранены — перезапустите обход для применения', 'success');
    } else {
      toast((r && r.error) || 'Не удалось сохранить порты', 'error');
    }
  }
  $('btnSavePorts').addEventListener('click', () => saveGfPorts(gfTcpPorts.value, gfUdpPorts.value));
  $('btnResetPorts').addEventListener('click', () => saveGfPorts('', ''));

  /* ---------------- автозапуск ---------------- */
  const autoChecks = { app:$('chkAutoApp'), service:$('chkAutoService'), proxy:$('chkAutoProxy') };
  const AUTO_NAMES = { app:'Автозапуск приложения', service:'Автозапуск службы', proxy:'Автозапуск Telegram-прокси' };
  function renderAutostart(a){
    const v = a || {};
    Object.keys(autoChecks).forEach(k => { autoChecks[k].checked = !!v[k]; });
  }
  Object.keys(autoChecks).forEach(k => {
    autoChecks[k].addEventListener('change', async () => {
      const want = autoChecks[k].checked;
      autoChecks[k].disabled = true;
      const r = await call('set_autostart', k, want);
      autoChecks[k].disabled = false;
      if(r && r.ok){
        toast(AUTO_NAMES[k] + (want ? ' включён' : ' выключен'), want ? 'success' : 'info');
      } else {
        toast((r && r.error) || ('Не удалось изменить: ' + AUTO_NAMES[k]), 'error');
      }
      renderAutostart(r && r.autostart ? r.autostart : { ...Object.fromEntries(Object.keys(autoChecks).map(x => [x, autoChecks[x].checked])), [k]: !want });
    });
  });

  /* ---------------- IPSet ---------------- */
  const IPSET_LABELS = { loaded:'loaded', none:'none', any:'any' };
  const IPSET_HINTS = {
    loaded:'«loaded» — обход применяется только к адресам из списка РФ. Нажмите, чтобы переключить на «none».',
    none:'«none» — список отключён (заглушка вместо реальных адресов). Нажмите, чтобы переключить на «any».',
    any:'«any» — обход применяется ко всем адресам без фильтра. Нажмите, чтобы вернуть «loaded» из резервной копии.'
  };
  function renderIpset(status){
    const s = status || 'any';
    $('ipsetStatusLabel').textContent = IPSET_LABELS[s] || s;
    $('ipsetHint').textContent = IPSET_HINTS[s] || IPSET_HINTS.any;
  }
  $('btnCycleIpset').addEventListener('click', async () => {
    const r = await call('cycle_ipset');
    if(r && r.ok){
      renderIpset(r.status);
      toast('Режим IPSet: ' + (IPSET_LABELS[r.status] || r.status), 'success');
    } else {
      toast((r && r.error) || 'Не удалось переключить режим IPSet', 'error');
    }
  });

  btnMagic.addEventListener('pointerdown', e => {
    const r = document.createElement('span');
    r.className = 'ripple';
    const rect = btnMagic.getBoundingClientRect();
    r.style.left = (e.clientX - rect.left) + 'px';
    r.style.top = (e.clientY - rect.top) + 'px';
    btnMagic.appendChild(r);
    setTimeout(() => r.remove(), 650);
  });
  btnMagic.addEventListener('click', async () => {
    if(state.testing) return;
    state.testing = true;
    btnMagic.disabled = true;
    ctaLabel.textContent = 'Идёт проверка...';
    spinner.hidden = false;
    clearLog();
    setConnectionState('testing');
    await call('start_auto_test');
  });

  /* ---------------- темы оформления ---------------- */
  const THEMES = ['standard','modern','ios26','custom'];
  const THEME_NAMES = { 'standard':'Стандарт', 'modern':'Модерн 010101', 'ios26':'IOS26', 'custom':'Своя тема' };
  const LOOKS = ['standard','modern','ios26'];
  const SCHEMES = ['classic','black','white'];
  const DEFAULT_SCHEMES = { standard:'classic', modern:'black', ios26:'classic' };
  const IOS_PALETTES = ['photo','aurora','ocean','sunset','graphite'];
  const LOOK_RADIUS = { standard:20, modern:0, ios26:26 };
  const ED_COLORS = ['bg','panel','term','text','border','accent','accent2','accent3','idle','testing'];
  let currentTheme = 'standard', currentLook = 'standard', currentPalette = 'photo';
  let schemes = Object.assign({}, DEFAULT_SCHEMES);
  let custom = null;
  let customVarNames = [];

  /* --- цветовые утилиты --- */
  function parseColor(str){
    const d = document.createElement('span');
    d.style.color = str; document.body.appendChild(d);
    const m = getComputedStyle(d).color.match(/[\d.]+/g); d.remove();
    return m ? { r:+m[0], g:+m[1], b:+m[2], a:(m[3] !== undefined ? +m[3] : 1) } : { r:0, g:0, b:0, a:1 };
  }
  const h2 = n => ('0' + Math.max(0, Math.min(255, Math.round(n))).toString(16)).slice(-2);
  const toHex = c => '#' + h2(c.r) + h2(c.g) + h2(c.b);
  const hexRgb = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];
  const rgbaStr = (h, a) => { const v = hexRgb(h); return 'rgba(' + v[0] + ',' + v[1] + ',' + v[2] + ',' + (Math.round(a*1000)/1000) + ')'; };
  function mixHex(a, b, t){ const x = hexRgb(a), y = hexRgb(b); return '#' + [0,1,2].map(i => h2(x[i]*(1-t) + y[i]*t)).join(''); }
  function lum(h){ const v = hexRgb(h).map(n => { n /= 255; return n <= .03928 ? n/12.92 : Math.pow((n+.055)/1.055, 2.4); }); return .2126*v[0] + .7152*v[1] + .0722*v[2]; }

  /* --- чтение цветов выбранной «основы» --- */
  function readBase(look, scheme){
    const root = document.documentElement;
    const keep = { t:root.getAttribute('data-theme'), s:root.getAttribute('data-scheme'), c:root.getAttribute('data-custom'), st:root.getAttribute('style') };
    root.removeAttribute('style'); root.removeAttribute('data-custom');
    root.setAttribute('data-theme', look); root.setAttribute('data-scheme', scheme);
    const cs = getComputedStyle(root);
    const g = n => parseColor(cs.getPropertyValue(n).trim());
    const bg = g('--bg-0'), panel = g('--bg-1'), border = g('--border');
    const out = {
      base: look, scheme: scheme,
      c: { bg: toHex(bg), panel: toHex(panel), term: toHex(bg), text: toHex(g('--text-0')), border: toHex(border),
           accent: toHex(g('--accent-mint')), accent2: toHex(g('--accent-cyan')), accent3: toHex(g('--accent-violet')),
           idle: toHex(g('--accent-coral')), testing: toHex(g('--accent-amber')) },
      panelA: Math.round(panel.a*100)/100, borderA: Math.round(border.a*100)/100,
      radius: LOOK_RADIUS[look], blur: 26
    };
    if(look === 'ios26'){
      out.c.bg = toHex(g('--p0')); out.c.accent2 = toHex(g('--p1')); out.c.accent3 = toHex(g('--p2')); out.c.accent = toHex(g('--p3'));
      out.c.panel = scheme === 'white' ? '#ffffff' : '#1e1a28';
      out.panelA = scheme === 'white' ? .6 : .3;
      out.c.term = scheme === 'white' ? '#ffffff' : '#120e1a';
    }
    if(look === 'modern') out.c.panel = out.c.bg;
    if(keep.t) root.setAttribute('data-theme', keep.t); else root.removeAttribute('data-theme');
    if(keep.s) root.setAttribute('data-scheme', keep.s); else root.removeAttribute('data-scheme');
    if(keep.c) root.setAttribute('data-custom', keep.c);
    if(keep.st) root.setAttribute('style', keep.st); else root.removeAttribute('style');
    return out;
  }

  /* --- переменные «своей» темы --- */
  function customVars(cu){
    const c = cu.c, dark = lum(c.bg) < .5, m = {};
    m['--bg-0'] = c.bg; m['--bg-1'] = rgbaStr(c.panel, cu.panelA); m['--bg-2'] = mixHex(c.panel, c.text, .1);
    m['--border'] = rgbaStr(c.border, cu.borderA); m['--border-soft'] = rgbaStr(c.border, cu.borderA * .6);
    m['--text-0'] = c.text; m['--text-1'] = mixHex(c.text, c.bg, .28); m['--text-2'] = mixHex(c.text, c.bg, .5);
    m['--accent-mint'] = c.accent; m['--accent-cyan'] = c.accent2; m['--accent-violet'] = c.accent3;
    m['--accent-coral'] = c.idle; m['--accent-amber'] = c.testing;
    m['--ink'] = c.text;
    m['--on-accent'] = cu.base === 'modern' ? c.bg : (lum(mixHex(c.accent, c.accent2, .5)) > .5 ? '#06111a' : '#ffffff');
    m['--bar-bg'] = 'linear-gradient(180deg, ' + rgbaStr(c.panel, .92) + ', ' + rgbaStr(c.panel, .6) + ')';
    m['--bar-bg-up'] = 'linear-gradient(0deg, ' + rgbaStr(c.panel, .92) + ', ' + rgbaStr(c.panel, .6) + ')';
    m['--overlay-bg'] = dark ? 'rgba(0,0,0,.6)' : 'rgba(20,28,54,.34)';
    m['--hover-soft'] = rgbaStr(c.text, .07); m['--scroll-thumb-hover'] = mixHex(c.bg, c.text, .2);
    m['--term-bg'] = rgbaStr(c.term, .55);
    // IOS26: фон из акцентов, стекло из цвета панелей
    m['--p0'] = c.bg; m['--p1'] = c.accent2; m['--p2'] = c.accent3; m['--p3'] = c.accent;
    m['--p4'] = mixHex(c.accent, c.accent3, .5); m['--p5'] = mixHex(c.accent2, c.accent3, .5);
    m['--p6'] = dark ? mixHex(c.bg, '#000000', .6) : mixHex(c.bg, '#ffffff', .5);
    const hl = dark ? ['rgba(255,255,255,.2)', 'rgba(255,255,255,.06)'] : ['rgba(255,255,255,.75)', 'rgba(255,255,255,.4)'];
    m['--glass'] = 'linear-gradient(180deg, ' + hl[0] + ', ' + hl[1] + '), ' + rgbaStr(c.panel, cu.panelA);
    m['--panel'] = 'linear-gradient(180deg, ' + hl[0] + ', ' + hl[1] + '), ' + rgbaStr(c.panel, Math.min(1, cu.panelA + .3));
    m['--field-bg'] = rgbaStr(mixHex(c.bg, dark ? '#000000' : '#ffffff', .4), .4);
    m['--select-bg'] = c.bg;
    m['--hi'] = c.text; m['--hi-soft'] = rgbaStr(c.text, .6);
    m['--tshadow'] = dark ? '0 1px 10px rgba(0,0,0,.22)' : 'none';
    m['--term-err'] = dark ? 'rgba(0,0,0,.35)' : rgbaStr(c.text, .12);
    m['--glass-blur'] = cu.blur + 'px'; m['--c-radius'] = cu.radius + 'px';
    return m;
  }
  function clearCustomVars(){
    const st = document.documentElement.style;
    customVarNames.forEach(n => st.removeProperty(n));
    customVarNames = [];
  }
  function applyCustomVars(cu){
    clearCustomVars();
    const st = document.documentElement.style, m = customVars(cu);
    Object.keys(m).forEach(n => { st.setProperty(n, m[n]); customVarNames.push(n); });
  }
  let themeSlots = [];
  function renderSlots(){
    [...$('themeSlot').options].forEach((o,i) => { o.textContent = 'Слот ' + (i+1) + (themeSlots[i] ? ' — сохранён' : ' — пусто'); });
  }
  function applyScale(value){
    const scale = [80,90,100,110,125,150].includes(+value) ? +value : 100;
    document.documentElement.style.zoom = scale / 100;
    document.documentElement.style.height = (10000 / scale) + 'vh';
    $('uiScale').value = String(scale);
    requestAnimationFrame(() => { moveGlider(); positionIndicator(document.querySelector('#settingsTabs .tab.active')); });
  }
  $('uiScale').addEventListener('change', async () => {
    const r = await call('set_ui_scale', +$('uiScale').value);
    if(r && r.ok) applyScale(r.scale);
  });
  $('saveSlot').addEventListener('click', async () => {
    const r = await call('set_theme_slot', +$('themeSlot').value, currentThemeSnapshot());
    if(r && r.ok){ themeSlots = r.slots; renderSlots(); toast('Тема сохранена в слот', 'success'); }
  });
  $('loadSlot').addEventListener('click', () => {
    const saved = themeSlots[+$('themeSlot').value];
    if(!saved){ toast('Этот слот пуст', 'info'); return; }
    custom = JSON.parse(JSON.stringify(saved)); applyTheme('custom', true); scheduleSaveCustom(true);
  });
  $('newTheme').addEventListener('click', () => { custom = readBase('standard','classic'); applyTheme('custom',true); scheduleSaveCustom(true); });
  $('themePreset').addEventListener('change', () => $('applyPreset').click());
  $('applyPreset').addEventListener('click', () => {
    const presets = {
      ocean:['#081a28','#102b3c','#06121d','#e6f6ff','#3d718b','#45d9b0','#59caff','#5576ed'],
      plum:['#201629','#30213e','#170e20','#f5e9ff','#755783','#d4a0ff','#ff91c8','#a688f5'],
      paper:['#f5f1e8','#fffdf6','#ebe5da','#282722','#b9ad98','#24664c','#285e94','#7e5a9d'],
      ember:['#17191d','#24272d','#101215','#f4ede0','#5c5347','#ffb454','#e98a61','#c29561']
    };
    const colors = presets[$('themePreset').value];
    custom = readBase('standard', $('themePreset').value === 'paper' ? 'white' : 'classic');
    ['bg','panel','term','text','border','accent','accent2','accent3'].forEach((k,i) => custom.c[k]=colors[i]);
    custom.panelA=1; custom.borderA=.5;
    applyTheme('custom',true); scheduleSaveCustom(true);
  });
  $('exportTheme').addEventListener('click', async () => {
    const r = await call('export_theme', currentThemeSnapshot());
    if(r && r.ok) toast('Тема экспортирована', 'success');
  });
  $('importTheme').addEventListener('click', () => $('themeFile').click());
  $('themeFile').addEventListener('change', async () => {
    const file = $('themeFile').files[0];
    try {
      if(!file) return;
      if(file.size > 65536) throw new Error('Файл темы слишком большой');
      const data = JSON.parse(await file.text());
      if(data.format && (data.format !== 'rknth' || data.version !== 1)) throw new Error('Неизвестный формат темы');
      $('edJson').value = JSON.stringify(data.theme || data);
      $('edImport').click();
    } catch(e){ toast('Не удалось импортировать тему: ' + String(e), 'error'); }
    finally { $('themeFile').value=''; }
  });
  let saveTimer = null;
  function scheduleSaveCustom(now){
    clearTimeout(saveTimer);
    const run = () => call('set_custom_theme', JSON.parse(JSON.stringify(custom)));
    if(now) run(); else saveTimer = setTimeout(run, 300);
  }

  /* --- применение тем --- */
  function syncRows(){
    const isCustom = currentTheme === 'custom';
    $('schemeBox').hidden = isCustom;
    $('themeEditor').hidden = !isCustom;
    const scheme = isCustom ? custom.scheme : schemes[currentTheme];
    $('variantIos').hidden = !(currentLook === 'ios26' && scheme === 'classic' && !isCustom);
    document.querySelectorAll('#schemeRow .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.scheme === scheme));
  }
  function applyTheme(name, save){
    if(THEMES.indexOf(name) < 0) name = 'standard';
    const root = document.documentElement;
    if(name === 'custom' && !custom){
      custom = readBase(currentLook, schemes[currentLook] || 'classic');
      scheduleSaveCustom(true);
    }
    currentTheme = name;
    if(name === 'custom'){
      currentLook = custom.base;
      root.setAttribute('data-theme', custom.base);
      root.setAttribute('data-scheme', custom.scheme);
      root.setAttribute('data-custom', '1');
      applyCustomVars(custom);
      fillEditor();
    } else {
      currentLook = name;
      clearCustomVars();
      root.removeAttribute('data-custom');
      root.setAttribute('data-theme', name);
      root.setAttribute('data-scheme', schemes[name] || DEFAULT_SCHEMES[name]);
    }
    document.querySelectorAll('#themeGrid .theme-card').forEach(c => c.classList.toggle('active', c.dataset.theme === name));
    syncRows();
    $('themePreset').value = '';
    if(save) call('set_theme', name);
  }
  function applyScheme(v, save){
    if(SCHEMES.indexOf(v) < 0 || currentTheme === 'custom') return;
    schemes[currentTheme] = v;
    document.documentElement.setAttribute('data-scheme', v);
    syncRows();
    if(save) call('set_scheme', currentTheme, v);
  }
  function applyPalette(v, save){
    if(IOS_PALETTES.indexOf(v) < 0) v = 'photo';
    currentPalette = v;
    document.documentElement.setAttribute('data-ios', v);
    document.querySelectorAll('#iosRow .swatch').forEach(b => b.classList.toggle('active', b.dataset.ios === v));
    if(save) call('set_variant', 'ios', v);
  }

  /* --- редактор своей темы --- */
  const SLIDERS = { radius:[1,'px'], panelA:[100,'%'], borderA:[100,'%'], blur:[1,'px'] };
  function fillEditor(){
    if(!custom) return;
    ED_COLORS.forEach(k => {
      const inp = document.querySelector('#themeEditor input[data-k="' + k + '"]');
      if(inp) inp.value = custom.c[k];
      const hx = document.querySelector('#themeEditor [data-hex="' + k + '"]');
      if(hx) hx.textContent = custom.c[k];
    });
    Object.keys(SLIDERS).forEach(k => {
      const sl = document.querySelector('#themeEditor input[data-sl="' + k + '"]');
      const v = Math.round(custom[k] * SLIDERS[k][0]);
      if(sl) sl.value = v;
      const lab = document.querySelector('#themeEditor [data-val="' + k + '"]');
      if(lab) lab.textContent = v + SLIDERS[k][1];
    });
    document.querySelectorAll('#edBase .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.base === custom.base));
    document.querySelectorAll('#edScheme .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.scheme === custom.scheme));
  }
  function customChanged(){
    $('themePreset').value = '';
    applyCustomVars(custom);
    scheduleSaveCustom(false);
  }
  document.querySelectorAll('#themeEditor input[data-k]').forEach(inp => {
    inp.addEventListener('input', () => {
      custom.c[inp.dataset.k] = inp.value;
      const hx = document.querySelector('#themeEditor [data-hex="' + inp.dataset.k + '"]');
      if(hx) hx.textContent = inp.value;
      customChanged();
    });
  });
  document.querySelectorAll('#themeEditor input[data-sl]').forEach(sl => {
    sl.addEventListener('input', () => {
      const k = sl.dataset.sl;
      custom[k] = (+sl.value) / SLIDERS[k][0];
      const lab = document.querySelector('#themeEditor [data-val="' + k + '"]');
      if(lab) lab.textContent = sl.value + SLIDERS[k][1];
      customChanged();
    });
  });
  function resetCustom(base, scheme){
    custom = readBase(base, scheme);
    applyTheme('custom', false);
    scheduleSaveCustom(true);
  }
  document.querySelectorAll('#edBase .seg-btn').forEach(b => b.addEventListener('click', () => resetCustom(b.dataset.base, custom.scheme)));
  document.querySelectorAll('#edScheme .seg-btn').forEach(b => b.addEventListener('click', () => resetCustom(custom.base, b.dataset.scheme)));
  $('edReset').addEventListener('click', () => { resetCustom(custom.base, custom.scheme); toast('Цвета сброшены к основе', 'info'); });
  function currentThemeSnapshot(){
    const data = JSON.parse(JSON.stringify(custom || readBase(currentLook, schemes[currentLook])));
    document.querySelectorAll('#themeEditor input[data-k]').forEach(i => { data.c[i.dataset.k]=i.value; });
    document.querySelectorAll('#themeEditor input[data-sl]').forEach(i => { data[i.dataset.sl]=(+i.value)/SLIDERS[i.dataset.sl][0]; });
    return data;
  }
  $('edCopy').addEventListener('click', async () => {
    const snapshot = currentThemeSnapshot();
    const text = JSON.stringify(snapshot, null, 2);
    $('edJson').value = text;
    if(hasBridge()){
      const r=await call('copy_theme', snapshot);
      toast(r && r.ok ? 'Код текущей темы скопирован' : ((r && r.error) || 'Не удалось скопировать; код доступен в поле ниже'), r && r.ok ? 'success' : 'error');
      return;
    }
    try { await navigator.clipboard.writeText(text); toast('Код текущей темы скопирован', 'success'); }
    catch(e){
      $('edJson').focus(); $('edJson').select();
      if(document.execCommand('copy')) toast('Код текущей темы скопирован', 'success');
      else toast('Скопируйте код из поля ниже', 'info');
    }
  });
  $('edImport').addEventListener('click', () => {
    try {
      const o = JSON.parse($('edJson').value);
      if(!o || !o.c || LOOKS.indexOf(o.base) < 0 || SCHEMES.indexOf(o.scheme) < 0) throw new Error('bad');
      const ok = ED_COLORS.every(k => /^#[0-9a-fA-F]{6}$/.test(o.c[k] || ''));
      if(!ok) throw new Error('bad');
      const num = (v, lo, hi, d) => { v = +v; return isNaN(v) ? d : Math.max(lo, Math.min(hi, v)); };
      custom = { base:o.base, scheme:o.scheme, c:Object.fromEntries(ED_COLORS.map(k => [k, o.c[k].toLowerCase()])),
                 panelA:num(o.panelA,0,1,1), borderA:num(o.borderA,0,1,.1), radius:Math.round(num(o.radius,0,40,20)), blur:Math.round(num(o.blur,0,60,26)) };
      applyTheme('custom', true);
      scheduleSaveCustom(true);
      toast('Тема применена', 'success');
    } catch(e){ toast('Не удалось прочитать код темы', 'error'); }
  });

  document.querySelectorAll('#themeGrid .theme-card').forEach(card => {
    card.addEventListener('click', () => {
      applyTheme(card.dataset.theme, true);
      toast('Тема: ' + THEME_NAMES[card.dataset.theme], 'info');
    });
  });
  document.querySelectorAll('#schemeRow .seg-btn').forEach(b => b.addEventListener('click', () => applyScheme(b.dataset.scheme, true)));
  document.querySelectorAll('#iosRow .swatch').forEach(b => b.addEventListener('click', () => applyPalette(b.dataset.ios, true)));
  $('btnTheme').addEventListener('click', () => {
    const list = THEMES.filter(t => t !== 'custom' || custom);
    const next = list[(list.indexOf(currentTheme) + 1) % list.length];
    applyTheme(next, true);
    toast('Тема: ' + THEME_NAMES[next], 'info');
  });
  // мгновенно применяем сохранённую «свою» тему (цвета лежат в переменных)
  if(window.__BOOT__ && window.__BOOT__.theme === 'custom' && window.__BOOT__.custom){
    custom = window.__BOOT__.custom;
    currentTheme = 'custom'; currentLook = custom.base;
    applyCustomVars(custom);
  }

  /* в разделе «Оформление» затемнение убираем, чтобы изменения темы были видны сразу */
  function updateSeeThrough(){
    const open = $('drawerSettings').classList.contains('show');
    const t = document.querySelector('#settingsTabs .tab.active');
    overlay.classList.toggle('see-through', open && !!t && t.dataset.tab === 'look');
  }

  /* ---------------- переключение разделов ---------------- */
  const viewTabs = Array.prototype.slice.call(document.querySelectorAll('#viewTabs .view-tab'));
  const glider = document.querySelector('#viewTabs .glider');
  const VIEW_ORDER = ['main','tg'];
  let currentView = 'main';

  function moveGlider(){
    const t = viewTabs.filter(x => x.classList.contains('active'))[0];
    if(!t) return;
    glider.style.width = t.offsetWidth + 'px';
    glider.style.transform = 'translateX(' + t.offsetLeft + 'px)';
  }
  function switchView(name){
    if(name === currentView) return;
    const dir = VIEW_ORDER.indexOf(name) > VIEW_ORDER.indexOf(currentView) ? 1 : -1;
    document.querySelectorAll('.view').forEach(v => {
      if(v.dataset.view === name){
        v.dataset.pos = dir > 0 ? 'right' : 'left';
        void v.offsetWidth;
        v.dataset.pos = 'center';
      } else if(v.dataset.pos === 'center'){
        v.dataset.pos = dir > 0 ? 'left' : 'right';
      }
    });
    currentView = name;
    viewTabs.forEach(t => t.classList.toggle('active', t.dataset.view === name));
    document.body.classList.toggle('view-tg', name === 'tg');
    moveGlider();
    if(name === 'tg') refreshTgStatus();
  }
  viewTabs.forEach(t => t.addEventListener('click', () => switchView(t.dataset.view)));
  window.addEventListener('resize', moveGlider);

  /* ---------------- тумблер «Лучший поиск» ---------------- */
  const bestToggle = $('bestSearchToggle');
  function setBest(value, save){
    const v = !!value;
    bestToggle.classList.toggle('on', v);
    bestToggle.setAttribute('aria-checked', v ? 'true' : 'false');
    if(save) call('set_best_search', v);
  }
  function toggleBest(){
    const v = !bestToggle.classList.contains('on');
    setBest(v, true);
    toast(v ? 'Лучший поиск включён — проверим все стратегии и выберем самую лучшую'
            : 'Лучший поиск выключен — берём первую полностью рабочую', v ? 'success' : 'info');
  }
  bestToggle.addEventListener('click', toggleBest);
  bestToggle.addEventListener('keydown', e => {
    if(e.key === ' ' || e.key === 'Enter'){ e.preventDefault(); toggleBest(); }
  });

  /* ---------------- Telegram-прокси ---------------- */
  const tgRadar = $('tgRadar');
  const btnTgPower = $('btnTgPower');
  const tgLabel = btnTgPower.querySelector('.cta-label');
  const tgSpin = btnTgPower.querySelector('.spinner');
  const btnTgApply = $('btnTgApply');
  let tgBusy = false;
  let seenConflict = null;
  $('tgDetailsToggle').addEventListener('click', () => {
    const open=$('tgDetails').classList.toggle('open');
    $('tgDetailsToggle').setAttribute('aria-expanded', String(open));
    $('tgDetailsBody').inert=!open;
  });
  for(const [id,kind] of [['socialTelegram','telegram'],['socialGithub','github']]){
    $(id).addEventListener('click',async()=>{
      const r=await call('open_project_link',kind);
      if(!r || !r.ok) toast((r && r.error) || 'Ссылка появится позже', 'info');
    });
  }
  function showPortConflict(conflict){
    if(!conflict || seenConflict===conflict.id) return;
    const previous=activeToasts.get('proxy-port-conflict');
    if(previous) previous.close();
    seenConflict=conflict.id;
    toast('Порт '+conflict.port+' занят. Возможно, запущен другой Telegram-прокси. Закрыть его и включить встроенный?', 'error', {
      key:'proxy-port-conflict', persistent:true, actions:[
        {label:'Закрыть (посторонний прокси)',run:async()=>{
          const r=await call('tg_resolve_port',conflict.id,true);
          if(r && r.status) renderTgStatus(r.status);
          toast(r && r.ok ? 'Прокси включён' : ((r && r.error) || 'Не удалось освободить порт'), r && r.ok ? 'success' : 'error');
        }},
        {label:'Отмена',run:async()=>{ await call('tg_resolve_port',conflict.id,false); }}
      ]
    });
  }

  function renderTgStatus(payload){
    const p = payload || {};
    if(p.portConflict) showPortConflict(p.portConflict);
    const on = !!p.running;
    const restarting = !!p.restarting;
    const missing = p.available === false;
    tgRadar.className = 'radar-wrap ' + (on ? 'state-local' : (restarting ? 'state-testing' : 'state-idle'));
    tgLabel.textContent = on ? 'Выключить Telegram-прокси' : 'Включить Telegram-прокси';
    btnTgPower.classList.toggle('on', on);
    btnTgPower.disabled = tgBusy || missing || restarting;
    if(missing){
      $('tgStatusText').textContent = 'Модуль прокси не найден — проверьте папку «proxy» рядом с программой';
    } else if(restarting){
      $('tgStatusText').textContent = 'Соединение прервалось, переподключаемся…';
    } else if(on){
      $('tgStatusText').textContent = 'Прокси работает — можно применять в Telegram';
    } else if(p.error){
      $('tgStatusText').textContent = p.error;
    } else {
      $('tgStatusText').textContent = 'Прокси выключен';
    }
    $('tgHost').textContent = p.host || '127.0.0.1';
    $('tgPort').textContent = p.port || '—';
    $('tgLink').textContent = p.link || '—';
    btnTgApply.disabled = !on;
    btnTgApply.classList.toggle('pulse', on);
  }
  async function refreshTgStatus(){
    const s = await call('tg_status');
    if(s) renderTgStatus(s);
  }

  btnTgPower.addEventListener('pointerdown', e => {
    const r = document.createElement('span');
    r.className = 'ripple';
    const rect = btnTgPower.getBoundingClientRect();
    r.style.left = (e.clientX - rect.left) + 'px';
    r.style.top = (e.clientY - rect.top) + 'px';
    btnTgPower.appendChild(r);
    setTimeout(() => r.remove(), 650);
  });
  btnTgPower.addEventListener('click', async () => {
    if(tgBusy) return;
    const wasOn = btnTgPower.classList.contains('on');
    tgBusy = true;
    btnTgPower.disabled = true;
    tgSpin.hidden = false;
    tgLabel.textContent = wasOn ? 'Останавливаем...' : 'Запускаем...';
    const r = await call(wasOn ? 'tg_stop' : 'tg_start');
    tgBusy = false;
    tgSpin.hidden = true;
    if(r && r.ok === false){
      if(!(r.status && r.status.portConflict)) toast(r.error || 'Не удалось запустить Telegram-прокси', 'error');
    } else {
      toast(wasOn ? 'Telegram-прокси остановлен' : 'Telegram-прокси запущен', wasOn ? 'info' : 'success');
    }
    renderTgStatus((r && r.status) || await call('tg_status'));
  });
  btnTgApply.addEventListener('click', async () => {
    const r = await call('tg_open_telegram');
    toast((r && r.ok)
      ? 'Открываем Telegram — подтвердите подключение прокси'
      : 'Не удалось открыть Telegram, скопируйте ссылку вручную', (r && r.ok) ? 'success' : 'error');
  });

  $('btnOpenDebugLog').addEventListener('click', () => call('open_debug_log'));
  $('btnOpenTgLog').addEventListener('click', () => call('open_tg_log'));

  async function init(){
    const data = await call('get_init_data');
    if(data){
      schemes = Object.assign({}, DEFAULT_SCHEMES, data.schemes || {});
      if(data.custom) custom = data.custom;
      applyPalette(data.iosPalette || 'photo', false);
      applyTheme(data.theme || 'standard', false);
      setBest(data.bestSearch, false);
      renderDomains(data.domains || []);
      renderStrategies(data.strategies || [], data.lastStrategy);
      renderTgStatus(data.tg || {});
      renderGameFilter(data.gameFilterMode || 'disabled');
      renderGfPorts(data.gameFilterPorts);
      renderAutostart(data.autostart);
      themeSlots = data.themeSlots || [];
      renderSlots();
      applyScale(data.uiScale || 100);
      renderIpset(data.ipsetStatus || 'any');
      window.zapretPush.status({ serviceStatus:data.serviceStatus, hasLocalProcess:data.hasLocalProcess, isTesting:false });
    }
    positionIndicator(document.querySelector('#settingsTabs .tab.active'));
    moveGlider();
    setTimeout(moveGlider, 400);
    setInterval(async () => {
      if(currentView === 'tg' && !tgBusy) refreshTgStatus();
      if(state.testing) return;
      const s = await call('get_status');
      if(s) window.zapretPush.status(s);
    }, 2500);
  }

  const MOCK_HELP_HTML = "\n<h4 class=\"reveal\">Включить обход</h4>\n<p class=\"reveal\">На главной нажмите «Найти и включить обход». Дождитесь результата в журнале. Рабочая стратегия будет установлена как служба.</p>\n<p class=\"reveal\">«Лучший поиск» проверяет все стратегии и выбирает лучшую по результатам проверки. Без него поиск останавливается на первой полностью рабочей стратегии.</p>\n<h4 class=\"reveal\">Если сайт не открывается</h4>\n<p class=\"reveal\">Нажмите «Добавить домен», укажите адрес без пути, например example.com, и повторите подбор. Проверьте подключение к интернету и журнал ошибок.</p>\n<h4 class=\"reveal\">Ручной выбор</h4>\n<p class=\"reveal\">В настройках выберите стратегию и нажмите «Принудить». Она работает до остановки или выхода из приложения. Для постоянной работы установите её на вкладке «Служба».</p>\n<h4 class=\"reveal\">Telegram</h4>\n<p class=\"reveal\">Откройте раздел Telegram, включите прокси и нажмите «Применить в телеграм». Подтвердите подключение в Telegram. Для работы прокси приложение должно оставаться запущенным, в том числе в трее.</p>\n<p class=\"reveal\">Если порт занят, выберите «Закрыть» или «Отмена» в уведомлении. Приложение завершит только распознанный Telegram Bridge, который занимает этот порт.</p>\n<h4 class=\"reveal\">Оформление и автозапуск</h4>\n<p class=\"reveal\">В «Оформлении» выберите тему и масштаб окна. В редакторе своей темы доступны готовые наборы, пять слотов, копирование и файлы .rknth. Галочки автозапуска находятся во вкладке «Управление».</p>\n<h4 class=\"reveal\">Остановка</h4>\n<p class=\"reveal\">Закрытие окна сворачивает приложение в трей. Для выхода используйте меню трея. Установленная служба управляется отдельно от окна приложения.</p>\n";
  const MOCK_CREDITS_HTML = [
    '<p class="reveal">Самое главное и человеческое спасибо — гению <strong>Flowseal</strong>. Благодаря ему миллионы людей без труда пользуются всеми сервисами из РФ бесплатно и с открытым кодом.</p>',
    '<p class="reveal">Огромное спасибо всему сообществу и энтузиастам, которые каждый день ищут новые пути обхода блокировок, поддерживая свободный интернет.</p>',
    '<p class="reveal"><strong>Автор оболочки</strong> — kere.</p>',
    '<p class="warn-box reveal">⚠️ Эта программа абсолютно бесплатна. Если кто-то продал её вам, требуйте возврата средств!</p>'
  ].join('');

  let initialized = false;
  function initOnce(){ if(initialized) return; initialized = true; init().catch(e => toast(String(e), 'error')); }
  if(window.__BOOT__){ bridgeReady.then(initOnce); }
  else if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initOnce, {once:true});
  else initOnce();
})();
</script>
</body>
</html>
"""

# =============================================================================
# СТАТИЧЕСКИЙ ТЕКСТ ДЛЯ МОДАЛЬНЫХ ОКОН (Помощь / Авторство)
# =============================================================================
HELP_HTML = """
<h4 class="reveal">Включить обход</h4>
<p class="reveal">На главной нажмите «Найти и включить обход». Дождитесь результата в журнале. Рабочая стратегия будет установлена как служба.</p>
<p class="reveal">«Лучший поиск» проверяет все стратегии и выбирает лучшую по результатам проверки. Без него поиск останавливается на первой полностью рабочей стратегии.</p>
<h4 class="reveal">Если сайт не открывается</h4>
<p class="reveal">Нажмите «Добавить домен», укажите адрес без пути, например example.com, и повторите подбор. Проверьте подключение к интернету и журнал ошибок.</p>
<h4 class="reveal">Ручной выбор</h4>
<p class="reveal">В настройках выберите стратегию и нажмите «Принудить». Она работает до остановки или выхода из приложения. Для постоянной работы установите её на вкладке «Служба».</p>
<h4 class="reveal">Telegram</h4>
<p class="reveal">Откройте раздел Telegram, включите прокси и нажмите «Применить в телеграм». Подтвердите подключение в Telegram. Для работы прокси приложение должно оставаться запущенным, в том числе в трее.</p>
<p class="reveal">Если порт занят, выберите «Закрыть» или «Отмена» в уведомлении. Приложение завершит только распознанный Telegram Bridge, который занимает этот порт.</p>
<h4 class="reveal">Оформление и автозапуск</h4>
<p class="reveal">В «Оформлении» выберите тему и масштаб окна. В редакторе своей темы доступны готовые наборы, пять слотов, копирование и файлы .rknth. Галочки автозапуска находятся во вкладке «Управление».</p>
<h4 class="reveal">Остановка</h4>
<p class="reveal">Закрытие окна сворачивает приложение в трей. Для выхода используйте меню трея. Установленная служба управляется отдельно от окна приложения.</p>
"""

CREDITS_HTML = """
<p class="reveal">Самое главное и человеческое спасибо я выражаю гению — <strong>Flowseal</strong>. Благодаря которому миллионы человек без труда могут пользоваться всеми сервисами из РФ бесплатно и с открытым кодом.</p>
<p class="reveal">Огромное спасибо всему сообществу и энтузиастам, которые каждый день ищут новые пути обхода блокировок, поддерживая свободный интернет.</p>
<p class="reveal"><strong>Автор оболочки</strong> — kere.<br><strong>Архитектура и написание кода</strong> — ИИ.</p>
<p class="warn-box reveal">⚠️ Эта программа абсолютно бесплатна. Если кто-то продал её вам, требуйте возврата средств!</p>
"""

# =============================================================================
# ФИРМЕННЫЙ ЗНАЧОК (для трея и как запасной вариант, если .ico не найден рядом)
# =============================================================================
def _draw_brand_icon(size: int = 64):
    """Рисует щит с галочкой на градиенте mint->cyan — тот же стиль, что и
    логотип в шапке приложения. Используется, если рядом с программой нет
    настоящего app_icon.ico (собранного installer_kit/make_icon.py)."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))

    pad = size * 0.05
    radius = size * 0.22
    mint = (51, 230, 166)
    cyan = (79, 209, 255)

    bg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(mint[0] + (cyan[0] - mint[0]) * t)
        g = int(mint[1] + (cyan[1] - mint[1]) * t)
        b = int(mint[2] + (cyan[2] - mint[2]) * t)
        bd.line([(0, y), (size, y)], fill=(r, g, b, 255))

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [pad, pad, size - pad, size - pad], radius=radius, fill=255)
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)
    dark = (9, 12, 26, 255)
    cx, cy = size / 2, size / 2 * 1.02
    w, h = size * 0.46, size * 0.52
    shield = [
        (cx, cy - h / 2),
        (cx + w / 2, cy - h / 2 + h * 0.16),
        (cx + w / 2, cy + h * 0.05),
        (cx, cy + h / 2),
        (cx - w / 2, cy + h * 0.05),
        (cx - w / 2, cy - h / 2 + h * 0.16),
    ]
    d.polygon(shield, fill=dark)

    stroke = max(2, int(size * 0.07))
    p1 = (cx - w * 0.22, cy)
    p2 = (cx - w * 0.03, cy + h * 0.18)
    p3 = (cx + w * 0.27, cy - h * 0.15)
    d.line([p1, p2], fill=mint, width=stroke)
    d.line([p2, p3], fill=mint, width=stroke)
    return img


def _find_brand_icon_file() -> str:
    """Ищет собранный installer_kit'ом app_icon.ico рядом с программой —
    и в установленной, и в распакованной onefile-версии."""
    candidates = [os.path.join(ZAPRET_BASE_DIR, 'app_icon.ico')]
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, 'app_icon.ico'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


# =============================================================================
# СОСТОЯНИЕ ПРИЛОЖЕНИЯ И МОСТ PYTHON <-> JS
# =============================================================================
class AppState:
    def __init__(self):
        self.window = None
        self.process = None
        self.config = load_config()
        self.strategies = scan_strategies()
        self.gf = get_game_filter(self.config)
        self.is_auto_testing = False
        self.tray_icon = None
        self.want_quit = False
        self._last_status_payload = None

        # Раньше каждый push_log/push_toast/push_status создавал НОВЫЙ поток
        # и дёргал window.evaluate_js() прямо из него. WebView2 не любит,
        # когда его дёргают из множества потоков одновременно — при большом
        # количестве строк лога (особенно в режиме "Лучший поиск", где
        # перебираются все стратегии без ранней остановки) это создавало
        # десятки потоков за секунды и могло уронить окно целиком.
        # Теперь все вызовы evaluate_js идут через очередь и один-единственный
        # долгоживущий поток-диспетчер — быстро, по порядку и безопасно.
        self._js_queue = queue.Queue()
        self._js_thread = threading.Thread(
            target=self._js_dispatcher, daemon=True, name='js-dispatcher')
        self._js_thread.start()

        self.tg_proxy = TgProxyManager(self.config, on_change=self._on_tg_proxy_change)
        if self.config.get("tg_secret") != self.tg_proxy.secret:
            self.config["tg_secret"] = self.tg_proxy.secret
            save_config(self.config)
        restore_user_files()
        ensure_user_lists()
        backup_user_files()
        if not os.path.exists(CONFIG_FILE) or not os.path.exists(BACKUP_CONFIG_FILE):
            try: save_config(self.config)
            except Exception: pass

    def _js_dispatcher(self):
        while True:
            expr = self._js_queue.get()
            if expr is None:
                continue
            try:
                if self.window is not None:
                    self.window.evaluate_js(expr)
            except Exception:
                pass

    def push_js(self, expr: str):
        try:
            self._js_queue.put_nowait(expr)
        except Exception:
            pass

    def _on_tg_proxy_change(self):
        """Колбэк из TgProxyManager (фоновый поток) — сразу шлём во фронтенд
        актуальный статус, не дожидаясь следующего опроса раз в 2.5с."""
        self.push_js(
            f"window.zapretPush && window.zapretPush.tgStatus("
            f"{json.dumps(self.tg_proxy.status())})")
        self._refresh_tray_menu()

    def push_log(self, message: str):
        self.push_js(f"window.zapretPush && window.zapretPush.log({json.dumps(message)})")

    def push_clear_log(self):
        self.push_js("window.zapretPush && window.zapretPush.clearLog()")

    def push_toast(self, message: str, kind: str = "info"):
        self.push_js(f"window.zapretPush && window.zapretPush.toast({json.dumps(message)}, {json.dumps(kind)})")

    def push_status(self):
        payload = {
            "serviceStatus": get_service_status(),
            "hasLocalProcess": self.process is not None and self.process.poll() is None,
            "isTesting": self.is_auto_testing,
        }
        if payload == self._last_status_payload:
            return
        self._last_status_payload = payload
        self.push_js(f"window.zapretPush && window.zapretPush.status({json.dumps(payload)})")
        self._refresh_tray_menu()

    def push_test_finished(self, success: bool):
        self.push_js(f"window.zapretPush && window.zapretPush.testFinished({json.dumps(bool(success))})")

    def status_loop(self):
        while not self.want_quit:
            if not self.is_auto_testing:
                self.push_status()
            time.sleep(2)

    def auto_test_thread(self):
        success = False
        try:
            self.push_clear_log()
            debug_log_reset()
            self.push_log("Начинаем автоматический подбор метода обхода блокировки...")
            self.push_log("1. Остановка текущих процессов и служб NERKN...")
            remove_service()
            time.sleep(1.5)

            best_search = bool(self.config.get("best_search", False))
            if best_search:
                self.push_log("Режим «Лучший поиск»: проверим ВСЕ стратегии и выберем самую лучшую. Это дольше.")
            else:
                self.push_log("Быстрый режим: остановимся на первой полностью рабочей стратегии.")

            strategies = [s for s in self.strategies if s.endswith('.bat')]
            best_strategy = None
            best_score = -1
            best_elapsed = float('inf')

            for i, bat in enumerate(strategies, 1):
                if not self.is_auto_testing: break
                self.push_log(f"\n[{i}/{len(strategies)}] Тестируем метод: {bat} ...")
                debug_log(f"\n===== [{i}/{len(strategies)}] {bat} =====")
                try:
                    _debug_args = parse_strategy_args(bat, self.gf)
                    debug_log("Аргументы winws.exe:")
                    for _a in _debug_args:
                        debug_log(f"  [{_a}]")
                except Exception as _e:
                    debug_log(f"(не удалось получить аргументы для отладки: {_e})")
                proc = start_standalone(bat, self.gf)
                if not proc:
                    self.push_log("  ❌ Не удалось запустить процесс.")
                    continue

                time.sleep(2.0)

                if proc.poll() is not None:
                    exit_code = proc.returncode
                    try:
                        raw_output = proc.stdout.read() if proc.stdout else ""
                    except Exception:
                        raw_output = ""
                    self.push_log(f"  ❌ Процесс завершился сразу после запуска (стратегия несовместима).")
                    debug_log(f"Код возврата: {exit_code}")
                    if raw_output and raw_output.strip():
                        debug_log("Вывод winws.exe:")
                        for out_line in raw_output.strip().splitlines():
                            debug_log(f"  {out_line}")
                    else:
                        debug_log("(winws.exe не вывел никакого текста — вероятно, процесс был "
                                  "принудительно завершён антивирусом/Защитником Windows сразу после старта, "
                                  "либо не смог зарегистрировать драйвер WinDivert.)")
                    stop_standalone(proc)
                    continue

                user_domains = [d["domain"] for d in load_domains() if d["editable"] and d["domain"] != "domain.example.abc"]

                self.push_log("  Проверяем Cloudflare, Discord, YouTube и остальные сервисы параллельно...")
                groups = {
                    "cloudflare": ["https://cloudflare.com"],
                    "discord": ["https://discord.com/api/v9/gateway"],
                    "youtube": ["https://googlevideo.com", "https://www.youtube.com"],
                    "others": ["https://soundcloud.com", "https://patreon.com", "https://roblox.com"],
                }
                if user_domains:
                    groups["user"] = [f"https://{d}" for d in user_domains[:3]]

                _t0 = time.monotonic()
                results = check_any_parallel(groups)
                elapsed = time.monotonic() - _t0
                cf_ok = results["cloudflare"]
                discord_ok = results["discord"]
                youtube_ok = results["youtube"]
                others_ok = results["others"]
                user_ok = results["user"] if user_domains else True

                self.push_log(
                    "  Cloudflare: " + ("✅" if cf_ok else "❌")
                    + "  Discord: " + ("✅" if discord_ok else "❌")
                    + "  YouTube: " + ("✅" if youtube_ok else "❌")
                    + "  Остальные: " + ("✅" if others_ok else "❌")
                    + ("  Ваши домены: " + ("✅" if user_ok else "❌") if user_domains else "")
                )

                stop_standalone(proc)

                score = sum([cf_ok, discord_ok, youtube_ok, others_ok, user_ok])
                debug_log(f"Итог {bat}: score={score}/5, время проверки {elapsed:.2f}с")

                is_better = (score > best_score) or (score == best_score and elapsed < best_elapsed)
                if is_better:
                    best_score = score
                    best_elapsed = elapsed
                    best_strategy = bat

                if score == 5:
                    if best_search:
                        self.push_log(f"✅ Метод открывает все сервисы (за {elapsed:.1f}с). "
                                      "Продолжаем проверку — вдруг найдётся ещё лучше.")
                    else:
                        self.push_log("✅ Этот метод отлично работает для всех сервисов!")
                        break
                elif score > 0:
                    self.push_log(f"⚠️ Метод работает частично ({score}/5).")
                else:
                    self.push_log("❌ Метод не подошел.")

            success = False
            if best_strategy and best_score > 0 and self.is_auto_testing:
                if best_score < 5:
                    self.push_log(f"\n⚠️ Идеальный метод не найден, но выбран наиболее рабочий: {best_strategy}.")
                    self.push_log("Ваш провайдер блокирует некоторые сервисы в любом случае, прочитайте 'Помощь' или обратитесь к kere.")
                elif best_search:
                    self.push_log(f"\n🏆 Проверены все стратегии. Лучшая: {best_strategy} "
                                  f"(5/5, самый быстрый отклик — {best_elapsed:.1f}с). Устанавливаем системную службу...")
                else:
                    self.push_log(f"\n⚙️ Идеальный метод найден ({best_strategy})! Устанавливаем системную службу...")

                success = install_service(best_strategy, self.gf)
                if success:
                    self.config["last_strategy"] = best_strategy
                    save_config(self.config)
                    self.push_log("🎉 ГОТОВО! Обход включен и будет запускаться вместе с Windows.")
                else:
                    self.push_log("❌ Ошибка при создании службы Windows.")
            elif self.is_auto_testing:
                self.push_log("\n❌ К сожалению, ни один из методов не смог пробить блокировку.")
        finally:
            self.is_auto_testing = False
            self.push_test_finished(success if 'success' in dir() else False)
            self.push_status()

    def create_tray_image(self):
        icon_path = _find_brand_icon_file()
        if icon_path:
            try:
                img = Image.open(icon_path).convert('RGBA')
                # .ico хранит несколько размеров — берём тот, что ближе к
                # типичному размеру значка в трее, чтобы не терять резкость
                if max(img.size) > 96:
                    img = img.resize((64, 64), Image.LANCZOS)
                return img
            except Exception:
                pass
        return _draw_brand_icon(64)

    def _tray_state_label(self) -> str:
        if self.is_auto_testing:
            return "NERKN: идёт подбор метода..."
        if get_service_status() == "running" or self.process is not None:
            return "NERKN: обход включён"
        return "NERKN: обход выключен"

    def _tray_bypass_label(self) -> str:
        return ("⏹  Остановить обход"
                if (get_service_status() == "running" or self.process is not None)
                else "▶  Включить обход")

    def _tray_tg_label(self) -> str:
        return ("✈  Выключить Telegram-прокси"
                if self.tg_proxy.running
                else "✈  Включить Telegram-прокси")

    def _build_tray_menu(self):
        return (
            item(self._tray_state_label(), lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            item('Открыть окно', self._tray_show, default=True),
            item(self._tray_bypass_label(), self._tray_toggle_bypass),
            item(self._tray_tg_label(), self._tray_toggle_tg),
            pystray.Menu.SEPARATOR,
            item('Выход', self._tray_quit),
        )

    def _refresh_tray_menu(self):
        if self.tray_icon is None:
            return
        try:
            self.tray_icon.menu = pystray.Menu(*self._build_tray_menu())
            self.tray_icon.update_menu()
        except Exception:
            pass

    def start_tray_icon(self):
        if self.tray_icon is not None:
            return
        self.tray_icon = pystray.Icon(
            "NERKN", self.create_tray_image(), "NERKN", pystray.Menu(*self._build_tray_menu()))
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_show(self, icon=None, tray_item=None):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        if self.window is not None:
            self.window.show()

    def _tray_toggle_bypass(self, icon=None, tray_item=None):
        """Быстрое вкл/выкл обхода прямо из трея, без открытия окна."""
        def worker():
            if get_service_status() == "running" or self.process is not None:
                remove_service()
                stop_standalone(self.process)
                self.process = None
                self.push_toast("Обход остановлен из трея", "info")
            else:
                strategy = self.config.get("last_strategy") or (self.strategies[0] if self.strategies else "")
                if not strategy:
                    self.push_toast("Нет сохранённой стратегии — откройте окно и запустите подбор", "error")
                else:
                    ok = install_service(strategy, self.gf)
                    self.push_toast(
                        "Обход включён из трея" if ok else "Не удалось включить обход",
                        "success" if ok else "error")
            self._last_status_payload = None  # форсируем пересчёт и пуш статуса
            self.push_status()
        threading.Thread(target=worker, daemon=True, name='tray-toggle-bypass').start()

    def _tray_toggle_tg(self, icon=None, tray_item=None):
        def worker():
            if self.tg_proxy.running:
                self.tg_proxy.stop()
                self.push_toast("Telegram-прокси остановлен из трея", "info")
            else:
                ok, err = self.tg_proxy.start()
                self.push_toast(
                    "Telegram-прокси запущен из трея" if ok else (err or "Не удалось запустить Telegram-прокси"),
                    "success" if ok else "error")
            self._on_tg_proxy_change()
        threading.Thread(target=worker, daemon=True, name='tray-toggle-tg').start()

    def _tray_quit(self, icon=None, tray_item=None):
        self.want_quit = True
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        if self.process is not None:
            stop_standalone(self.process)
        try:
            self.tg_proxy.stop()
        except Exception:
            pass
        os._exit(0)

    def hide_to_tray(self):
        if self.window is not None:
            threading.Thread(target=self.window.hide, daemon=True).start()
        self.start_tray_icon()

    def on_closing(self):
        if self.want_quit:
            return True
        self.hide_to_tray()
        return False

    def on_ready(self):
        threading.Thread(target=self.status_loop, daemon=True).start()
        if AUTOSTART_LAUNCH:
            # запуск при входе в Windows: окно скрыто, живём в трее
            self.start_tray_icon()
        threading.Thread(target=self._startup_actions, daemon=True, name='startup-actions').start()

    def _wait_network(self, attempts: int = 30):
        """При автозапуске сеть может подняться позже приложения."""
        for _ in range(attempts):
            for host, port in (("149.154.167.220", 443), ("1.1.1.1", 443)):
                try:
                    with socket.create_connection((host, port), timeout=2.0):
                        return True
                except OSError:
                    pass
            time.sleep(1.0)
        return False

    def _startup_actions(self):
        """Автозапуск службы и Telegram-прокси согласно чекбоксам в настройках."""
        try:
            # самолечение: после переустановки путь к exe мог измениться — пересоздаём задачу
            if autostart_app_enabled():
                set_autostart_app(True)
        except Exception as exc:
            debug_log(f"startup: обновление задачи автозапуска: {exc!r}")
        try:
            if self.config.get("autostart_service", True) and get_service_status() == "stopped":
                start_installed_service()
                self._last_status_payload = None
                self.push_status()
        except Exception as exc:
            debug_log(f"startup: служба: {exc!r}")
        try:
            if self.config.get("autostart_proxy", False) and not self.tg_proxy.running:
                self._wait_network()
                ok, err = False, ""
                for attempt in range(3):
                    ok, err = self.tg_proxy.start()
                    if ok or not self.tg_proxy.is_available():
                        break
                    time.sleep(3.0)
                debug_log(f"startup: Telegram-прокси ok={ok} {err}")
                self.push_toast("Telegram-прокси запущен автоматически" if ok
                                else (err or "Не удалось автоматически запустить Telegram-прокси"),
                                "success" if ok else "error")
                self._on_tg_proxy_change()
        except Exception as exc:
            debug_log(f"startup: Telegram-прокси: {exc!r}")

# =============================================================================
# JS API (вызывается из фронтенда как window.pywebview.api.<метод>(...))
# =============================================================================
class Api:
    def __init__(self, app: AppState):
        self._app = app
        self._local_lock = threading.Lock()

    def get_init_data(self):
        return {
            "strategies": self._app.strategies,
            "lastStrategy": self._app.config.get("last_strategy", self._app.strategies[0] if self._app.strategies else ""),
            "domains": load_domains(),
            "serviceStatus": get_service_status(),
            "hasLocalProcess": self._app.process is not None and self._app.process.poll() is None,
            "theme": normalize_theme(self._app.config.get("theme", "standard")),
            "schemes": get_schemes(self._app.config),
            "custom": sanitize_custom(self._app.config.get("custom_theme")),
            "iosPalette": self._app.config.get("ios_palette", "photo"),
            "bestSearch": bool(self._app.config.get("best_search", False)),
            "tg": self._app.tg_proxy.status(),
            "gameFilterMode": self._app.gf.get("mode", "disabled"),
            "gameFilterPorts": get_game_filter_ports(self._app.config),
            "ipsetStatus": get_ipset_status(),
            "autostart": self.get_autostart(),
            "uiScale": normalize_scale(self._app.config.get("ui_scale")),
            "themeSlots": self._theme_slots(),
        }

    # ---------- Game Filter / IPSet (перенесено из service.bat) ----------
    def set_game_filter(self, mode: str):
        ok = set_game_filter_mode(mode)
        if ok:
            self._app.gf = get_game_filter(self._app.config)
        return {"ok": ok, "mode": self._app.gf.get("mode", "disabled")}

    def set_game_filter_ports(self, tcp: str, udp: str):
        """Порты GameFilter TCP/UDP (Flowseal 1.10.3). Пусто = 1024-65535."""
        t, u = sanitize_ports(tcp), sanitize_ports(udp)
        if t is None or u is None:
            return {"ok": False, "error": "Неверный формат. Пример: 1024-1934,1936-65535",
                    "ports": get_game_filter_ports(self._app.config)}
        self._app.config["gf_tcp_ports"] = t
        self._app.config["gf_udp_ports"] = u
        save_config(self._app.config)
        self._app.gf = get_game_filter(self._app.config)
        return {"ok": True, "error": "", "ports": {"tcp": t, "udp": u}}

    # ---------- автозапуск ----------
    def get_autostart(self):
        return {
            "app": autostart_app_enabled(),
            "service": bool(self._app.config.get("autostart_service", True)),
            "proxy": bool(self._app.config.get("autostart_proxy", False)),
        }

    def set_autostart(self, kind: str, enabled: bool):
        enabled = bool(enabled)
        ok, err = True, ""
        if kind == "app":
            ok, err = set_autostart_app(enabled)
        elif kind == "service":
            previous = bool(self._app.config.get("autostart_service", True))
            ok = set_service_start_type(enabled)
            if ok:
                self._app.config["autostart_service"] = enabled
                try:
                    save_config(self._app.config)
                except Exception as exc:
                    self._app.config["autostart_service"] = previous
                    restored = set_service_start_type(previous)
                    ok = False
                    err = f"Не удалось сохранить настройку автозапуска: {exc}"
                    if not restored:
                        err += ". Не удалось вернуть прежний режим службы; проверьте его в Windows."
            else:
                err = "Windows не смогла изменить автозапуск службы. Прежняя настройка сохранена; подробности в журнале."
        elif kind == "proxy":
            self._app.config["autostart_proxy"] = enabled
            save_config(self._app.config)
        else:
            ok, err = False, "Неизвестный параметр"
        return {"ok": ok, "error": err, "autostart": self.get_autostart()}

    def get_ipset_status(self):
        return get_ipset_status()

    def cycle_ipset(self):
        ok, status, err = cycle_ipset_status()
        return {"ok": ok, "status": status, "error": err}

    # ---------- оформление и режим подбора ----------
    def _theme_slots(self):
        saved = self._app.config.get("theme_slots", [])
        if not isinstance(saved, list):
            saved = []
        return [sanitize_custom(saved[i]) if i < len(saved) else None for i in range(5)]

    def set_theme_slot(self, slot, data):
        clean = sanitize_custom(data)
        if not isinstance(slot, int) or slot not in range(5) or clean is None:
            return {"ok": False}
        slots = self._theme_slots()
        slots[slot] = clean
        self._app.config["theme_slots"] = slots
        save_config(self._app.config)
        return {"ok": True, "slots": slots}

    def set_ui_scale(self, value):
        scale = normalize_scale(value)
        self._app.config["ui_scale"] = scale
        save_config(self._app.config)
        return {"ok": True, "scale": scale}

    def open_project_link(self, kind):
        url = PROJECT_LINKS.get(kind, "")
        if not url:
            return {"ok": False, "error": "Ссылка проекта появится позже"}
        if not url.startswith('https://'):
            return {"ok": False, "error": "Для ссылки проекта нужен адрес https://"}
        return {"ok": bool(webbrowser.open(url))}

    def copy_theme(self, data):
        clean = sanitize_custom(data)
        if clean is None:
            return {"ok": False, "error": "Не удалось прочитать текущую тему"}
        try:
            copy_text_to_clipboard(json.dumps(clean, ensure_ascii=False, indent=2))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"Буфер обмена недоступен: {exc}. Код доступен в поле ниже."}

    def export_theme(self, data):
        clean = sanitize_custom(data)
        if clean is None:
            return {"ok": False}
        selected = self._app.window.create_file_dialog(webview.FileDialog.SAVE,
            save_filename="my-theme.rknth", file_types=("NERKN theme (*.rknth)",))
        if not selected:
            return {"ok": False, "cancelled": True}
        path = selected if isinstance(selected, str) else selected[0]
        if not path.lower().endswith('.rknth'):
            path += '.rknth'
        _write_json_atomic(path, {"format": "rknth", "version": 1, "theme": clean})
        return {"ok": True}

    def set_theme(self, theme: str):
        self._app.config["theme"] = normalize_theme(theme)
        save_config(self._app.config)
        return {"ok": True}

    def set_variant(self, kind: str, value: str):
        """Палитра фона IOS26 (kind == "ios")."""
        if kind == "ios" and value in IOS_PALETTES:
            self._app.config["ios_palette"] = value
        else:
            return {"ok": False}
        save_config(self._app.config)
        return {"ok": True}

    def set_scheme(self, theme: str, scheme: str):
        """Цветовая схема темы: classic / black / white."""
        if theme not in LOOK_KEYS or scheme not in SCHEME_KEYS:
            return {"ok": False}
        schemes = get_schemes(self._app.config)
        schemes[theme] = scheme
        self._app.config["schemes"] = schemes
        save_config(self._app.config)
        return {"ok": True}

    def set_custom_theme(self, data):
        """Сохраняет «свою» тему из редактора."""
        clean = sanitize_custom(data)
        if clean is None:
            return {"ok": False}
        self._app.config["custom_theme"] = clean
        save_config(self._app.config)
        return {"ok": True}

    def set_best_search(self, enabled: bool):
        self._app.config["best_search"] = bool(enabled)
        save_config(self._app.config)
        return {"ok": True}

    # ---------- логи ----------
    def open_debug_log(self):
        debug_log_open()
        return {"ok": True}

    def open_tg_log(self):
        tg_proxy_log_open()
        return {"ok": True}

    # ---------- Telegram-прокси ----------
    def tg_status(self):
        return self._app.tg_proxy.status()

    def tg_start(self):
        ok, err = self._app.tg_proxy.start()
        return {"ok": ok, "error": err, "status": self._app.tg_proxy.status()}

    def tg_resolve_port(self, token, close_proxy):
        ok, error = self._app.tg_proxy.resolve_port_conflict(token, bool(close_proxy))
        return {"ok": ok, "error": error, "status": self._app.tg_proxy.status()}

    def tg_stop(self):
        self._app.tg_proxy.stop()
        return {"ok": True, "error": "", "status": self._app.tg_proxy.status()}

    def tg_open_telegram(self):
        if not self._app.tg_proxy.running:
            return {"ok": False, "error": "Прокси не запущен"}
        return {"ok": self._app.tg_proxy.open_in_telegram(), "error": ""}

    def get_status(self):
        return {
            "serviceStatus": get_service_status(),
            "hasLocalProcess": self._app.process is not None and self._app.process.poll() is None,
            "isTesting": self._app.is_auto_testing,
        }

    def get_help_text(self):
        return HELP_HTML

    def get_credits_text(self):
        return CREDITS_HTML

    def start_auto_test(self):
        if self._app.is_auto_testing:
            return {"ok": False}
        self._app.is_auto_testing = True
        threading.Thread(target=self._app.auto_test_thread, daemon=True).start()
        return {"ok": True}

    def get_domains(self):
        return load_domains()

    def add_domain(self, domain: str):
        domain = (domain or "").strip().lower()
        if not domain or " " in domain:
            return {"ok": False}
        user_doms = [x["domain"] for x in load_domains() if x["editable"]]
        if domain not in user_doms:
            user_doms.append(domain)
            save_user_domains(user_doms)
        release_domain_from_excludes(domain)
        backup_user_files()
        return {"ok": True}

    def remove_domain(self, domain: str):
        domain = (domain or "").strip().lower()
        user_doms = [x["domain"] for x in load_domains() if x["editable"] and x["domain"] != domain]
        if not user_doms:
            user_doms = ["domain.example.abc"]
        save_user_domains(user_doms)
        restore_domain_to_excludes(domain)
        backup_user_files()
        return {"ok": True}

    def start_local(self, strategy: str):
        with self._local_lock:
            if self._app.is_auto_testing:
                return {"ok": False, "error": "Дождитесь завершения автоматического подбора."}
            if self._app.process is not None and self._app.process.poll() is None:
                return {"ok": False, "error": "Ручной обход уже запущен. Нажмите «Остановить» перед выбором другой стратегии."}
            if get_service_status() == "running":
                return {"ok": False, "error": "Служба обхода уже работает. Сначала остановите её через меню приложения в трее, затем нажмите «Принудить»."}
            if strategy not in self._app.strategies:
                return {"ok": False, "error": "Выберите существующую стратегию из списка."}
            proc = start_standalone(strategy, self._app.gf)
            if proc is None:
                return {"ok": False, "error": "Не удалось запустить выбранную стратегию. Проверьте файлы winws.exe и стратегии."}
            self._app.process = proc
            self._app.config["last_strategy"] = strategy
            save_config(self._app.config)
            self._app.push_status()
            return {"ok": True}

    def stop_local(self):
        with self._local_lock:
            proc = self._app.process
            stop_standalone(proc)
            if proc is not None:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    return {"ok": False, "error": "Процесс ещё не остановился. Повторите остановку через несколько секунд."}
            self._app.process = None
            self._app.push_status()
            return {"ok": True}

    def install_service_manual(self, strategy: str):
        ok = install_service(strategy, self._app.gf)
        if ok:
            self._app.config["last_strategy"] = strategy
            save_config(self._app.config)
        self._app.push_status()
        return {"ok": ok}

    def remove_all_bypasses(self):
        self._app.is_auto_testing = False
        remove_service()
        stop_standalone(self._app.process)
        self._app.process = None
        self._app.push_status()
        return {"ok": True}

    def update_ipset(self):
        try:
            r = requests.get(IPSET_UPDATE_URL, timeout=10)
            r.raise_for_status()
            with open(IPSET_FILE, 'w', encoding='utf-8') as f:
                f.write(r.text)
            return {"ok": True}
        except Exception:
            return {"ok": False}

# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================
def main():
    app_state = AppState()
    api = Api(app_state)

    cfg = app_state.config
    theme = normalize_theme(cfg.get("theme", "standard"))
    schemes = get_schemes(cfg)
    custom = sanitize_custom(cfg.get("custom_theme")) if theme == "custom" else None
    if theme == "custom" and custom is None:
        theme = "standard"
    palette = cfg.get("ios_palette", "photo")
    palette = palette if palette in IOS_PALETTES else "photo"
    if custom:
        look, scheme, bg_color = custom["base"], custom["scheme"], custom["c"]["bg"]
    else:
        look, scheme = theme, schemes[theme]
        bg_color = {
            "standard": {"classic": "#090c1a", "black": "#000000", "white": "#f2f5fb"},
            "modern": {"classic": "#e7e7e4", "black": "#010101", "white": "#ffffff"},
            "ios26": {"classic": "#2a2433", "black": "#060607", "white": "#e8e8f0"},
        }[theme][scheme]
    attrs = f'data-theme="{look}" data-scheme="{scheme}" data-ios="{palette}"' + (' data-custom="1"' if custom else '')
    boot = json.dumps({"theme": theme, "custom": custom}, ensure_ascii=False)
    html = FRONTEND_HTML.replace('<html lang="ru">', f'<html lang="ru" {attrs}>', 1)
    html = html.replace('window.__BOOT__=null;', f'window.__BOOT__={boot};', 1)

    win_w, win_h = 980, 660
    try:
        scr = webview.screens[0]
        win_w = max(720, min(win_w, int(scr.width * 0.92)))
        win_h = max(480, min(win_h, int(scr.height * 0.85)))
    except Exception:
        pass

    window = webview.create_window(
        "NERKN",
        html=html,
        js_api=api,
        width=win_w,
        height=win_h,
        min_size=(720, 480),
        background_color=bg_color,
        text_select=False,
        hidden=AUTOSTART_LAUNCH,
    )
    app_state.window = window
    window.events.closing += app_state.on_closing

    webview.start(app_state.on_ready, debug=False)

if __name__ == "__main__":
    main()

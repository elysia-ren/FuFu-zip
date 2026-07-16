# -*- coding: utf-8 -*-
"""
FuFu-zip v1.1.0
- 批量解压 · 拖拽 · 取消
- 浅色/深色/随系统主题
"""

import os
import sys
import time
import threading
import string
import json
import base64
import hashlib
import random
import pyzipper
from Cryptodome.Cipher import AES
from Cryptodome.Protocol.KDF import PBKDF2
from Cryptodome.Random import get_random_bytes

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    tk_available = True
except ImportError:
    tk_available = False

_pyzipper = pyzipper
_AES = AES
_PBKDF2 = PBKDF2
_get_random_bytes = get_random_bytes
_base64 = base64
_hashlib = hashlib
_random_mod = random

class SilentLogger:
    def log(self, msg, level="INFO"):
        try:
            print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}")
        except Exception:
            pass

logger = SilentLogger()


# ============================================================
# 密码 / 文件名加密
# ============================================================
class _PyPasswordManager:
    def __init__(self):
        self.chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
        self.password_seed = 293132843413430611711722818101810311111127
        self.password_count = 100
        self.passwords = self._generate_all()

    def _generate_one(self, length=50, index=0):
        try:
            _random_mod.seed(self.password_seed + index)
            pw = ''.join(_random_mod.choice(self.chars) for _ in range(length))
            _random_mod.seed()
            return pw
        except (ValueError, TypeError, OverflowError):
            return _hashlib.sha256(f"{self.password_seed}_{index}".encode()).hexdigest()[:length]

    def _generate_all(self):
        return [self._generate_one(index=i) for i in range(self.password_count)]

    def get_passwords(self):
        return self.passwords.copy()

    def get_password_count(self):
        return self.password_count


class _PyFileNameEncryptor:
    MAGIC = b"ZENC"
    def __init__(self):
        self.encryption_key = _PBKDF2(
            "builtin_file_encryption_key_2025_v9",
            b"fixed_salt_for_file_encryption_2025",
            dkLen=32, count=1111)
        self.block_size = 16

    def _pad(self, d):
        p = self.block_size - len(d) % self.block_size
        return d + bytes([p] * p)

    def _unpad(self, d):
        if not d: return d
        p = d[-1]
        if p < 1 or p > self.block_size: raise ValueError("无效填充")
        if d[-p:] != bytes([p] * p): raise ValueError("无效填充")
        return d[:-p]

    def encrypt_filename(self, name):
        try:
            payload = self._pad(self.MAGIC + name.encode('utf-8'))
            iv = _get_random_bytes(self.block_size)
            ct = _AES.new(self.encryption_key, _AES.MODE_CBC, iv).encrypt(payload)
            b64 = _base64.b64encode(iv + ct).decode('ascii')
            return b64.replace('/', '_').replace('+', '-').replace('=', '') + ".enc"
        except Exception:
            return f"fallback_{_hashlib.sha256(name.encode()).hexdigest()[:16]}.enc"

    def decrypt_filename(self, enc_name):
        try:
            if not enc_name.endswith('.enc'): return enc_name
            s = enc_name[:-4].replace('_', '/').replace('-', '+')
            s += '=' * (-len(s) % 4)
            raw = _base64.b64decode(s)
            if len(raw) < self.block_size * 2: return enc_name
            iv, ct = raw[:self.block_size], raw[self.block_size:]
            pt = self._unpad(_AES.new(self.encryption_key, _AES.MODE_CBC, iv).decrypt(ct))
            if pt[:4] != self.MAGIC: return enc_name
            return pt[4:].decode('utf-8')
        except Exception:
            return enc_name


_use_cython_core = False
try:
    import core as _cython_core; _use_cython_core = True
except ImportError:
    pass

def _create_password_manager():
    if _use_cython_core and hasattr(_cython_core, 'PasswordManager'):
        return _cython_core.PasswordManager()
    return _PyPasswordManager()

def _create_filename_encryptor():
    if _use_cython_core and hasattr(_cython_core, 'FileNameEncryptor'):
        return _cython_core.FileNameEncryptor()
    return _PyFileNameEncryptor()


# ============================================================
# 压缩解压处理器
# ============================================================
class SecureZipHandler:
    def __init__(self, pm):
        self.password_manager = pm
        self.last_password = None
        self.filename_encryptor = _create_filename_encryptor()
        self.current_zip_password = None

    def safe_encode(self, text):
        if not isinstance(text, str): text = str(text)
        for enc in ('utf-8', 'gbk', 'latin-1'):
            try: return text.encode(enc)
            except Exception: continue
        return text.encode('utf-8', 'replace')

    def compress_files(self, sources, output, progress_cb=None, cancel_check=None):
        for p in sources:
            if not os.path.exists(p): return False, "源文件不存在: " + p, None
        out_dir = os.path.dirname(output)
        if out_dir and not os.path.exists(out_dir):
            try: os.makedirs(out_dir)
            except Exception as e: return False, "创建目录失败: " + str(e), None
        pws = self.password_manager.get_passwords()
        pw = _random_mod.choice(pws) if pws else "default_password_fallback"
        self.current_zip_password = self.last_password = pw
        try:
            with _pyzipper.AESZipFile(output, 'w',
                                      compression=_pyzipper.ZIP_DEFLATED,
                                      encryption=_pyzipper.WZ_AES) as zf:
                zf.setpassword(self.safe_encode(pw))
                total = processed = 0
                for src in sources:
                    if os.path.isfile(src): total += 1
                    else:
                        for r, ds, fs in os.walk(src): total += len(fs)
                last_ts = [0]
                def _prog(v):
                    now = time.monotonic()
                    if now - last_ts[0] < 0.1 and v < 100: return
                    last_ts[0] = now
                    if progress_cb: progress_cb(v)
                for src in sources:
                    if os.path.isfile(src):
                        if cancel_check and cancel_check(): return False, "操作已取消", None
                        zf.write(src, arcname=self.filename_encryptor.encrypt_filename(os.path.basename(src)))
                        processed += 1; _prog(int(processed / total * 100))
                        if processed % 10 == 0: time.sleep(0)  # 让出GIL，防止UI卡死
                    else:
                        base = os.path.basename(src)
                        for root, dirs, files in os.walk(src):
                            rel = os.path.relpath(root, src)
                            for f in files:
                                if cancel_check and cancel_check(): return False, "操作已取消", None
                                fp = os.path.join(root, f)
                                orig = os.path.join(base, f) if rel == '.' else os.path.join(base, rel, f)
                                zf.write(fp, arcname=self.filename_encryptor.encrypt_filename(orig))
                                processed += 1; _prog(int(processed / total * 100))
                                if processed % 10 == 0: time.sleep(0)  # 让出GIL，防止UI卡死
                return True, "压缩成功，文件名已加密", pw
        except PermissionError as e: return False, "权限不足: " + str(e), None
        except Exception as e: return False, "压缩失败: " + str(e), None

    def decompress_file(self, zip_path, out_dir, progress_cb=None, cancel_check=None):
        if not os.path.exists(zip_path): return False, "ZIP文件不存在", None
        if not os.path.exists(out_dir):
            try: os.makedirs(out_dir)
            except Exception as e: return False, "创建目录失败: " + str(e), None
        try:
            try:
                with _pyzipper.AESZipFile(zip_path, 'r') as zf:
                    flist = zf.infolist(); fcount = len(flist)
            except Exception as e: return False, "无效ZIP: " + str(e), None
            if fcount == 0: return True, "ZIP为空", None
            pws = self.password_manager.get_passwords()
            matched = None
            for i, pw in enumerate(pws):
                if cancel_check and cancel_check(): return False, "操作已取消", None
                try:
                    with _pyzipper.AESZipFile(zip_path, 'r') as zf:
                        zf.setpassword(self.safe_encode(pw))
                        with zf.open(flist[0]) as f: f.read(1)
                    matched = pw; break
                except RuntimeError as e:
                    err = str(e).lower()
                    if "password" not in err and "incorrect" not in err: pass
                except Exception: pass
            if not matched: return False, "密码不在字典中", None
            try:
                with _pyzipper.AESZipFile(zip_path, 'r') as zf:
                    zf.setpassword(self.safe_encode(matched))
                    extracted = []
                    last_ts = [0]
                    for j, fi in enumerate(flist):
                        if cancel_check and cancel_check(): return False, "操作已取消", None
                        try:
                            fn = self.filename_encryptor.decrypt_filename(fi.filename)
                            op = os.path.join(out_dir, fn)
                            dp = os.path.dirname(op)
                            if dp and not os.path.exists(dp): os.makedirs(dp)
                            with zf.open(fi) as src, open(op, 'wb') as tgt:
                                while True:
                                    if cancel_check and cancel_check(): return False, "操作已取消", None
                                    chunk = src.read(1048576)
                                    if not chunk: break
                                    tgt.write(chunk)
                            extracted.append(op)
                            now = time.monotonic()
                            if now - last_ts[0] >= 0.1 or j == fcount - 1:
                                last_ts[0] = now
                                if progress_cb: progress_cb(int((j + 1) / fcount * 100))
                        except Exception: continue
                    if extracted: return True, "解压成功", matched
                    return True, "部分解压成功", None
            except Exception as e: return False, "解压失败: " + str(e), None
        except Exception as e: return False, "解压失败: " + str(e), None


# ============================================================
# 主题
# ============================================================
THEMES = {
    'light': {
        'BG': '#F5F6FA', 'CARD': '#FFFFFF', 'PRIMARY': '#89CFF0',
        'PRIMARY_HOVER': '#6ABDE6', 'DANGER': '#E74C3C', 'DANGER_HOVER': '#C0392B',
        'TEXT': '#2D3436', 'TEXT_SEC': '#636E72', 'BORDER': '#DFE6E9',
        'SUCCESS': '#00B894', 'TAB_BG': '#E8ECF1', 'HEADER_BG': '#89CFF0',
        'HEADER_FG': '#FFFFFF', 'HEADER_SUB': '#E8F4FD',
        'PROGRESS_TROUGH': '#E8ECF1', 'BTN_SEC_BG': '#FFFFFF',
        'BTN_SEC_HOVER': '#F0F2F5', 'LOG_BG': '#FFFFFF',
    },
    'dark': {
        'BG': '#1A1B2E', 'CARD': '#252641', 'PRIMARY': '#7BB8D4',
        'PRIMARY_HOVER': '#5AA0C4', 'DANGER': '#E74C3C', 'DANGER_HOVER': '#C0392B',
        'TEXT': '#E0E0E0', 'TEXT_SEC': '#8E9AAF', 'BORDER': '#3A3B5C',
        'SUCCESS': '#00B894', 'TAB_BG': '#1E1F36', 'HEADER_BG': '#2A2B4A',
        'HEADER_FG': '#E0E0E0', 'HEADER_SUB': '#8E9AAF',
        'PROGRESS_TROUGH': '#3A3B5C', 'BTN_SEC_BG': '#2D2E4A',
        'BTN_SEC_HOVER': '#3A3B5C', 'LOG_BG': '#1E1F36',
    },
}

def _detect_system_theme():
    """检测 Windows 系统主题"""
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return 'light' if val == 1 else 'dark'
        except Exception:
            pass
    return 'light'

def _get_app_dir():
    """获取应用数据目录（AppData/Roaming/FuFu-zip）"""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:
        base = os.path.join(os.path.expanduser('~'), '.config')
    app_dir = os.path.join(base, 'FuFu-zip')
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

CONFIG_PATH = os.path.join(_get_app_dir(), 'config.json')
DISCLAIMER_PATH = os.path.join(_get_app_dir(), '.disclaimer_accepted')

def _load_theme_pref():
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
            return cfg.get('theme', 'system')
    except Exception:
        return 'system'

def _save_theme_pref(pref):
    try:
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f: cfg = json.load(f)
        cfg['theme'] = pref
        with open(CONFIG_PATH, 'w') as f: json.dump(cfg, f)
    except Exception:
        pass

def _resolve_theme(pref):
    if pref == 'system': return _detect_system_theme()
    return pref if pref in THEMES else 'light'


# ============================================================
# 主窗口
# ============================================================
class ModernMainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("FuFu-zip v1.1.0")
        self.root.geometry("960x680")
        self.root.minsize(780, 520)
        self._cancelled = False

        # 必须在窗口显示前设置 AppUserModelID，否则任务栏图标不生效
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fufuzip.v1.1.0')
            except Exception: pass

        self._set_window_icon()

        self.password_manager = None
        self.zip_handler = None

        # 主题
        self._theme_pref = _load_theme_pref()  # 'light' / 'dark' / 'system'
        self._apply_theme(_resolve_theme(self._theme_pref))

        self._create_styles()
        self._create_widgets()
        self._setup_drag_drop()
        self._add_log("🎉 欢迎使用 FuFu-zip v1.1.0")
        self._add_log("🔒 文件名全加密 · AES-256 · ZENC 魔数校验")
        self._show_disclaimer()

    def _apply_theme(self, name):
        self.T = THEMES.get(name, THEMES['light'])
        self.root.configure(bg=self.T['BG'])

    def _switch_theme(self, pref):
        self._theme_pref = pref
        _save_theme_pref(pref)
        self._apply_theme(_resolve_theme(pref))
        self._create_styles()
        # 记住当前状态
        old_files = list(self.file_list.get(0, tk.END))
        old_zips = list(self.zip_list.get(0, tk.END))
        old_log = self.log_text.get('1.0', tk.END) if self.log_text else ''
        old_output = self.output_path.get()
        old_extract = self.extract_path.get()
        # 重建 UI（销毁所有子组件，包括 ttk）
        for w in self.root.winfo_children():
            w.destroy()
        self._create_widgets()
        # 恢复状态
        for f in old_files: self.file_list.insert(tk.END, f)
        for z in old_zips: self.zip_list.insert(tk.END, z)
        if old_log.strip():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, old_log)
            self.log_text.config(state=tk.DISABLED)
        self.output_path.delete(0, tk.END); self.output_path.insert(0, old_output)
        self.extract_path.delete(0, tk.END); self.extract_path.insert(0, old_extract)
        self._update_file_stats()
        self._add_log(f"🎨 主题已切换: {pref}")

    def _set_window_icon(self):
        """设置图标（延迟 + 定期刷新防止丢失）"""
        # 缓存图标句柄
        self._icon_hicon = None
        self._icon_path = None
        icon_names = ['fufu.ico', 'secure_zip_icon.ico']
        search_dirs = []
        if hasattr(sys, '_MEIPASS'):
            search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.dirname(os.path.abspath(__file__)))
        search_dirs.append(os.getcwd())

        for name in icon_names:
            for base in search_dirs:
                p = os.path.join(base, name)
                if os.path.exists(p):
                    self._icon_path = p
                    break
            if self._icon_path:
                break

        if not self._icon_path:
            return

        # 延迟首次设置
        self.root.after(100, self._apply_icon)
        # 窗口获焦时重新设置
        self.root.bind('<FocusIn>', lambda e: self._apply_icon())

    def _apply_icon(self):
        """应用图标到窗口和任务栏"""
        if not self._icon_path or not os.path.exists(self._icon_path):
            return

        if sys.platform == 'win32':
            try:
                import ctypes
                user32 = ctypes.windll.user32

                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x10
                LR_DEFAULTSIZE = 0x40
                WM_SETICON = 0x0080
                ICON_SMALL = 0
                ICON_BIG = 1

                # 每次都重新加载图标（防止缓存失效）
                hicon = user32.LoadImageW(
                    None, self._icon_path, IMAGE_ICON, 0, 0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE
                )
                if hicon:
                    hwnd = int(self.root.frame(), 16)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                    self._icon_hicon = hicon
                    return
            except Exception:
                pass

        try:
            self.root.iconbitmap(self._icon_path)
        except Exception:
            pass

    def _ensure_handler(self):
        if self.zip_handler is None:
            self._add_log("⏳ 初始化加密模块...")
            self.password_manager = _create_password_manager()
            self.zip_handler = SecureZipHandler(self.password_manager)
            self._add_log("✅ 就绪")

    # ---------- 样式 ----------
    def _create_styles(self):
        T = self.T
        s = ttk.Style()
        try: s.theme_use('clam')
        except Exception: pass
        s.configure('.', background=T['BG'], foreground=T['TEXT'], font=('Microsoft YaHei', 10))
        s.configure('Primary.TButton', background=T['PRIMARY'], foreground='white',
                     borderwidth=0, padding=(18, 8), font=('Microsoft YaHei', 10, 'bold'))
        s.map('Primary.TButton',
               background=[('active', T['PRIMARY_HOVER']), ('disabled', '#B2BEC3')],
               foreground=[('disabled', '#DFE6E9')])
        s.configure('Secondary.TButton', background=T['BTN_SEC_BG'], foreground=T['TEXT'],
                     borderwidth=1, relief='solid', padding=(14, 7), font=('Microsoft YaHei', 9))
        s.map('Secondary.TButton', background=[('active', T['BTN_SEC_HOVER'])],
               bordercolor=[('focus', T['PRIMARY'])])
        s.configure('Danger.TButton', background=T['DANGER'], foreground='white',
                     borderwidth=0, padding=(14, 7), font=('Microsoft YaHei', 9, 'bold'))
        s.map('Danger.TButton',
               background=[('active', T['DANGER_HOVER']), ('disabled', '#B2BEC3')])
        s.configure('TFrame', background=T['BG'])
        s.configure('TLabel', background=T['BG'], foreground=T['TEXT'], font=('Microsoft YaHei', 10))
        s.configure('TEntry', fieldbackground=T['CARD'], foreground=T['TEXT'],
                     borderwidth=1, relief='solid', padding=8, font=('Microsoft YaHei', 10))
        s.map('TEntry', bordercolor=[('focus', T['PRIMARY'])])
        s.configure('TNotebook', background=T['TAB_BG'], borderwidth=0)
        s.configure('TNotebook.Tab', background=T['TAB_BG'], foreground=T['TEXT_SEC'],
                     padding=[20, 10], font=('Microsoft YaHei', 10))
        s.map('TNotebook.Tab',
               background=[('selected', T['CARD']), ('active', T['BTN_SEC_HOVER'])],
               foreground=[('selected', T['PRIMARY']), ('active', T['TEXT'])])
        s.configure('TProgressbar', background=T['PRIMARY'], troughcolor=T['PROGRESS_TROUGH'],
                     borderwidth=0, thickness=6)
        s.configure('TLabelframe', background=T['CARD'], foreground=T['TEXT'], borderwidth=0)
        s.configure('TLabelframe.Label', background=T['CARD'], foreground=T['TEXT_SEC'],
                     font=('Microsoft YaHei', 10, 'bold'))
        s.configure('TCheckbutton', background=T['CARD'], foreground=T['TEXT'], font=('Microsoft YaHei', 10))

    # ---------- 主布局 ----------
    def _create_widgets(self):
        T = self.T
        # 标题栏
        hdr = tk.Frame(self.root, bg=T['HEADER_BG'], height=56)
        hdr.pack(fill=tk.X); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔒  FuFu-zip", bg=T['HEADER_BG'], fg=T['HEADER_FG'],
                 font=('Microsoft YaHei', 16, 'bold')).pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(hdr, text="v1.1.0  ·  AES-256  ·  ZENC", bg=T['HEADER_BG'],
                 fg=T['HEADER_SUB'], font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=10, pady=12)

        # 主题切换按钮
        theme_frame = tk.Frame(hdr, bg=T['HEADER_BG'])
        theme_frame.pack(side=tk.RIGHT, padx=16)
        for label, pref in [("☀️", "light"), ("🌙", "dark"), ("💻", "system")]:
            btn = tk.Button(theme_frame, text=label, bg=T['HEADER_BG'], fg=T['HEADER_FG'],
                            relief='flat', bd=0, font=('Microsoft YaHei', 11), cursor='hand2',
                            activebackground=T['PRIMARY_HOVER'],
                            command=lambda p=pref: self._switch_theme(p))
            btn.pack(side=tk.LEFT, padx=2)
            # 当前选中加下划线
            if pref == self._theme_pref:
                btn.configure(font=('Microsoft YaHei', 11, 'underline'))

        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 16))
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self._create_compress_tab()
        self._create_decompress_tab()
        self._create_log_tab()
        self._create_about_tab()

        # 底部状态栏
        bar = tk.Frame(self.root, bg=T['CARD'], height=32)
        bar.pack(fill=tk.X, side=tk.BOTTOM); bar.pack_propagate(False)
        tk.Frame(bar, bg=T['BORDER'], height=1).pack(fill=tk.X)
        self.status_info = tk.Label(bar, text="✅ 就绪", bg=T['CARD'],
                                    fg=T['TEXT_SEC'], font=('Microsoft YaHei', 9))
        self.status_info.pack(side=tk.RIGHT, padx=16)

    def _card(self, parent, **kw):
        T = self.T
        outer = tk.Frame(parent, bg=T['BORDER'], padx=1, pady=1)
        outer.pack(fill=tk.BOTH, **kw)
        inner = tk.Frame(outer, bg=T['CARD'])
        inner.pack(fill=tk.BOTH, expand=True)
        return inner

    def _card_header(self, parent, text, icon=""):
        T = self.T
        f = tk.Frame(parent, bg=T['CARD']); f.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(f, text=f"{icon}  {text}" if icon else text,
                 bg=T['CARD'], fg=T['TEXT'], font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

    def _input_row(self, parent, label, default="", cmd=None):
        T = self.T
        f = tk.Frame(parent, bg=T['CARD']); f.pack(fill=tk.X, padx=16, pady=8)
        tk.Label(f, text=label, bg=T['CARD'], fg=T['TEXT_SEC'],
                 font=('Microsoft YaHei', 9), width=10, anchor='w').pack(side=tk.LEFT)
        entry = tk.Entry(f, bg=T['CARD'], fg=T['TEXT'], relief='solid', bd=1,
                         font=('Microsoft YaHei', 10), highlightthickness=1,
                         highlightbackground=T['BORDER'], highlightcolor=T['PRIMARY'])
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        if default: entry.insert(0, default)
        if cmd:
            tk.Button(f, text="浏览", bg=T['BTN_SEC_BG'], fg=T['TEXT'], relief='solid', bd=1,
                      font=('Microsoft YaHei', 9), activebackground=T['BTN_SEC_HOVER'],
                      cursor='hand2', command=cmd).pack(side=tk.RIGHT)
        return entry

    def _btn(self, parent, text, command, style='primary', **kw):
        T = self.T
        if style == 'primary':
            bg, fg, hover = T['PRIMARY'], 'white', T['PRIMARY_HOVER']
            font = ('Microsoft YaHei', 10, 'bold')
        elif style == 'danger':
            bg, fg, hover = T['DANGER'], 'white', T['DANGER_HOVER']
            font = ('Microsoft YaHei', 9, 'bold')
        else:
            bg, fg, hover = T['BTN_SEC_BG'], T['TEXT'], T['BTN_SEC_HOVER']
            font = ('Microsoft YaHei', 9)
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                        relief='flat', bd=0, font=font, cursor='hand2',
                        activebackground=hover, activeforeground=fg, padx=16, pady=6)
        btn.pack(**kw)
        btn.bind('<Enter>', lambda e, b=btn, h=hover: b.config(bg=h))
        btn.bind('<Leave>', lambda e, b=btn, c=bg: b.config(bg=c))
        return btn

    def _listbox(self, parent, height=8):
        T = self.T
        f = tk.Frame(parent, bg=T['CARD']); f.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))
        lb = tk.Listbox(f, bg=T['CARD'], fg=T['TEXT'], relief='flat', bd=0,
                        highlightthickness=1, highlightbackground=T['BORDER'],
                        highlightcolor=T['PRIMARY'], selectbackground=T['PRIMARY'],
                        selectforeground='white', font=('Microsoft YaHei', 9),
                        height=height, activestyle='none', selectmode=tk.EXTENDED)
        lb.pack(fill=tk.BOTH, expand=True)
        return lb

    # ---------- 压缩标签页 ----------
    def _create_compress_tab(self):
        T = self.T
        tab = ttk.Frame(self.notebook); self.notebook.add(tab, text="  📦  压缩  ")
        card = self._card(tab, pady=(0, 8))
        self._card_header(card, "选择文件 / 文件夹", "📁")
        row = tk.Frame(card, bg=T['CARD']); row.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn(row, "📄 添加文件", self._add_files, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "📁 添加文件夹", self._add_folder, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "移除选中", self._remove_selected, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "清空", self._clear_list, 'secondary', side=tk.LEFT)
        self.file_list = self._listbox(card)
        self.file_stats = tk.Label(card, text="已添加: 0 项", bg=T['CARD'],
                                   fg=T['TEXT_SEC'], font=('Microsoft YaHei', 9))
        self.file_stats.pack(padx=16, anchor='w')
        card2 = self._card(tab, pady=(0, 8))
        self._card_header(card2, "输出设置", "📤")
        self.output_path = self._input_row(card2, "输出文件", "", self._select_output_file)
        af = tk.Frame(tab, bg=T['BG']); af.pack(fill=tk.X, pady=(4, 0))
        self.compress_btn = self._btn(af, "🚀  开始压缩", self._start_compression,
                                       'primary', side=tk.LEFT, padx=(0, 8))
        self.compress_cancel_btn = self._btn(af, "取消", self._request_cancel, 'danger', side=tk.LEFT)
        self.compress_cancel_btn.pack_forget()
        self.compress_status = tk.Label(af, text="就绪", bg=T['BG'], fg=T['TEXT_SEC'],
                                        font=('Microsoft YaHei', 9))
        self.compress_status.pack(side=tk.LEFT, padx=16)
        self.compress_pf = tk.Frame(tab, bg=T['BG'])
        self.compress_progress = ttk.Progressbar(self.compress_pf, mode='determinate')
        self.compress_progress.pack(fill=tk.X, pady=(8, 0))

    # ---------- 解压标签页 ----------
    def _create_decompress_tab(self):
        T = self.T
        tab = ttk.Frame(self.notebook); self.notebook.add(tab, text="  📤  解压  ")
        card = self._card(tab, pady=(0, 8))
        self._card_header(card, "选择 ZIP 文件", "📦")
        row = tk.Frame(card, bg=T['CARD']); row.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn(row, "📂 添加ZIP", self._add_zip_files, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "移除选中", self._remove_selected_zip, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "清空", self._clear_zip_list, 'secondary', side=tk.LEFT)
        self.zip_list = self._listbox(card, height=5)
        card2 = self._card(tab, pady=(0, 8))
        self._card_header(card2, "输出设置", "📁")
        self.extract_path = self._input_row(card2, "输出目录", "", self._select_extract_dir)
        tk.Label(card2, text="内置100条密码，自动尝试解密 · ZENC 魔数校验",
                 bg=T['CARD'], fg=T['TEXT_SEC'], font=('Microsoft YaHei', 9)
                 ).pack(padx=16, pady=(0, 12), anchor='w')
        af = tk.Frame(tab, bg=T['BG']); af.pack(fill=tk.X, pady=(4, 0))
        self.decompress_btn = self._btn(af, "🚀  开始解压", self._start_decompression,
                                         'primary', side=tk.LEFT, padx=(0, 8))
        self.decompress_cancel_btn = self._btn(af, "取消", self._request_cancel, 'danger', side=tk.LEFT)
        self.decompress_cancel_btn.pack_forget()
        self.decompress_status = tk.Label(af, text="就绪", bg=T['BG'], fg=T['TEXT_SEC'],
                                          font=('Microsoft YaHei', 9))
        self.decompress_status.pack(side=tk.LEFT, padx=16)
        self.decompress_pf = tk.Frame(tab, bg=T['BG'])
        self.decompress_progress = ttk.Progressbar(self.decompress_pf, mode='determinate')
        self.decompress_progress.pack(fill=tk.X, pady=(8, 0))

    # ---------- 日志 ----------
    def _create_log_tab(self):
        T = self.T
        tab = ttk.Frame(self.notebook); self.notebook.add(tab, text="  📝  日志  ")
        card = self._card(tab, pady=(0, 8))
        self._card_header(card, "操作记录", "📊")
        self.log_text = scrolledtext.ScrolledText(card, bg=T['LOG_BG'], fg=T['TEXT'],
                                                  relief='flat', bd=0, highlightthickness=1,
                                                  highlightbackground=T['BORDER'],
                                                  font=('Microsoft YaHei', 9), wrap=tk.WORD,
                                                  state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        row = tk.Frame(card, bg=T['CARD']); row.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._btn(row, "🗑️ 清空", self._clear_log, 'secondary', side=tk.LEFT, padx=(0, 6))
        self._btn(row, "📋 复制", self._copy_log, 'secondary', side=tk.LEFT)

    # ---------- 关于 ----------
    def _create_about_tab(self):
        T = self.T
        tab = ttk.Frame(self.notebook); self.notebook.add(tab, text="  ℹ️  关于  ")
        card = self._card(tab, pady=(0, 8))
        self._card_header(card, "功能特性", "🔐")
        for title, desc in [("文件名全加密", "文件名+扩展名一起加密，统一.enc后缀"),
                            ("ZENC 魔数校验", "密文头部4字节标记，精确识别"),
                            ("AES-256 加密", "AES-256-CBC加密文件名，ZIP内容AES-256"),
                            ("100条密码字典", "内置50位高强度随机密码"),
                            ("批量解压", "支持同时解压多个ZIP文件"),
                            ("深色模式", "浅色/深色/随系统自动切换")]:
            row = tk.Frame(card, bg=T['CARD']); row.pack(fill=tk.X, padx=20, pady=6)
            tk.Label(row, text="•", bg=T['CARD'], fg=T['PRIMARY'],
                     font=('Microsoft YaHei', 12, 'bold'), width=2).pack(side=tk.LEFT, anchor='n')
            tk.Label(row, text=title, bg=T['CARD'], fg=T['TEXT'],
                     font=('Microsoft YaHei', 10, 'bold')).pack(side=tk.LEFT)
            tk.Label(row, text=desc, bg=T['CARD'], fg=T['TEXT_SEC'],
                     font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=(12, 0))
        tk.Frame(card, bg=T['CARD'], height=12).pack()
        card2 = self._card(tab, pady=(0, 8))
        self._card_header(card2, "使用提示", "💡")
        for tip in ["重要文件请做好多重备份", "确保使用同一版本进行压缩和解压"]:
            tk.Label(card2, text=f"  ▸  {tip}", bg=T['CARD'], fg=T['TEXT_SEC'],
                     font=('Microsoft YaHei', 9)).pack(fill=tk.X, padx=20, pady=4)
        tk.Frame(card2, bg=T['CARD'], height=8).pack()

    # ---------- 拖拽 ----------
    def _setup_drag_drop(self):
        try:
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop)
            self._add_log("✅ 拖拽已启用")
        except ImportError:
            self._add_log("💡 拖拽不可用，请使用按钮添加文件")

    def _on_drop(self, files):
        if isinstance(files, (list, tuple)):
            for f in files:
                if isinstance(f, bytes):
                    # Windows 拖拽用系统编码（中文系统为 GBK）
                    for enc in ('gbk', 'utf-8', 'latin-1'):
                        try: f = f.decode(enc); break
                        except Exception: continue
                    else:
                        f = f.decode('utf-8', errors='replace')
                f = f.strip()
                if f not in self.file_list.get(0, tk.END):
                    self.file_list.insert(tk.END, f)
                if f.lower().endswith('.zip') and f not in self.zip_list.get(0, tk.END):
                    self.zip_list.insert(tk.END, f)
            self._update_file_stats()

    def _request_cancel(self): self._cancelled = True; self._add_log("⛔ 取消中...")
    def _is_cancelled(self): return self._cancelled
    def _reset_cancel(self): self._cancelled = False

    # ---------- 免责声明 ----------
    def _show_disclaimer(self):
        dp = DISCLAIMER_PATH
        if os.path.exists(dp): return
        def _do():
            T = self.T
            dlg = tk.Toplevel(self.root); dlg.title("免责声明")
            dlg.geometry("460x300"); dlg.resizable(False, False)
            dlg.transient(self.root); dlg.grab_set(); dlg.configure(bg=T['CARD'])
            tk.Label(dlg, text="【免责声明】\n\nFuFu-zip 仅供个人学习与隐私保护使用。\n\n"
                     "• 请勿用于任何非法用途\n• 请遵守当地法律法规\n"
                     "• 开发者不对任何损失承担责任\n• 使用即表示同意",
                     bg=T['CARD'], fg=T['TEXT'], font=('Microsoft YaHei', 10),
                     wraplength=420, justify='left').pack(padx=20, pady=20)
            sv = tk.BooleanVar(value=False)
            tk.Checkbutton(dlg, text="不再显示", variable=sv, bg=T['CARD'], fg=T['TEXT_SEC'],
                           font=('Microsoft YaHei', 9), activebackground=T['CARD']).pack(padx=20, anchor='w')
            def _ok():
                if sv.get():
                    try:
                        with open(dp, 'w') as f: f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
                    except Exception: pass
                dlg.destroy()
            self._btn(dlg, "我已阅读并同意", _ok, 'primary', pady=16)
            dlg.protocol("WM_DELETE_WINDOW", _ok)
        if threading.current_thread() is threading.main_thread(): _do()
        else: self.root.after(0, _do)

    # ---------- 线程安全 UI ----------
    def _add_log(self, msg):
        def _do():
            try:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
                self.log_text.see(tk.END); self.log_text.config(state=tk.DISABLED)
                self.status_info.config(text=msg[:40])
                self.root.update_idletasks()  # 立即刷新UI防止卡死
            except Exception: pass
        if threading.current_thread() is threading.main_thread(): _do()
        else:
            try: self.root.after(0, _do)
            except Exception: pass

    def _update_progress(self, bar, label, v, text):
        def _do(): bar['value'] = v; label.config(text=text)
        if threading.current_thread() is threading.main_thread(): _do()
        else: self.root.after(0, _do)

    def _show_error(self, title, msg):
        def _do(): messagebox.showerror(title, msg) if tk_available else print(f"错误: {msg}")
        if threading.current_thread() is threading.main_thread(): _do()
        else: self.root.after(0, _do)

    def _set_btn_state(self, btn, state):
        def _do(): btn.config(state=state)
        if threading.current_thread() is threading.main_thread(): _do()
        else: self.root.after(0, _do)

    def _play_done_sound(self):
        """完成提示音"""
        if sys.platform == 'win32':
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception: pass

    def _open_output_folder(self, path):
        """打开输出目录"""
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder): return
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    # ---------- 文件操作 ----------
    def _add_files(self):
        files = filedialog.askopenfilenames(title="选择文件", filetypes=[("所有文件", "*.*")])
        if files:
            for f in files:
                if f not in self.file_list.get(0, tk.END): self.file_list.insert(tk.END, f)
            self._update_file_stats()
            self._update_output_path()

    def _add_folder(self):
        d = filedialog.askdirectory(title="选择文件夹")
        if d and d not in self.file_list.get(0, tk.END):
            self.file_list.insert(tk.END, d); self._update_file_stats()
            self._update_output_path()

    def _remove_selected(self):
        for i in reversed(self.file_list.curselection()): self.file_list.delete(i)
        self._update_file_stats()

    def _clear_list(self): self.file_list.delete(0, tk.END); self._update_file_stats()

    def _update_file_stats(self):
        self.file_stats.config(text=f"已添加: {self.file_list.size()} 项")

    def _update_output_path(self):
        """根据已添加的文件自动更新默认输出路径（参考7-Zip）"""
        items = self.file_list.get(0, tk.END)
        if not items:
            return
        first = items[0]
        if os.path.isfile(first):
            # 单文件：同目录下 同名.zip
            out_dir = os.path.dirname(first)
            out_name = os.path.splitext(os.path.basename(first))[0] + '.zip'
        else:
            # 文件夹：上级目录下 文件夹名.zip
            out_dir = os.path.dirname(first)
            out_name = os.path.basename(first) + '.zip'
        out_path = os.path.join(out_dir, out_name)
        self.output_path.delete(0, tk.END)
        self.output_path.insert(0, out_path)

    def _update_extract_path(self):
        """根据选择的ZIP自动更新默认解压路径"""
        zips = self.zip_list.get(0, tk.END)
        if not zips:
            return
        first = zips[0]
        if os.path.isfile(first):
            # ZIP所在目录
            out_dir = os.path.dirname(first)
        else:
            out_dir = os.path.dirname(first)
        self.extract_path.delete(0, tk.END)
        self.extract_path.insert(0, out_dir)

    def _select_output_file(self):
        o = filedialog.asksaveasfilename(defaultextension=".zip",
                                          filetypes=[("ZIP", "*.zip"), ("所有", "*.*")])
        if o: self.output_path.delete(0, tk.END); self.output_path.insert(0, o)

    def _add_zip_files(self):
        files = filedialog.askopenfilenames(filetypes=[("ZIP", "*.zip"), ("所有", "*.*")])
        if files:
            for f in files:
                if f not in self.zip_list.get(0, tk.END): self.zip_list.insert(tk.END, f)
            self._update_extract_path()

    def _remove_selected_zip(self):
        for i in reversed(self.zip_list.curselection()): self.zip_list.delete(i)

    def _clear_zip_list(self): self.zip_list.delete(0, tk.END)

    def _select_extract_dir(self):
        d = filedialog.askdirectory(title="选择解压目录")
        if d: self.extract_path.delete(0, tk.END); self.extract_path.insert(0, d)

    # ---------- 压缩 ----------
    def _start_compression(self):
        files = self.file_list.get(0, tk.END)
        output = self.output_path.get()
        if not files: self._show_error("错误", "请先添加文件"); return
        if not output: self._show_error("错误", "请选择输出文件"); return
        self._reset_cancel()
        self._set_btn_state(self.compress_btn, tk.DISABLED)
        self.compress_cancel_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.compress_status.config(text="压缩中...")
        self.compress_pf.pack(fill=tk.X, pady=(8, 0))
        self.compress_progress['value'] = 0
        def _prog(v): self._update_progress(self.compress_progress, self.compress_status, v, f"压缩中 {v}%")
        def _run():
            try:
                self._ensure_handler()
                ok, msg, pw = self.zip_handler.compress_files(files, output, _prog, self._is_cancelled)
                self._update_progress(self.compress_progress, self.compress_status, 100,
                                      "✅ 完成" if ok else "❌ 失败")
                if ok:
                    self._add_log(f"🎉 {msg}")
                    try: self._add_log(f"📊 {self._format_size(os.path.getsize(output))}")
                    except Exception: pass
                    self._play_done_sound()
                    # 弹出打开目录按钮
                    self.root.after(0, lambda: self._show_open_btn(output, 'compress'))
                else:
                    self._add_log(f"{'⚠️' if '取消' in msg else '❌'} {msg}")
                    if "取消" not in msg: self._show_error("失败", msg)
            except Exception as e:
                self._add_log(f"❌ {e}"); self._show_error("异常", str(e))
            finally:
                self._set_btn_state(self.compress_btn, tk.NORMAL)
                self.root.after(0, self.compress_cancel_btn.pack_forget)
        threading.Thread(target=_run, daemon=True).start()

    def _show_open_btn(self, path, which):
        """在操作栏显示「打开目录」按钮"""
        try:
            T = self.T
            if which == 'compress':
                parent = self.compress_status.master
            else:
                parent = self.decompress_status.master
            for w in parent.winfo_children():
                if getattr(w, '_open_btn', False): w.destroy()
            btn = tk.Button(parent, text="📂 打开目录", bg=T['BTN_SEC_BG'], fg=T['TEXT'],
                            relief='flat', bd=0, font=('Microsoft YaHei', 9), cursor='hand2',
                            activebackground=T['BTN_SEC_HOVER'],
                            command=lambda: self._open_output_folder(path))
            btn._open_btn = True
            btn.pack(side=tk.LEFT, padx=8)
            btn.bind('<Enter>', lambda e: btn.config(bg=T['BTN_SEC_HOVER']))
            btn.bind('<Leave>', lambda e: btn.config(bg=T['BTN_SEC_BG']))
        except Exception: pass

    # ---------- 解压 ----------
    def _start_decompression(self):
        zips = self.zip_list.get(0, tk.END)
        out = self.extract_path.get()
        if not zips: self._show_error("错误", "请先添加ZIP"); return
        if not out: self._show_error("错误", "请选择输出目录"); return
        self._reset_cancel()
        self._set_btn_state(self.decompress_btn, tk.DISABLED)
        self.decompress_cancel_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.decompress_status.config(text="解压中...")
        self.decompress_pf.pack(fill=tk.X, pady=(8, 0))
        self.decompress_progress['value'] = 0
        def _prog(v): self._update_progress(self.decompress_progress, self.decompress_status, v, f"解压中 {v}%")
        def _run():
            ok_c = fail_c = 0; total = len(zips); last_output = None
            for idx, zf in enumerate(zips):
                if self._is_cancelled(): self._add_log("⛔ 已取消"); break
                self._add_log(f"📦 [{idx+1}/{total}] {os.path.basename(zf)}")
                od = os.path.join(out, os.path.splitext(os.path.basename(zf))[0]) if total > 1 else out
                last_output = od
                try:
                    self._ensure_handler()
                    ok, msg, _ = self.zip_handler.decompress_file(zf, od, _prog, self._is_cancelled)
                    if ok: ok_c += 1; self._add_log(f"  ✅ {msg}")
                    else: fail_c += 1; self._add_log(f"  {'⚠️' if '取消' in msg else '❌'} {msg}")
                except Exception as e:
                    fail_c += 1; self._add_log(f"  ❌ {e}")
            self._update_progress(self.decompress_progress, self.decompress_status, 100, "✅ 完成")
            self._add_log(f"📊 完成: 成功{ok_c} 失败{fail_c} 共{total}")
            self._play_done_sound()
            if last_output:
                self.root.after(0, lambda: self._show_open_btn(last_output, 'decompress'))
            self._set_btn_state(self.decompress_btn, tk.NORMAL)
            self.root.after(0, self.decompress_cancel_btn.pack_forget)
        threading.Thread(target=_run, daemon=True).start()

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL); self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _copy_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.root.clipboard_clear(); self.root.clipboard_append(self.log_text.get(1.0, tk.END))
        self.log_text.config(state=tk.DISABLED); self._add_log("📋 已复制")

    @staticmethod
    def _format_size(s):
        for u in ['B', 'KB', 'MB', 'GB', 'TB']:
            if s < 1024: return f"{s:.2f} {u}"
            s /= 1024
        return f"{s:.2f} PB"


def main():
    if not tk_available:
        print("错误: Tkinter不可用"); return
    root = tk.Tk()
    ModernMainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
文件压缩解压工具 - 安全增强版 (v1.0.0)
- ZENC魔数 + .enc统一后缀，完整隐藏文件类型
- 移除cp437编码，直接使用UTF-8 Base64安全文件名
- 子线程UI更新通过root.after调度到主线程
- 可选Cython编译核心模块防反编译
- 启动时依赖检查，友好错误提示
"""

import os
import random
import string
import time
import threading
import sys
import ctypes
import traceback
import platform
import base64
import hashlib

# ============================================================
# 依赖检查
# ============================================================
_missing_deps = []

try:
    import pyzipper
except ImportError:
    _missing_deps.append(("pyzipper", "pip install pyzipper"))

try:
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Random import get_random_bytes
except ImportError:
    _missing_deps.append(("pycryptodome", "pip install pycryptodome"))

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    from tkinter.ttk import Style
    tk_available = True
except ImportError:
    tk_available = False
    _missing_deps.append(("tkinter", "请安装包含Tkinter的Python版本"))

# 依赖检查结果保存，main()启动时再判断是否退出
# 允许 import 时不退出（测试脚本可跳过tkinter）

# ============================================================
# 尝试导入 Cython 编译的核心模块（优先使用二进制版本）
# ============================================================
_use_cython_core = False
try:
    import core as _cython_core
    _use_cython_core = True
except ImportError:
    pass

# ============================================================
# 日志器
# ============================================================
class SilentLogger:
    """静默日志器 - 只输出到控制台"""
    def log(self, message, level="INFO"):
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] [{level}] {message}")
        except:
            pass

logger = SilentLogger()

# ============================================================
# 密码管理器（内置纯Python实现，作为Cython模块的fallback）
# ============================================================
class _PyPasswordManager:
    """
    密码字典生成器
    注意：此类的Cython编译版本位于 core.pyx，安全性更高。
    当 core 可用时自动使用编译版本。
    """
    def __init__(self):
        self.chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
        self.password_seed = 0  # TODO: 替换为你自己的种子
        self.password_count = 100
        self.passwords = self._generate_all()

    def _generate_one(self, length=50, index=0):
        try:
            random.seed(self.password_seed + index)
            pw = ''.join(random.choice(self.chars) for _ in range(length))
            random.seed()
            return pw
        except:
            return "fallback_" + str(index).zfill(3) + "_" + "x" * 40

    def _generate_all(self):
        return [self._generate_one(index=i) for i in range(self.password_count)]

    def get_passwords(self):
        return self.passwords.copy()

    def get_password_count(self):
        return self.password_count

# ============================================================
# 文件名加密器（内置纯Python实现，作为Cython模块的fallback）
# ============================================================
class _PyFileNameEncryptor:
    """
    文件名全名加密器（含扩展名）
    - 加密输入：完整文件名UTF-8字节
    - 密文格式：ZENC(4B) + IV(16B) + AES-CBC密文 → Base64 → .enc后缀
    - 解密校验：ZENC魔数验证，非本程序加密的文件直接跳过

    注意：此类的Cython编译版本位于 core.pyx，安全性更高。
    当 core 可用时自动使用编译版本。
    """
    MAGIC = b"ZENC"  # 4字节魔数

    def __init__(self):
        self.master_password = "YOUR_SECRET_KEY_HERE"  # TODO: 替换
        self.salt = b"YOUR_SECRET_SALT_HERE"  # TODO: 替换
        self.iterations = 100000
        self.key_size = 32
        self.block_size = 16
        self.encryption_key = PBKDF2(self.master_password, self.salt,
                                     dkLen=self.key_size, count=self.iterations)

    def _pad(self, data):
        padding = self.block_size - len(data) % self.block_size
        return data + bytes([padding] * padding)

    def _unpad(self, data):
        if not data:
            return data
        padding = data[-1]
        if padding < 1 or padding > self.block_size:
            raise ValueError("无效的填充")
        return data[:-padding]

    def encrypt_filename(self, original_filename):
        """
        加密完整文件名（含扩展名）
        返回：Base64字符串.enc（如 'aBcDeFgH...xYz.enc'）
        """
        try:
            data = original_filename.encode('utf-8')
            # 魔数 + 原始文件名
            payload = self.MAGIC + data
            payload = self._pad(payload)

            iv = get_random_bytes(self.block_size)
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            encrypted = cipher.encrypt(payload)

            combined = iv + encrypted
            b64 = base64.b64encode(combined).decode('ascii')
            # 替换URL不安全字符，确保ZIP文件名兼容
            safe = b64.replace('/', '_').replace('+', '-').replace('=', '')
            return safe + ".enc"
        except Exception as e:
            logger.log(f"文件名加密失败: {e}", "ERROR")
            # fallback: 用SHA256哈希
            h = hashlib.sha256(original_filename.encode('utf-8')).hexdigest()[:16]
            return f"fallback_{h}.enc"

    def decrypt_filename(self, encrypted_filename):
        """
        解密文件名
        输入：Base64字符串.enc
        返回：原始完整文件名（含扩展名）
        """
        try:
            name = encrypted_filename
            # 去掉.enc后缀
            if name.endswith('.enc'):
                name = name[:-4]
            else:
                # 不是.enc文件，原样返回
                return encrypted_filename

            # 恢复Base64字符
            name = name.replace('_', '/').replace('-', '+')
            # 补齐padding
            pad_needed = len(name) % 4
            if pad_needed:
                name += '=' * (4 - pad_needed)

            decoded = base64.b64decode(name)

            # 至少需要 IV(16) + 最小密文(16) + 魔数(4) + 填充
            if len(decoded) < self.block_size * 2:
                return encrypted_filename

            iv = decoded[:self.block_size]
            encrypted = decoded[self.block_size:]

            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(encrypted)
            unpadded = self._unpad(decrypted)

            # 校验ZENC魔数
            if unpadded[:4] != self.MAGIC:
                # 非本程序加密的文件，原样返回
                return encrypted_filename

            original = unpadded[4:].decode('utf-8')
            return original
        except Exception as e:
            logger.log(f"文件名解密失败: {e}", "ERROR")
            return encrypted_filename

# ============================================================
# 统一接口：优先Cython，fallback纯Python
# ============================================================
def _create_password_manager():
    if _use_cython_core and hasattr(_cython_core, 'PasswordManager'):
        logger.log("使用Cython编译的核心模块(PasswordManager)")
        return _cython_core.PasswordManager()
    logger.log("使用内置纯Python密码管理器")
    return _PyPasswordManager()

def _create_filename_encryptor():
    if _use_cython_core and hasattr(_cython_core, 'FileNameEncryptor'):
        logger.log("使用Cython编译的核心模块(FileNameEncryptor)")
        return _cython_core.FileNameEncryptor()
    logger.log("使用内置纯Python文件名加密器")
    return _PyFileNameEncryptor()

# ============================================================
# 安全压缩解压处理器
# ============================================================
class SecureZipHandler:
    """安全压缩解压处理器"""
    def __init__(self, password_manager):
        self.password_manager = password_manager
        self.last_password = None
        self.filename_encryptor = _create_filename_encryptor()
        self.current_zip_password = None

    def safe_encode(self, text):
        """安全编码文本"""
        if not isinstance(text, str):
            text = str(text)
        for enc in ('utf-8', 'gbk', 'latin-1'):
            try:
                return text.encode(enc)
            except:
                continue
        return text.encode('utf-8', 'replace')

    def compress_files(self, source_paths, output_path, progress_callback=None):
        """
        压缩文件
        - 文件名经加密后为纯ASCII Base64字符串 + .enc后缀
        - pyzipper自动以UTF-8存储，无需手动cp437编码
        - ZIP内容使用AES-256加密
        """
        for path in source_paths:
            if not os.path.exists(path):
                return False, "源文件不存在: " + str(path)

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                return False, "创建输出目录失败: " + str(e)

        passwords = self.password_manager.get_passwords()
        if passwords:
            password = random.choice(passwords)
            self.current_zip_password = password
            self.last_password = password
        else:
            password = "default_password_fallback"
            self.current_zip_password = password

        try:
            with pyzipper.AESZipFile(output_path, 'w',
                                     compression=pyzipper.ZIP_DEFLATED,
                                     encryption=pyzipper.WZ_AES) as zipf:
                zipf.setpassword(self.safe_encode(password))

                # 计算总文件数
                total_files = 0
                for path in source_paths:
                    if os.path.isfile(path):
                        total_files += 1
                    else:
                        for root, dirs, files in os.walk(path):
                            total_files += len(files)

                processed = 0
                for path in source_paths:
                    if os.path.isfile(path):
                        # 加密完整文件名（含扩展名）
                        arcname = self.filename_encryptor.encrypt_filename(
                            os.path.basename(path))
                        zipf.write(path, arcname=arcname)
                        processed += 1
                        if progress_callback:
                            progress_callback(int(processed / total_files * 100))
                    else:
                        base_name = os.path.basename(path)
                        for root, dirs, files in os.walk(path):
                            rel_path = os.path.relpath(root, path)
                            for file in files:
                                file_path = os.path.join(root, file)
                                if rel_path == '.':
                                    original_filename = os.path.join(base_name, file)
                                else:
                                    original_filename = os.path.join(base_name, rel_path, file)
                                # 加密完整相对路径
                                arcname = self.filename_encryptor.encrypt_filename(
                                    original_filename)
                                zipf.write(file_path, arcname=arcname)
                                processed += 1
                                if progress_callback:
                                    progress_callback(int(processed / total_files * 100))

                logger.log(f"压缩完成: {output_path}")
                return True, "压缩成功，文件名已加密", password

        except PermissionError as e:
            return False, "权限不足: " + str(e)
        except Exception as e:
            logger.log(f"压缩失败: {e}", "ERROR")
            return False, "压缩失败: " + str(e)

    def decompress_file(self, zip_path, output_dir, progress_callback=None):
        """
        解压文件
        - 先逐个密码尝试读取第一个文件来验证密码
        - 密码匹配后再集中解压全部文件（进度条仅覆盖解压阶段）
        - 文件名通过ZENC魔数校验后解密
        - 非本程序加密的文件保持原名不解密
        """
        if not os.path.exists(zip_path):
            return False, "ZIP文件不存在"

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                return False, "创建输出目录失败: " + str(e)

        try:
            # 读取文件列表
            try:
                with pyzipper.AESZipFile(zip_path, 'r') as zipf:
                    file_list = zipf.infolist()
                    file_count = len(file_list)
                    logger.log(f"ZIP包含 {file_count} 个文件")
            except Exception as e:
                return False, "无效的ZIP文件: " + str(e)

            if file_count == 0:
                return True, "ZIP文件为空", None

            passwords = self.password_manager.get_passwords()
            total_passwords = len(passwords)

            # ---- 阶段1：验证密码（读取第一个文件的一个字节） ----
            matched_password = None
            for i, password in enumerate(passwords):
                try:
                    with pyzipper.AESZipFile(zip_path, 'r') as zipf:
                        zipf.setpassword(self.safe_encode(password))
                        with zipf.open(file_list[0]) as f:
                            f.read(1)  # 读1字节验证密码
                    matched_password = password
                    logger.log(f"密码 #{i+1} 验证成功")
                    break
                except RuntimeError as e:
                    err = str(e).lower()
                    if "password" in err or "incorrect" in err:
                        continue
                    else:
                        logger.log(f"运行时错误: {e}", "ERROR")
                except Exception as e:
                    logger.log(f"尝试密码 #{i+1} 出错: {e}", "ERROR")

            if matched_password is None:
                return False, "解压失败，密码不在内置字典中", None

            # ---- 阶段2：用已验证的密码解压全部文件 ----
            try:
                with pyzipper.AESZipFile(zip_path, 'r') as zipf:
                    zipf.setpassword(self.safe_encode(matched_password))

                    extracted_files = []
                    for j, file_info in enumerate(file_list):
                        try:
                            encrypted_name = file_info.filename
                            filename = self.filename_encryptor.decrypt_filename(encrypted_name)

                            output_path = os.path.join(output_dir, filename)
                            dir_path = os.path.dirname(output_path)
                            if dir_path and not os.path.exists(dir_path):
                                os.makedirs(dir_path)

                            with zipf.open(file_info) as source, \
                                 open(output_path, 'wb') as target:
                                while True:
                                    chunk = source.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    target.write(chunk)

                            extracted_files.append(output_path)

                            if progress_callback:
                                progress_callback(int((j + 1) / file_count * 100))

                        except Exception as e:
                            logger.log(f"处理文件 {file_info.filename} 失败: {e}", "ERROR")
                            continue

                    if extracted_files:
                        logger.log(f"成功提取 {len(extracted_files)} 个文件")
                        return True, "解压成功，文件名已解密", matched_password
                    else:
                        return True, "部分解压成功，但密码验证异常", None

            except Exception as e:
                logger.log(f"解压阶段出错: {e}", "ERROR")
                return False, "解压失败: " + str(e)

        except Exception as e:
            logger.log(f"解压严重错误: {e}", "ERROR")
            return False, "解压失败: " + str(e)

# ============================================================
# 现代化主窗口
# ============================================================
class ModernMainWindow:
    """现代化主窗口"""
    def __init__(self, root):
        self.root = root
        self.root.title("FuFu-zip - 文件压缩解压工具 v1.0.0")
        self.root.geometry("1000x750")
        self.root.minsize(800, 550)

        try:
            self.root.iconbitmap(default='secure_zip_icon.ico')
        except:
            pass

        try:
            self.password_manager = _create_password_manager()
            self.zip_handler = SecureZipHandler(self.password_manager)
        except Exception as e:
            self._show_error("程序初始化失败", str(e))
            self.root.quit()
            return

        self._create_style()
        self._create_widgets()
        self._check_system()
        self._add_log("🎉 欢迎使用 FuFu-zip")
        self._add_log("🔒 文件名+扩展名全加密，.enc统一后缀")
        self._add_log("🛡️ ZENC魔数校验，防误识别")
        if _use_cython_core:
            self._add_log("✅ 核心模块已编译（Cython二进制保护）")
        else:
            self._add_log("⚠️ 核心模块为纯Python（建议编译为Cython）")
        self._show_disclaimer()

    def _create_style(self):
        self.style = Style()
        try:
            self.style.theme_use('clam')
        except:
            pass

        self.colors = {
            'primary': '#2E86AB', 'secondary': '#A23B72',
            'accent': '#F18F01', 'success': '#C73E1D',
            'background': '#F8F9FA', 'card': '#FFFFFF',
            'text': '#333333', 'text_light': '#666666',
            'border': '#E0E0E0'
        }

        self.style.configure('Modern.TButton',
                             background=self.colors['primary'], foreground='white',
                             borderwidth=0, padding=8,
                             font=('Microsoft YaHei', 10, 'bold'))
        self.style.map('Modern.TButton',
                       background=[('active', self.colors['secondary'])],
                       foreground=[('active', 'white')])
        self.style.configure('Modern.TNotebook',
                             background=self.colors['background'], borderwidth=0)
        self.style.configure('Modern.TNotebook.Tab',
                             background=self.colors['card'], foreground=self.colors['text'],
                             padding=[15, 8], font=('Microsoft YaHei', 11), borderwidth=0)
        self.style.map('Modern.TNotebook.Tab',
                       background=[('selected', self.colors['primary']),
                                   ('active', self.colors['accent'])],
                       foreground=[('selected', 'white'), ('active', 'white')])
        self.style.configure('Modern.TFrame', background=self.colors['background'])
        self.style.configure('Modern.TLabel',
                             background=self.colors['background'],
                             foreground=self.colors['text'],
                             font=('Microsoft YaHei', 10))
        self.style.configure('Modern.TEntry',
                             background=self.colors['card'], foreground=self.colors['text'],
                             borderwidth=1, relief='solid',
                             fieldbackground=self.colors['card'], padding=6,
                             font=('Microsoft YaHei', 10))
        self.style.configure('Modern.Horizontal.TProgressbar',
                             background=self.colors['primary'], borderwidth=0, relief='solid')
        self.style.configure('Modern.TLabelframe',
                             background=self.colors['background'], foreground=self.colors['text'],
                             borderwidth=1, relief='solid', bordercolor=self.colors['border'])
        self.style.configure('Modern.TLabelframe.Label',
                             background=self.colors['background'], foreground=self.colors['text'],
                             font=('Microsoft YaHei', 11, 'bold'))

    def _check_system(self):
        try:
            if sys.platform.startswith('win32'):
                if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                    self._show_warning("权限提示", "建议以管理员身份运行以避免权限问题")
        except:
            pass

    def _show_disclaimer(self):
        """显示免责声明（首次启动）"""
        # 标记文件放在用户主目录，PyInstaller --onefile打包后临时目录会变
        disclaimer_path = os.path.join(os.path.expanduser('~'),
                                       '.securezip_disclaimer_accepted')
        if os.path.exists(disclaimer_path):
            return

        disclaimer_text = (
            "【免责声明】\n\n"
            "FuFu-zip 仅供个人学习与隐私保护使用。\n\n"
            "• 请勿用于任何非法用途\n"
            "• 请遵守当地法律法规\n"
            "• 开发者不对因使用本软件造成的任何损失承担责任\n"
            "• 使用本软件即表示您已阅读并同意本声明\n"
        )

        def _do():
            if not tk_available:
                return
            dlg = tk.Toplevel(self.root)
            dlg.title("免责声明")
            dlg.geometry("500x320")
            dlg.resizable(False, False)
            dlg.transient(self.root)
            dlg.grab_set()

            ttk.Label(dlg, text=disclaimer_text,
                      font=('Microsoft YaHei', 10),
                      wraplength=460, justify='left').pack(padx=20, pady=15)

            skip_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(dlg, text="不再显示此声明",
                            variable=skip_var).pack(padx=20, anchor='w')

            def _accept():
                if skip_var.get():
                    try:
                        with open(disclaimer_path, 'w') as f:
                            f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
                    except:
                        pass
                dlg.destroy()

            ttk.Button(dlg, text="我已阅读并同意", command=_accept,
                       style='Modern.TButton').pack(pady=15)

            dlg.protocol("WM_DELETE_WINDOW", _accept)

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def _create_widgets(self):
        self.root.config(bg=self.colors['background'])
        self.main_frame = ttk.Frame(self.root, style='Modern.TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.notebook = ttk.Notebook(self.main_frame, style='Modern.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._create_compress_tab()
        self._create_decompress_tab()
        self._create_log_tab()
        self._create_security_tab()
        self._create_status_bar()

    # ---------- 压缩标签页 ----------
    def _create_compress_tab(self):
        tab = ttk.Frame(self.notebook, style='Modern.TFrame')
        self.notebook.add(tab, text="📦 压缩文件")

        file_frame = ttk.LabelFrame(tab, text="📁 选择文件/文件夹", style='Modern.TLabelframe')
        file_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        list_frame = ttk.Frame(file_frame, style='Modern.TFrame')
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.file_list = tk.Listbox(list_frame,
                                    bg=self.colors['card'], fg=self.colors['text'],
                                    bd=1, relief='solid',
                                    highlightbackground=self.colors['primary'],
                                    highlightthickness=1,
                                    selectbackground=self.colors['primary'],
                                    selectforeground='white',
                                    font=('Microsoft YaHei', 10), height=10)
        self.file_list.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(file_frame, style='Modern.TFrame')
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        for text, cmd in [("📄 添加文件", self._add_files),
                          ("📁 添加文件夹", self._add_folder),
                          ("❌ 移除选中", self._remove_selected),
                          ("🗑️ 清空列表", self._clear_list)]:
            ttk.Button(btn_frame, text=text, command=cmd, style='Modern.TButton').pack(fill=tk.X, pady=5, padx=5)

        output_frame = ttk.LabelFrame(tab, text="📤 输出设置", style='Modern.TLabelframe')
        output_frame.pack(fill=tk.X, padx=15, pady=10)

        path_frame = ttk.Frame(output_frame, style='Modern.TFrame')
        path_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(path_frame, text="输出文件:", style='Modern.TLabel').pack(side=tk.LEFT, padx=5, pady=5)
        self.output_path = ttk.Entry(path_frame, style='Modern.TEntry')
        self.output_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=5)
        self.output_path.insert(0, os.path.join(os.path.expanduser("~"), "encrypted.zip"))
        ttk.Button(path_frame, text="📂 浏览", command=self._select_output_file, style='Modern.TButton').pack(side=tk.LEFT, padx=5, pady=5)

        self.file_stats = ttk.Label(output_frame, text="📊 已添加: 0个文件/文件夹", style='Modern.TLabel')
        self.file_stats.pack(padx=10, pady=5)

        progress_frame = ttk.Frame(tab, style='Modern.TFrame')
        progress_frame.pack(fill=tk.X, padx=15, pady=10)
        self.compress_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL,
                                                  mode='determinate',
                                                  style='Modern.Horizontal.TProgressbar')
        self.compress_progress.pack(fill=tk.X, expand=True, padx=10, pady=5)

        status_frame = ttk.Frame(progress_frame, style='Modern.TFrame')
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        self.compress_status = ttk.Label(status_frame, text="✅ 准备就绪", style='Modern.TLabel')
        self.compress_status.pack(side=tk.LEFT, padx=10)
        self.compress_btn = ttk.Button(status_frame, text="🚀 开始压缩",
                                        command=self._start_compression, style='Modern.TButton')
        self.compress_btn.pack(side=tk.RIGHT, padx=10)

    # ---------- 解压标签页 ----------
    def _create_decompress_tab(self):
        tab = ttk.Frame(self.notebook, style='Modern.TFrame')
        self.notebook.add(tab, text="📤 解压文件")

        zip_frame = ttk.LabelFrame(tab, text="📦 选择ZIP文件", style='Modern.TLabelframe')
        zip_frame.pack(fill=tk.X, padx=15, pady=15)
        zip_path_frame = ttk.Frame(zip_frame, style='Modern.TFrame')
        zip_path_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(zip_path_frame, text="ZIP文件:", style='Modern.TLabel').pack(side=tk.LEFT, padx=5, pady=5)
        self.zip_path = ttk.Entry(zip_path_frame, style='Modern.TEntry')
        self.zip_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=5)
        ttk.Button(zip_path_frame, text="📂 浏览", command=self._select_zip_file, style='Modern.TButton').pack(side=tk.LEFT, padx=5, pady=5)

        extract_frame = ttk.LabelFrame(tab, text="📁 输出设置", style='Modern.TLabelframe')
        extract_frame.pack(fill=tk.X, padx=15, pady=10)
        extract_path_frame = ttk.Frame(extract_frame, style='Modern.TFrame')
        extract_path_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(extract_path_frame, text="输出目录:", style='Modern.TLabel').pack(side=tk.LEFT, padx=5, pady=5)
        self.extract_path = ttk.Entry(extract_path_frame, style='Modern.TEntry')
        self.extract_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=5)
        self.extract_path.insert(0, os.path.join(os.path.expanduser("~"), "解压文件"))
        ttk.Button(extract_path_frame, text="📂 浏览", command=self._select_extract_dir, style='Modern.TButton').pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Label(tab, text="🔒 内置100条密码，自动尝试解密 | ZENC魔数校验文件名",
                  style='Modern.TLabel').pack(padx=15, pady=5)

        progress_frame = ttk.Frame(tab, style='Modern.TFrame')
        progress_frame.pack(fill=tk.X, padx=15, pady=10)
        self.decompress_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL,
                                                    mode='determinate',
                                                    style='Modern.Horizontal.TProgressbar')
        self.decompress_progress.pack(fill=tk.X, expand=True, padx=10, pady=5)
        status_frame = ttk.Frame(progress_frame, style='Modern.TFrame')
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        self.decompress_status = ttk.Label(status_frame, text="✅ 准备就绪", style='Modern.TLabel')
        self.decompress_status.pack(side=tk.LEFT, padx=10)
        self.decompress_btn = ttk.Button(status_frame, text="🚀 开始解压",
                                          command=self._start_decompression, style='Modern.TButton')
        self.decompress_btn.pack(side=tk.RIGHT, padx=10)

    # ---------- 日志标签页 ----------
    def _create_log_tab(self):
        tab = ttk.Frame(self.notebook, style='Modern.TFrame')
        self.notebook.add(tab, text="📝 操作日志")

        log_frame = ttk.LabelFrame(tab, text="📊 操作记录", style='Modern.TLabelframe')
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        self.log_text = scrolledtext.ScrolledText(log_frame,
                                                  bg=self.colors['card'], fg=self.colors['text'],
                                                  bd=1, relief='solid',
                                                  highlightbackground=self.colors['primary'],
                                                  highlightthickness=1,
                                                  font=('Microsoft YaHei', 10), wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state=tk.DISABLED)

        ctrl = ttk.Frame(log_frame, style='Modern.TFrame')
        ctrl.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(ctrl, text="🗑️ 清空日志", command=self._clear_log, style='Modern.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="📋 复制日志", command=self._copy_log, style='Modern.TButton').pack(side=tk.LEFT, padx=5)

    # ---------- 安全标签页 ----------
    def _create_security_tab(self):
        tab = ttk.Frame(self.notebook, style='Modern.TFrame')
        self.notebook.add(tab, text="🛡️ 安全设置")

        sec = ttk.LabelFrame(tab, text="🔐 安全信息", style='Modern.TLabelframe')
        sec.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        features = [
            ("🔒 文件名全加密", "文件名+扩展名一起加密，统一.enc后缀，完全隐藏文件类型"),
            ("🛡 ZENC魔数校验", "密文头部4字节魔数标记，精确识别本程序加密文件"),
            ("🔑 AES-256加密", "军用级AES-256-CBC加密文件名，ZIP内容AES-256加密"),
            ("📦 100条密码字典", "内置100条50位高强度随机密码，压缩随机选一条"),
            ("🚫 零外部文件", "完全独立运行，不生成任何外部配置或对照文档"),
            ("🔒 Cython保护（可选）", "核心模块可编译为二进制，防止反编译获取密钥"),
            ("🧵 线程安全UI", "子线程操作通过root.after调度到主线程，杜绝崩溃"),
        ]
        for title, desc in features:
            f = ttk.Frame(sec, style='Modern.TFrame')
            f.pack(fill=tk.X, padx=20, pady=8)
            ttk.Label(f, text=title, style='Modern.TLabel',
                      font=('Microsoft YaHei', 11, 'bold'),
                      foreground=self.colors['primary']).pack(anchor=tk.W)
            ttk.Label(f, text=desc, style='Modern.TLabel',
                      font=('Microsoft YaHei', 9),
                      foreground=self.colors['text_light']).pack(anchor=tk.W, padx=20, pady=2)

        warn = ttk.LabelFrame(tab, text="⚠️ 重要提醒", style='Modern.TLabelframe')
        warn.pack(fill=tk.X, padx=15, pady=10)
        for w in ["1. 重要文件请做好多重备份，避免数据丢失",
                   "2. 建议使用Cython编译核心模块后再分发",
                   "3. 确保使用同一版本进行压缩和解压",
                   "4. 请勿修改程序文件结构"]:
            ttk.Label(warn, text=w, style='Modern.TLabel',
                      font=('Microsoft YaHei', 10),
                      foreground=self.colors['success']).pack(anchor=tk.W, padx=20, pady=3)

    # ---------- 状态栏 ----------
    def _create_status_bar(self):
        bar = ttk.Frame(self.main_frame, style='Modern.TFrame', relief='solid', borderwidth=1)
        bar.pack(fill=tk.X, pady=15)
        ttk.Label(bar, text="FuFu-zip | ZENC + AES-256",
                  style='Modern.TLabel', font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=15, pady=5)
        self.status_info = ttk.Label(bar, text="✅ 就绪",
                                     style='Modern.TLabel', font=('Microsoft YaHei', 9))
        self.status_info.pack(side=tk.RIGHT, padx=15, pady=5)

    # ============================================================
    # UI操作（线程安全：所有UI更新通过root.after调度）
    # ============================================================
    def _add_log(self, message):
        """添加日志（线程安全）"""
        def _do():
            try:
                self.log_text.config(state=tk.NORMAL)
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                self.log_text.insert(tk.END, f"[{ts}] {message}\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.status_info.config(text=f"📝 {message[:30]}...")
            except:
                pass
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def _update_progress(self, progress_bar, status_label, value, text):
        """更新进度条和状态（线程安全）"""
        def _do():
            progress_bar['value'] = value
            status_label.config(text=text)
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def _show_error(self, title, message):
        """显示错误弹窗（线程安全）"""
        def _do():
            if tk_available:
                messagebox.showerror(title, message)
            else:
                print(f"错误: {message}")
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def _show_warning(self, title, message):
        """显示警告弹窗（线程安全）"""
        def _do():
            if tk_available:
                messagebox.showwarning(title, message)
            else:
                print(f"警告: {message}")
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def _set_button_state(self, btn, state):
        """设置按钮状态（线程安全）"""
        def _do():
            btn.config(state=state)
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    # ============================================================
    # 文件操作
    # ============================================================
    def _add_files(self):
        files = filedialog.askopenfilenames(title="选择文件", filetypes=[("所有文件", "*.*")])
        if files:
            for f in files:
                if f not in self.file_list.get(0, tk.END):
                    self.file_list.insert(tk.END, f)
            self._update_file_stats()
            self._add_log(f"📄 添加了 {len(files)} 个文件")

    def _add_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            if folder not in self.file_list.get(0, tk.END):
                self.file_list.insert(tk.END, folder)
            self._update_file_stats()
            self._add_log(f"📁 添加了文件夹: {folder}")

    def _remove_selected(self):
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)
        self._update_file_stats()

    def _clear_list(self):
        count = self.file_list.size()
        self.file_list.delete(0, tk.END)
        self._update_file_stats()
        self._add_log(f"🗑️ 清空文件列表（共 {count} 项）")

    def _update_file_stats(self):
        count = self.file_list.size()
        self.file_stats.config(text=f"📊 已添加: {count}个文件/文件夹")

    def _select_output_file(self):
        output = filedialog.asksaveasfilename(title="保存压缩文件",
                                              defaultextension=".zip",
                                              filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")])
        if output:
            self.output_path.delete(0, tk.END)
            self.output_path.insert(0, output)

    def _select_zip_file(self):
        zf = filedialog.askopenfilename(title="选择ZIP文件",
                                        filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")])
        if zf:
            self.zip_path.delete(0, tk.END)
            self.zip_path.insert(0, zf)

    def _select_extract_dir(self):
        d = filedialog.askdirectory(title="选择解压目录")
        if d:
            self.extract_path.delete(0, tk.END)
            self.extract_path.insert(0, d)

    # ============================================================
    # 压缩/解压（子线程执行，UI更新通过root.after）
    # ============================================================
    def _start_compression(self):
        files = self.file_list.get(0, tk.END)
        output = self.output_path.get()
        if not files:
            self._show_error("错误", "请先添加文件或文件夹")
            return
        if not output:
            self._show_error("错误", "请选择输出文件")
            return

        self._set_button_state(self.compress_btn, tk.DISABLED)
        self._add_log("🚀 开始压缩...")

        def _progress(v):
            self._update_progress(self.compress_progress, self.compress_status,
                                  v, f"🔄 压缩中... {v}%")

        def _thread():
            try:
                success, message, password = self.zip_handler.compress_files(
                    files, output, _progress)
                self._update_progress(self.compress_progress, self.compress_status,
                                      100, "✅ 压缩成功" if success else "❌ 压缩失败")
                if success:
                    self._add_log(f"🎉 {message}")
                    if password:
                        try:
                            idx = self.password_manager.get_passwords().index(password) + 1
                            self._add_log(f"🔑 使用密码索引: #{idx}")
                        except:
                            pass
                    try:
                        sz = os.path.getsize(output)
                        self._add_log(f"📊 输出大小: {self._format_size(sz)}")
                    except:
                        pass
                else:
                    self._add_log(f"❌ {message}")
                    self._show_error("压缩失败", message)
            except Exception as e:
                self._add_log(f"❌ 压缩异常: {e}")
                self._show_error("压缩异常", str(e))
            finally:
                self._set_button_state(self.compress_btn, tk.NORMAL)

        threading.Thread(target=_thread, daemon=True).start()

    def _start_decompression(self):
        zip_file = self.zip_path.get()
        extract_dir = self.extract_path.get()
        if not zip_file:
            self._show_error("错误", "请选择ZIP文件")
            return
        if not extract_dir:
            self._show_error("错误", "请选择输出目录")
            return

        self._set_button_state(self.decompress_btn, tk.DISABLED)
        self._add_log("🚀 开始解压...")

        def _progress(v):
            self._update_progress(self.decompress_progress, self.decompress_status,
                                  v, f"🔄 解压中... {v}%")

        def _thread():
            try:
                success, message, password = self.zip_handler.decompress_file(
                    zip_file, extract_dir, _progress)
                self._update_progress(self.decompress_progress, self.decompress_status,
                                      100, "✅ 解压成功" if success else "❌ 解压失败")
                if success:
                    self._add_log(f"🎉 {message}")
                    if password:
                        try:
                            idx = self.password_manager.get_passwords().index(password) + 1
                            self._add_log(f"🔑 匹配密码索引: #{idx}")
                        except:
                            pass
                    try:
                        fc = sum(len(files) for _, _, files in os.walk(extract_dir))
                        self._add_log(f"📊 成功解压: {fc}个文件")
                    except:
                        pass
                else:
                    self._add_log(f"❌ {message}")
                    self._show_error("解压失败", message)
            except Exception as e:
                self._add_log(f"❌ 解压异常: {e}")
                self._show_error("解压异常", str(e))
            finally:
                self._set_button_state(self.decompress_btn, tk.NORMAL)

        threading.Thread(target=_thread, daemon=True).start()

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self._add_log("🗑️ 日志已清空")

    def _copy_log(self):
        self.log_text.config(state=tk.NORMAL)
        content = self.log_text.get(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self._add_log("📋 日志已复制到剪贴板")

    @staticmethod
    def _format_size(size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

# ============================================================
# 入口
# ============================================================
def main():
    # 启动GUI前检查依赖
    if _missing_deps and tk_available:
        _root = tk.Tk()
        _root.withdraw()
        _msg = "缺少以下依赖，程序无法运行：\n\n"
        for name, cmd in _missing_deps:
            _msg += f"  • {name} → {cmd}\n"
        _msg += "\n请安装后重新运行。"
        messagebox.showerror("依赖缺失", _msg)
        _root.destroy()
        return
    elif _missing_deps:
        print("错误：缺少以下依赖：")
        for name, cmd in _missing_deps:
            print(f"  • {name} → {cmd}")
        return

    if not tk_available:
        print("错误: Tkinter不可用，请安装包含Tkinter的Python版本")
        return

    root = tk.Tk()
    app = ModernMainWindow(root)
    try:
        root.option_add("*Font", "Microsoft YaHei 10")
    except:
        pass
    root.mainloop()

if __name__ == "__main__":
    main()

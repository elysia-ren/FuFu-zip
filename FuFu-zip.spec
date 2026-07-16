# -*- mode: python ; coding: utf-8 -*-
"""
FuFu-zip PyInstaller spec 文件
使用 --onedir 模式，启动更快
"""

import os
import platform
import glob
from PyInstaller.utils.hooks import collect_dynamic_libs

# ============================================================
# 核心模块
# ============================================================
binaries = []
datas = []

# 图标
if os.path.exists('fufu.ico'):
    datas.append(('fufu.ico', '.'))
if os.path.exists('secure_zip_icon.ico'):
    datas.append(('secure_zip_icon.ico', '.'))

# Cython 核心模块
if platform.system() == 'Windows':
    candidates = glob.glob('core*.pyd')
else:
    candidates = glob.glob('core*.so')

if candidates:
    core_file = candidates[0]
    binaries.append((core_file, '.'))
    print(f"已找到 Cython 核心模块: {core_file}")
else:
    print("注意：未找到 Cython 核心模块，将使用纯Python内置核心模块")

# ============================================================
# 强制收集依赖的动态库
# ============================================================
cryptodome_binaries = collect_dynamic_libs('Cryptodome')
pyzipper_binaries = collect_dynamic_libs('pyzipper')

# ============================================================
# Analysis
# ============================================================
a = Analysis(
    ['zip_tool_modern_v1_0_0.py'],
    pathex=[],
    binaries=binaries + cryptodome_binaries + pyzipper_binaries,
    datas=datas,
    hiddenimports=[
        'pyzipper', 'pyzipper.zipfile_aes',
        'Cryptodome', 'Cryptodome.Cipher', 'Cryptodome.Cipher.AES',
        'Cryptodome.Cipher._AES', 'Cryptodome.Cipher._raw_aes',
        'Cryptodome.Cipher._raw_aesni',
        'Cryptodome.Hash', 'Cryptodome.Hash._SHA256',
        'Cryptodome.Util', 'Cryptodome.Util._raw_api',
        'Cryptodome.Protocol', 'Cryptodome.Protocol.KDF',
        'Cryptodome.Random', 'Cryptodome.Random.get_random_bytes',
        'windnd',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['unittest', 'test', 'xml', 'pydoc', 'doctest', 'pdb',
              'tkinter.test', 'lib2to3', 'ensurepip'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FuFu-zip',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['fufu.ico'] if os.path.exists('fufu.ico') else [],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FuFu-zip',
)

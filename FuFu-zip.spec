# -*- mode: python ; coding: utf-8 -*-
"""
FuFu-zip PyInstaller spec 文件

注意：
- 如果已编译 Cython 核心模块 (core.pyd/core.so)，
  需要在 datas 中添加，确保打包进exe
- 使用 --onefile 模式，配合 Cython 保护敏感代码
"""

import os
import platform

# 检查是否有 Cython 编译的核心模块
binaries = []
datas = []

if platform.system() == 'Windows':
    core_file = 'core.pyd'
else:
    core_file = 'core.so'

if os.path.exists(core_file):
    binaries.append((core_file, '.'))
else:
    print(f"注意：未找到 {core_file}，将使用纯Python内置核心模块")

a = Analysis(
    ['zip_tool_modern_v1_0_0.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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

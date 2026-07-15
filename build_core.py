# -*- coding: utf-8 -*-
"""
Cython 核心模块编译脚本

使用方法：
    pip install cython setuptools pycryptodome
    python build_core.py build_ext --inplace

编译产物：
    Windows: core.pyd
    Linux:   core.so

将编译产物放在主程序同目录，主程序启动时自动 import core 使用编译版本。

⚠️ 版本一致性要求（重要！）：
    core.pyx 中的敏感参数必须与 zip_tool_modern_v1_0_0.py 中的
    _PyPasswordManager / _PyFileNameEncryptor 严格一致，否则会出现：
    - 用 Cython 版压缩 → 用纯 Python 版解压 → 失败
    - 用纯 Python 版压缩 → 用 Cython 版解压 → 失败
    必须保持一致的参数：
    1. 密码种子 (password_seed)
    2. 密码字符集 (chars)
    3. 密码数量 (count) 和长度 (length)
    4. AES 主密码 (master_password)
    5. PBKDF2 盐 (salt)
    6. PBKDF2 迭代次数 (iterations)
    7. AES 密钥长度 (key_size)
    8. ZENC 魔数 (MAGIC)
"""

import os
import sys
import platform

try:
    from setuptools import setup, Extension
    from Cython.Build import cythonize
except ImportError:
    print("请先安装 Cython 和 setuptools：")
    print("  pip install cython setuptools")
    sys.exit(1)

# 确定编译选项
extra_compile_args = []
extra_link_args = []

if platform.system() == 'Windows':
    extra_compile_args = ['/O2']
else:
    extra_compile_args = ['-O2']

# 定义扩展模块
extensions = [
    Extension(
        "core",
        sources=["core.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    )
]

# 编译
setup(
    name="securezip_core",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': '3',
            'boundscheck': False,
            'wraparound': False,
        }
    ),
)

print()
print("=" * 60)
import glob
if platform.system() == 'Windows':
    candidates = glob.glob('core*.pyd')
else:
    candidates = glob.glob('core*.so')

if candidates:
    target = candidates[0]
    print(f"✅ 编译成功！生成: {target}")
    print(f"   文件大小: {os.path.getsize(target) / 1024:.1f} KB")
    print()
    print("下一步：")
    print(f"  1. 将 {target} 放在主程序 zip_tool_modern_v1_0_0.py 同目录")
    print(f"  2. PyInstaller 打包时需包含 {target}")
else:
    print("⚠️ 未找到生成的 core 模块")
    print("   请检查编译输出是否有错误")
print("=" * 60)

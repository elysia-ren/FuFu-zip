# -*- coding: utf-8 -*-
"""
FuFu-zip 打包脚本
自动生成Windows可执行文件

打包流程：
1. （可选）先运行 build_core.py 编译 Cython 核心模块
2. 运行本脚本，自动调用 PyInstaller 生成 exe
3. 产物在 dist/ 目录
"""

import os
import sys
import subprocess
import shutil
import platform


def info(msg):
    print(f"[INFO] {msg}")

def success(msg):
    print(f"[SUCCESS] {msg}")

def error(msg):
    print(f"[ERROR] {msg}")


def check_pyinstaller():
    try:
        subprocess.run(['pyinstaller', '--version'],
                       capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_pyinstaller():
    info("正在安装 pyinstaller...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
                       check=True)
        success("pyinstaller 安装成功")
        return True
    except subprocess.CalledProcessError as e:
        error(f"pyinstaller 安装失败: {e}")
        return False


def check_cython_core():
    """检查是否已编译 Cython 核心模块"""
    import glob
    if platform.system() == 'Windows':
        candidates = glob.glob('core*.pyd')
    else:
        candidates = glob.glob('core*.so')

    if candidates:
        target = candidates[0]
        info(f"检测到 Cython 编译核心模块: {target}")
        return True, target
    else:
        info("未检测到 Cython 核心模块，将使用纯Python内置版本")
        info("如需编译，请先运行: python build_core.py build_ext --inplace")
        return False, None


def create_executable():
    info("开始创建可执行文件...")

    python_version = sys.version_info
    if python_version < (3, 6):
        error(f"Python 版本过低，需要 3.6+，当前: {python_version.major}.{python_version.minor}")
        return False

    if platform.system() != 'Windows':
        error("本打包脚本仅支持 Windows 系统")
        return False

    main_file = "zip_tool_modern_v1_0_0.py"
    if not os.path.exists(main_file):
        error(f"主程序文件不存在: {main_file}")
        return False

    # 检查 Cython 核心模块
    has_core, core_file = check_cython_core()

    # 构建 PyInstaller 命令
    command = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--name', 'FuFu-zip',
        '--clean',
        '--noconfirm',
        main_file
    ]

    # 如果有图标文件，添加图标
    if os.path.exists('fufu.ico'):
        command.extend(['--icon', 'fufu.ico'])

    # 如果有 Cython 核心模块，添加为额外数据
    if has_core and core_file:
        command.extend(['--add-data', f'{core_file};.'])

    try:
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            success("可执行文件创建成功")

            dist_dir = "dist"
            exe_file = os.path.join(dist_dir, "FuFu-zip.exe")

            if os.path.exists(exe_file):
                info(f"可执行文件位置: {exe_file}")
                info(f"文件大小: {os.path.getsize(exe_file) / 1024 / 1024:.2f} MB")
                create_zip_package(dist_dir)
                return True
            else:
                error("可执行文件生成失败")
                return False
        else:
            error(f"pyinstaller 执行失败:\n{result.stderr}")
            return False

    except Exception as e:
        error(f"创建可执行文件时发生错误: {e}")
        return False


def create_zip_package(dist_dir):
    info("创建发布压缩包...")

    release_dir = "FuFu-zip_Release"
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)
    os.makedirs(release_dir)

    exe_file = os.path.join(dist_dir, "FuFu-zip.exe")
    if os.path.exists(exe_file):
        shutil.copy2(exe_file, release_dir)

    for readme in ["优化版使用说明.md", "README.md"]:
        if os.path.exists(readme):
            shutil.copy2(readme, release_dir)

    zip_filename = f"{release_dir}.zip"
    shutil.make_archive(release_dir, 'zip', release_dir)

    success(f"发布压缩包创建成功: {zip_filename}")
    info(f"压缩包大小: {os.path.getsize(zip_filename) / 1024 / 1024:.2f} MB")


def main():
    print("=" * 60)
    print("FuFu-zip 打包工具")
    print("=" * 60)

    if not check_pyinstaller():
        info("检测到 pyinstaller 未安装")
        if not install_pyinstaller():
            error("无法安装 pyinstaller，打包失败")
            return 1

    if create_executable():
        success("=" * 60)
        success("打包完成！")
        success("=" * 60)
        return 0
    else:
        error("=" * 60)
        error("打包失败！")
        error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())

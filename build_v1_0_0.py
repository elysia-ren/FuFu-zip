# -*- coding: utf-8 -*-
"""
FuFu-zip 一键打包脚本 (与 build.bat 等效)
用法: python build_v1_0_0.py
"""
import os, sys, subprocess, shutil, glob

def main():
    if sys.version_info < (3, 6):
        print("需要 Python 3.6+"); return 1
    try:
        subprocess.run(['pyinstaller', '--version'], capture_output=True)
    except:
        print("请先安装 PyInstaller: pip install pyinstaller"); return 1

    # 用和 build.bat 完全相同的方式获取真实路径
    try:
        import Cryptodome, pyzipper, windnd
        crypt_path = Cryptodome.__path__[0]
        zipper_path = pyzipper.__path__[0]
        windnd_path = windnd.__path__[0]
    except ImportError as e:
        print(f"缺少依赖: {e}，请执行 pip install pyzipper pycryptodomex windnd")
        return 1

    for d in ['build', 'dist']:
        if os.path.exists(d):
            shutil.rmtree(d)

    cmd = [
        'pyinstaller',
        '--onefile', '--windowed',
        '--name', 'FuFu-zip',
        '--clean', '--noconfirm',
        '--collect-all', 'Cryptodome',
        '--collect-all', 'pyzipper',
        '--collect-all', 'windnd',
        '--hidden-import', 'tkinter',
        '--hidden-import', 'tkinter.ttk',
        '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'tkinter.messagebox',
        '--hidden-import', 'tkinter.scrolledtext',
        '--exclude-module', 'unittest',
        '--exclude-module', 'test',
        '--exclude-module', 'xml',
        '--exclude-module', 'pydoc',
        '--exclude-module', 'doctest',
        '--exclude-module', 'pdb',
        '--exclude-module', 'lib2to3',
        '--exclude-module', 'ensurepip',
    ]

    if os.path.exists('fufu.ico'):
        cmd += ['--icon', 'fufu.ico', '--add-data', 'fufu.ico;.']

    core_files = glob.glob('core*.pyd') + glob.glob('core*.so')
    if core_files:
        cmd += ['--add-binary', f'{core_files[0]};.']

    cmd.append('zip_tool_modern_v1_0_0.py')

    print("开始打包...")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        exe_path = os.path.join('dist', 'FuFu-zip.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"Build OK: dist\\FuFu-zip.exe ({size_mb:.1f} MB)")
        else:
            print("Build OK: dist\\FuFu-zip.exe")
    else:
        print("打包失败")
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
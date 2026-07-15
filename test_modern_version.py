# -*- coding: utf-8 -*-
"""
FuFu-zip 功能测试脚本
测试加密解密、压缩解压、文件名全加密、ZENC魔数校验
"""
import os
import sys
import tempfile
import shutil

def test_password_manager():
    """测试密码管理器"""
    print("=" * 70)
    print("1. 密码管理器测试")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_password_manager
        pm = _create_password_manager()
        passwords = pm.get_passwords()

        assert len(passwords) == 100, f"密码数量异常: {len(passwords)}"
        assert len(passwords[0]) == 50, f"密码长度异常: {len(passwords[0])}"
        # 验证确定性：同一种子生成相同密码
        pm2 = _create_password_manager()
        passwords2 = pm2.get_passwords()
        assert passwords == passwords2, "两次生成的密码不一致，种子可能未固定"

        print(f"   ✅ 密码数量: {len(passwords)}")
        print(f"   ✅ 密码长度: {len(passwords[0])}")
        print(f"   ✅ 确定性生成验证通过")
        return True
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False

def test_filename_encryptor():
    """测试文件名加密器（含扩展名、ZENC魔数）"""
    print("\n" + "=" * 70)
    print("2. 文件名加密器测试（ZENC魔数 + .enc后缀）")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_filename_encryptor
        enc = _create_filename_encryptor()

        test_cases = [
            "test.txt",
            "报告.docx",
            "中文文件名测试.txt",
            "包含特殊字符的长文件名！@#$%^&*.docx",
            "这是一个非常长的文件名用来测试加密解密功能是否正常工作.pdf",
            "image.png",
            "data.csv",
            "document with spaces.txt",
            "subdir/nested/file.txt",
        ]

        all_passed = True
        for original in test_cases:
            encrypted = enc.encrypt_filename(original)

            # 验证.enc后缀
            assert encrypted.endswith('.enc'), f"缺少.enc后缀: {encrypted}"

            # 验证解密
            decrypted = enc.decrypt_filename(encrypted)
            if decrypted == original:
                print(f"   ✅ {original} → {encrypted[:30]}... → 解密成功")
            else:
                print(f"   ❌ {original} → 期望: {original}, 实际: {decrypted}")
                all_passed = False

        # 测试非.enc文件应原样返回
        fake = "not_encrypted_file.txt"
        result = enc.decrypt_filename(fake)
        assert result == fake, f"非.enc文件应原样返回: {result}"
        print(f"   ✅ 非.enc文件原样返回: {fake}")

        return all_passed
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_compress_decompress():
    """测试完整压缩解压流程"""
    print("\n" + "=" * 70)
    print("3. 压缩解压完整流程测试")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_password_manager, SecureZipHandler

        # 创建测试文件
        test_dir = tempfile.mkdtemp()
        test_files = []
        for i in range(3):
            fp = os.path.join(test_dir, f"测试文件_{i+1}.txt")
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(f"这是测试文件 {i+1} 的内容\n包含中文和特殊字符！@#$%^&*\n")
            test_files.append(fp)

        # 创建子文件夹
        sub_dir = os.path.join(test_dir, "子文件夹")
        os.makedirs(sub_dir)
        sub_file = os.path.join(sub_dir, "嵌套文件.txt")
        with open(sub_file, 'w', encoding='utf-8') as f:
            f.write("这是子文件夹内的文件\n")
        test_files.append(sub_dir)

        pm = _create_password_manager()
        handler = SecureZipHandler(pm)

        # 压缩
        test_zip = os.path.join(test_dir, "test_output.zip")
        success, msg, password = handler.compress_files(test_files, test_zip)
        assert success, f"压缩失败: {msg}"
        assert os.path.exists(test_zip), "ZIP文件未生成"
        print(f"   ✅ 压缩成功: {msg}")
        print(f"   ✅ ZIP大小: {os.path.getsize(test_zip)} bytes")

        # 解压
        extract_dir = os.path.join(test_dir, "解压结果")
        success, msg, used_pw = handler.decompress_file(test_zip, extract_dir)
        assert success, f"解压失败: {msg}"
        print(f"   ✅ 解压成功: {msg}")

        # 验证解压文件
        extracted = []
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                extracted.append(os.path.relpath(os.path.join(root, f), extract_dir))

        print(f"   ✅ 解压文件数: {len(extracted)}")
        for ef in sorted(extracted):
            print(f"      {ef}")

        # 验证文件名恢复（含扩展名）
        has_txt = any(ef.endswith('.txt') for ef in extracted)
        assert has_txt, "解压后未恢复.txt扩展名"
        print(f"   ✅ 文件名+扩展名恢复正确")

        # 清理
        shutil.rmtree(test_dir)
        return True

    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_zenc_magic_validation():
    """测试ZENC魔数校验：非本程序加密的文件不应被错误解密"""
    print("\n" + "=" * 70)
    print("4. ZENC魔数校验测试")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_filename_encryptor
        enc = _create_filename_encryptor()

        # 构造一个没有ZENC魔数的假加密文件名
        import base64
        from Crypto.Random import get_random_bytes
        fake_data = b"this is not ZENC encrypted" + b"\x10" * 16
        fake_b64 = base64.b64encode(fake_data).decode('ascii').replace('/', '_').replace('+', '-').replace('=', '')
        fake_name = fake_b64 + ".enc"

        result = enc.decrypt_filename(fake_name)
        # 无ZENC魔数，应原样返回
        assert result == fake_name, f"应原样返回但得到: {result}"
        print(f"   ✅ 无ZENC魔数的文件原样返回（不解密）")

        # 正常加密应有ZENC魔数
        original = "test_file.txt"
        encrypted = enc.encrypt_filename(original)
        decrypted = enc.decrypt_filename(encrypted)
        assert decrypted == original
        print(f"   ✅ 正常加密文件通过ZENC校验并正确解密")

        return True
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 70)
    print("FuFu-zip 功能测试")
    print("=" * 70)

    # 检查依赖
    try:
        import pyzipper
        print("✅ pyzipper 可用")
    except ImportError:
        print("❌ pyzipper 不可用: pip install pyzipper")
        return 1

    try:
        from Crypto.Cipher import AES
        print("✅ pycryptodome 可用")
    except ImportError:
        print("❌ pycryptodome 不可用: pip install pycryptodome")
        return 1

    print()

    results = []
    results.append(("密码管理器", test_password_manager()))
    results.append(("文件名加密器", test_filename_encryptor()))
    results.append(("ZENC魔数校验", test_zenc_magic_validation()))
    results.append(("压缩解压流程", test_compress_decompress()))

    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    all_ok = True
    for name, ok in results:
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"  {name}: {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main())

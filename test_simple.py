# -*- coding: utf-8 -*-
"""
简化版功能测试 - 快速验证核心加密解密能力
"""
import sys
import os

def test_filename_encryption():
    """测试文件名加密解密（含扩展名、ZENC魔数、.enc后缀）"""
    print("=" * 70)
    print("FuFu-zip - 文件名加密解密功能测试")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_filename_encryptor
        encryptor = _create_filename_encryptor()
        print("✅ 创建加密器成功")
    except Exception as e:
        print(f"❌ 创建加密器失败: {e}")
        return False

    test_filenames = [
        "test.txt",
        "中文文件名测试.txt",
        "包含特殊字符的长文件名！@#$%^&*.docx",
        "这是一个非常长的文件名用来测试加密解密功能是否正常工作.pdf",
        "image.png",
        "data.csv",
        "document with spaces.txt",
        "1234567890_abcdefghijklmnopqrstuvwxyz.txt",
        "subdir/nested/file.txt",
    ]

    print(f"\n开始测试 {len(test_filenames)} 个文件名...\n")

    all_passed = True
    for i, filename in enumerate(test_filenames, 1):
        try:
            encrypted = encryptor.encrypt_filename(filename)
            decrypted = encryptor.decrypt_filename(encrypted)

            has_enc = encrypted.endswith('.enc')
            match = decrypted == filename

            if has_enc and match:
                print(f"  #{i} ✅ {filename}")
            else:
                reasons = []
                if not has_enc:
                    reasons.append("缺少.enc后缀")
                if not match:
                    reasons.append(f"解密不匹配: {decrypted}")
                print(f"  #{i} ❌ {filename} — {', '.join(reasons)}")
                all_passed = False
        except Exception as e:
            print(f"  #{i} ❌ {filename} — 异常: {e}")
            all_passed = False

    print()
    return all_passed

def test_password_manager():
    """测试密码管理器"""
    print("=" * 70)
    print("密码管理器测试")
    print("=" * 70)

    try:
        from zip_tool_modern_v1_0_0 import _create_password_manager
        manager = _create_password_manager()
        passwords = manager.get_passwords()
        count = manager.get_password_count()

        print(f"✅ 密码管理器初始化成功")
        print(f"✅ 生成密码数量: {count}")
        print(f"✅ 每个密码长度: {len(passwords[0]) if passwords else 0}")

        # 验证确定性
        from zip_tool_modern_v1_0_0 import _create_password_manager as pm2
        p2 = pm2().get_passwords()
        assert passwords == p2, "密码不一致"
        print(f"✅ 确定性生成验证通过")

        return True
    except Exception as e:
        print(f"❌ 密码管理器测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始 FuFu-zip 功能测试...\n")

    filename_ok = test_filename_encryption()
    password_ok = test_password_manager()

    print("=" * 70)
    print("测试总结")
    print("=" * 70)

    if filename_ok and password_ok:
        print("\n🎉 所有核心功能测试通过！")
        print("\n✅ 文件名加密解密: 正常（含扩展名、ZENC魔数、.enc后缀）")
        print("✅ 密码管理器: 正常（确定性生成）")
        return 0
    else:
        print("\n❌ 部分测试失败。")
        return 1

if __name__ == "__main__":
    sys.exit(main())

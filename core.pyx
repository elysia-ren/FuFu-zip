# -*- coding: utf-8 -*-
# cython: language_level=3
"""
SecureZip Pro 核心安全模块 (Cython编译版)
...
"""

import os
import random
import string
import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes


cdef class PasswordManager:
    """
    密码字典生成器（Cython编译保护）
    种子和字符集编译为二进制后，常规反编译工具无法直接读取。
    """

    cdef list _passwords
    cdef int _count

    def __init__(self):
        cdef str chars = (
            string.ascii_uppercase
            + string.ascii_lowercase
            + string.digits
            + "!@#$%^&*()_+-=[]{}|;:,.<>?"
        )
        # 使用普通 Python 整数，避免 C 编译器 int 大小限制
        seed = 0  # 占位值，请替换为自己的随机种子（推荐 9~12 位整数）

        # ---- 占位值检测 ----
        if seed == 0:
            raise RuntimeError("核心模块未配置安全密钥，请替换占位种子后重新编译。")
        # -------------------

        cdef int count = 100
        cdef int length = 50
        cdef int i
        cdef str pw

        self._count = count
        self._passwords = []
        for i in range(count):
            random.seed(seed + i)
            pw = ''.join(random.choice(chars) for _ in range(length))
            random.seed()
            self._passwords.append(pw)

    def get_passwords(self):
        return self._passwords.copy()

    def get_password_count(self):
        return self._count


cdef class FileNameEncryptor:
    """
    文件名全名加密器（含扩展名，Cython编译保护）
    密钥通过PBKDF2从主密码派生，编译后主密码以二进制形式存在。
    """

    cdef bytes _magic
    cdef bytes _key
    cdef int _block_size

    def __init__(self):
        # ---- 敏感参数：编译后以二进制形式存在 ----
        master_pw = "YOUR_SECRET_KEY_HERE"       # 占位值，请替换为强密码
        salt = b"YOUR_SECRET_SALT_HERE"          # 占位值，请替换为随机字节序列

        # ---- 占位值检测 ----
        if master_pw == "YOUR_SECRET_KEY_HERE" or salt == b"YOUR_SECRET_SALT_HERE":
            raise RuntimeError("核心模块未配置安全密钥，请替换占位密码和盐后重新编译。")
        # -------------------

        cdef int iterations = 100000
        cdef int key_size = 32

        self._magic = b"ZENC"
        self._block_size = 16
        self._key = PBKDF2(master_pw, salt, dkLen=key_size, count=iterations)

    cdef bytes _pad(self, bytes data):
        cdef int padding = self._block_size - len(data) % self._block_size
        return data + bytes([padding] * padding)

    cdef bytes _unpad(self, bytes data):
        if not data:
            return data
        cdef int length = len(data)
        cdef int p = data[length - 1]          # 正索引替换 data[-1]
        if p < 1 or p > self._block_size:
            raise ValueError("无效的填充")
        return data[:length - p]               # 正索引替换 data[:-p]

    def encrypt_filename(self, str original_filename):
        """
        加密完整文件名（含扩展名）
        返回：纯ASCII字符串.enc
        """
        cdef bytes payload
        cdef bytes iv
        cdef bytes encrypted
        cdef bytes combined
        cdef str b64
        cdef str safe

        try:
            payload = self._magic + original_filename.encode('utf-8')
            payload = self._pad(payload)

            iv = get_random_bytes(self._block_size)
            encrypted = AES.new(self._key, AES.MODE_CBC, iv).encrypt(payload)

            combined = iv + encrypted
            b64 = base64.b64encode(combined).decode('ascii')
            safe = b64.replace('/', '_').replace('+', '-').replace('=', '')
            return safe + ".enc"
        except Exception:
            h = hashlib.sha256(
                original_filename.encode('utf-8')).hexdigest()[:16]
            return f"fallback_{h}.enc"

    def decrypt_filename(self, str encrypted_filename):
        """
        解密文件名
        输入：Base64字符串.enc
        返回：原始完整文件名
        """
        cdef str name
        cdef int pad_needed
        cdef bytes decoded
        cdef bytes iv
        cdef bytes enc_data
        cdef bytes decrypted
        cdef bytes unpadded
        cdef str original

        try:
            name = encrypted_filename
            if name.endswith('.enc'):
                name = name[:-4]
            else:
                return encrypted_filename

            # 恢复Base64字符
            name = name.replace('_', '/').replace('-', '+')
            pad_needed = len(name) % 4
            if pad_needed:
                name += '=' * (4 - pad_needed)

            decoded = base64.b64decode(name)
            if len(decoded) < self._block_size * 2:
                return encrypted_filename

            iv = decoded[:self._block_size]
            enc_data = decoded[self._block_size:]

            decrypted = AES.new(self._key, AES.MODE_CBC, iv).decrypt(enc_data)
            unpadded = self._unpad(decrypted)

            # 校验ZENC魔数
            if unpadded[:4] != self._magic:
                return encrypted_filename

            original = unpadded[4:].decode('utf-8')
            return original
        except Exception:
            return encrypted_filename
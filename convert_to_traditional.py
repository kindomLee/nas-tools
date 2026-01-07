#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡體中文轉繁體中文（台灣用語）轉換腳本
使用 OpenCC 進行專業級的簡繁轉換
"""

import os
import sys
import subprocess
from pathlib import Path

def install_opencc():
    """安裝 OpenCC 函式庫"""
    print("正在安裝 OpenCC 函式庫...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "opencc-python-reimplemented"])
        print("✓ OpenCC 安裝完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ OpenCC 安裝失敗: {e}")
        return False

def convert_file(file_path, converter):
    """轉換單一檔案"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用 OpenCC 轉換
        converted = converter.convert(content)

        # 只有當內容有變化時才寫入
        if converted != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(converted)
            return True
        return False
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
        return False

def main():
    """主函式"""
    # 安裝 OpenCC
    if not install_opencc():
        sys.exit(1)

    # 匯入 OpenCC
    try:
        from opencc import OpenCC
    except ImportError:
        print("✗ 無法匯入 OpenCC，請確認安裝是否成功")
        sys.exit(1)

    # 初始化轉換器（簡體轉繁體台灣用語）
    print("\n正在初始化 OpenCC 轉換器（s2twp: 簡體->繁體台灣用語+慣用詞彙）...")
    converter = OpenCC('s2twp')

    # 定義要轉換的檔案模式
    file_patterns = {
        '**/*.md': 'Markdown 檔案',
        '**/*.html': 'HTML 範本',
        '**/*.py': 'Python 原始碼',
        '**/*.yaml': 'YAML 配置檔',
        '**/*.yml': 'YAML 配置檔',
        '**/*.json': 'JSON 配置檔',
    }

    # 排除的目錄
    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.github', 'third_party', 'db_scripts'}

    root_path = Path('.')
    total_files = 0
    converted_files = 0

    print("\n開始轉換檔案...\n")

    for pattern, description in file_patterns.items():
        print(f"處理 {description}...")
        for file_path in root_path.glob(pattern):
            # 跳過排除的目錄
            if any(excluded in file_path.parts for excluded in exclude_dirs):
                continue

            # 跳過此腳本本身
            if file_path.name == 'convert_to_traditional.py':
                continue

            total_files += 1
            print(f"  處理: {file_path}")

            if convert_file(file_path, converter):
                converted_files += 1
                print(f"  ✓ 已轉換")
            else:
                print(f"  - 無變更或已是繁體")

    # 輸出統計
    print(f"\n{'='*60}")
    print(f"轉換完成！")
    print(f"總共處理: {total_files} 個檔案")
    print(f"實際轉換: {converted_files} 個檔案")
    print(f"無需轉換: {total_files - converted_files} 個檔案")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()

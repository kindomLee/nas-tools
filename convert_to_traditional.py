#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert Simplified Chinese to Traditional Chinese in nas-tools repository
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Try to import conversion libraries
converter = None
conversion_method = None

try:
    from opencc import OpenCC
    converter = OpenCC('s2twp')  # Simplified to Traditional (Taiwan variant with phrases)
    conversion_method = "opencc"
    print("Using OpenCC for conversion")
except ImportError:
    try:
        import zhconv
        conversion_method = "zhconv"
        print("Using zhconv for conversion")
    except ImportError:
        try:
            from hanziconv import HanziConv
            conversion_method = "hanziconv"
            print("Using hanziconv for conversion")
        except ImportError:
            print("No conversion library found. Installing opencc-python-reimplemented...")
            import subprocess
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "opencc-python-reimplemented", "-q"])
                from opencc import OpenCC
                converter = OpenCC('s2twp')
                conversion_method = "opencc"
                print("Successfully installed and loaded OpenCC")
            except Exception as e:
                print(f"Failed to install OpenCC: {e}")
                print("Trying zhconv...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "zhconv", "-q"])
                    import zhconv
                    conversion_method = "zhconv"
                    print("Successfully installed and loaded zhconv")
                except Exception as e2:
                    print(f"Failed to install zhconv: {e2}")
                    print("ERROR: No conversion library available. Please install manually:")
                    print("  pip install opencc-python-reimplemented")
                    print("  OR pip install zhconv")
                    sys.exit(1)


def convert_text(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese"""
    if not text:
        return text

    if conversion_method == "opencc":
        return converter.convert(text)
    elif conversion_method == "zhconv":
        import zhconv
        return zhconv.convert(text, 'zh-tw')
    elif conversion_method == "hanziconv":
        from hanziconv import HanziConv
        return HanziConv.toTraditional(text)

    return text


def has_chinese(text: str) -> bool:
    """Check if text contains Chinese characters"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def convert_file(file_path: Path) -> Tuple[bool, str]:
    """
    Convert a single file from Simplified to Traditional Chinese
    Returns: (was_modified, error_message)
    """
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # Skip if no Chinese characters
        if not has_chinese(original_content):
            return False, "No Chinese characters"

        # Convert content
        converted_content = convert_text(original_content)

        # Check if content changed
        if converted_content == original_content:
            return False, "Already in Traditional Chinese"

        # Write back converted content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(converted_content)

        return True, "Converted successfully"

    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    """Main conversion process"""
    base_dir = Path('/home/runner/work/nas-tools/nas-tools')

    # Define file lists to convert
    file_lists = {
        "Markdown files": [
            "README.md",
            "LICENSE.md",
            "docker/readme.md",
            ".github/ISSUE_TEMPLATE/feature.md",
            ".github/ISSUE_TEMPLATE/bug.md",
        ],
        "Configuration files": [
            "config/config.yaml",
            "config/default-category.yaml",
            "docker/compose.yml",
        ],
    }

    # Find all HTML template files
    html_files = []
    web_templates_dir = base_dir / "web" / "templates"
    if web_templates_dir.exists():
        html_files = [str(f.relative_to(base_dir)) for f in web_templates_dir.rglob("*.html")]
    file_lists["HTML template files"] = html_files

    # Find all Python files
    py_files = []
    for pattern in ["app/**/*.py", "web/**/*.py", "*.py"]:
        py_files.extend([str(f.relative_to(base_dir)) for f in base_dir.glob(pattern)])
    # Remove duplicates and sort
    py_files = sorted(set(py_files))
    file_lists["Python source files"] = py_files

    # Statistics
    total_files = 0
    converted_files = 0
    skipped_files = 0
    error_files = 0

    converted_list = []
    skipped_list = []
    error_list = []

    print(f"\n{'='*80}")
    print(f"Starting Simplified to Traditional Chinese conversion")
    print(f"{'='*80}\n")

    # Process each category
    for category, files in file_lists.items():
        print(f"\n{category} ({len(files)} files):")
        print(f"{'-'*80}")

        for file_rel_path in files:
            file_path = base_dir / file_rel_path

            if not file_path.exists():
                print(f"  SKIP: {file_rel_path} (file not found)")
                skipped_files += 1
                skipped_list.append((file_rel_path, "File not found"))
                continue

            total_files += 1
            was_modified, message = convert_file(file_path)

            if was_modified:
                print(f"  CONVERTED: {file_rel_path}")
                converted_files += 1
                converted_list.append(file_rel_path)
            elif "Error" in message:
                print(f"  ERROR: {file_rel_path} - {message}")
                error_files += 1
                error_list.append((file_rel_path, message))
            else:
                print(f"  SKIP: {file_rel_path} ({message})")
                skipped_files += 1
                skipped_list.append((file_rel_path, message))

    # Print summary
    print(f"\n{'='*80}")
    print(f"CONVERSION SUMMARY")
    print(f"{'='*80}")
    print(f"Total files processed: {total_files}")
    print(f"  Converted: {converted_files}")
    print(f"  Skipped: {skipped_files}")
    print(f"  Errors: {error_files}")
    print(f"{'='*80}\n")

    if converted_list:
        print(f"\nConverted files ({len(converted_list)}):")
        for f in converted_list:
            print(f"  - {f}")

    if error_list:
        print(f"\nFiles with errors ({len(error_list)}):")
        for f, msg in error_list:
            print(f"  - {f}: {msg}")

    # Save detailed report
    report_path = base_dir / "conversion_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Simplified to Traditional Chinese Conversion Report\n")
        f.write(f"{'='*80}\n\n")
        f.write(f"Conversion method: {conversion_method}\n")
        f.write(f"Total files processed: {total_files}\n")
        f.write(f"Converted: {converted_files}\n")
        f.write(f"Skipped: {skipped_files}\n")
        f.write(f"Errors: {error_files}\n\n")

        f.write(f"Converted files:\n")
        for file in converted_list:
            f.write(f"  - {file}\n")

        f.write(f"\nSkipped files:\n")
        for file, reason in skipped_list:
            f.write(f"  - {file}: {reason}\n")

        if error_list:
            f.write(f"\nFiles with errors:\n")
            for file, msg in error_list:
                f.write(f"  - {file}: {msg}\n")

    print(f"\nDetailed report saved to: {report_path}")

    return 0 if error_files == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

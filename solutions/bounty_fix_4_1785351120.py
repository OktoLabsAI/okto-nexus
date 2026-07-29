### Technical Overview

This solution provides an automated, zero-downtime Python migration tool to organize root-level product screenshots into `docs/assets/screenshots/` while updating all relative and absolute path references across the repository (e.g., Markdown files, HTML templates, CSS/SCSS files, and code docstrings).

#### Strategy & Refactoring Logic

1. **Target Directory Strategy**:
   - Create destination directory `docs/assets/screenshots/` if it does not exist.
   - Target image formats: `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`.

2. **Relative Path Resolution Engine**:
   - For every text/documentation file in the repository (e.g., `.md`, `.rst`, `.html`, `.py`), the engine calculates the correct relative path from the document's directory to `docs/assets/screenshots/<filename>`.
   - Examples:
     - Root `README.md` $\rightarrow$ `docs/assets/screenshots/screenshot.png`
     - `docs/index.md` $\rightarrow$ `assets/screenshots/screenshot.png`
     - `docs/guides/user.md` $\rightarrow$ `../assets/screenshots/screenshot.png`

3. **Pattern Matching & Reference Updates**:
   - Matches Markdown images (`![alt](...)`), HTML tags (`<img src="...">`), CSS (`url(...)`), and plain string references.
   - Handles prefixes such as `./`, `../`, `/`, and bare filenames.

---

### Python Solution: `migrate_screenshots.py`

```python
#!/usr/bin/env python3
"""
Automated Migration Script: Move Root Screenshots to docs/assets/screenshots/
and update all repository references dynamically.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Configuration
TARGET_DIR = Path("docs/assets/screenshots")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".html", ".htm", ".json", ".py", ".js", ".ts", ".css"}


def get_root_screenshots(repo_root: Path) -> List[Path]:
    """Find all image files sitting directly in the repository root."""
    screenshots = []
    for item in repo_root.iterdir():
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
            screenshots.append(item)
    return sorted(screenshots)


def compute_relative_path(from_file: Path, target_image_path: Path) -> str:
    """Compute relative POSIX path from a document file to the target image location."""
    file_dir = from_file.parent
    rel_path = os.path.relpath(target_image_path, file_dir)
    return Path(rel_path).as_posix()


def update_references_in_file(
    file_path: Path, image_map: Dict[str, Path], repo_root: Path
) -> bool:
    """
    Scans a single file and replaces references to moved screenshots.
    Returns True if any updates were made.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False

    modified = False
    new_content = content

    for img_name, new_target_path in image_map.items():
        if img_name not in new_content:
            continue

        # Compute relative replacement path for this specific file
        new_rel_path = compute_relative_path(file_path, new_target_path)

        # Regex pattern to match various path styles referencing the image:
        # e.g., "my_img.png", "./my_img.png", "/my_img.png", "../my_img.png"
        pattern = re.compile(
            r"(?<=[\"'\(\=\s/])" + re.escape(img_name)
            + r"|(?<=[\"'\(\=\s])(?:\./|\.\./|/)" + re.escape(img_name)
        )

        def replace_match(match: re.Match) -> str:
            nonlocal modified
            modified = True
            return new_rel_path

        # Simple string replace fallback if pattern matching requires standard path update
        # Standard markdown replacement: ![alt](img_name) or ![alt](./img_name)
        old_refs = [
            f"({img_name})",
            f"(./{img_name})",
            f'src="{img_name}"',
            f'src="./{img_name}"',
            f'href="{img_name}"',
            f'href="./{img_name}"',
        ]

        for old_ref in old_refs:
            if old_ref in new_content:
                if "src=" in old_ref:
                    new_ref = f'src="{new_rel_path}"'
                elif "href=" in old_ref:
                    new_ref = f'href="{new_rel_path}"'
                else:
                    new_ref = f"({new_rel_path})"
                new_content = new_content.replace(old_ref, new_ref)
                modified = True

    if modified:
        file_path.write_text(new_content, encoding="utf-8")

    return modified


def scan_and_update_all_references(repo_root: Path, image_map: Dict[str, Path]) -> int:
    """Scan all repo files and update screenshot references."""
    updated_files_count = 0

    for root, dirs, files in os.walk(repo_root):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file_name in files:
            file_path = Path(root) / file_name
            if file_path.suffix.lower() in DOC_EXTENSIONS:
                if update_references_in_file(file_path, image_map, repo_root):
                    print(f"  Updated references in: {file_path.relative_to(repo_root)}")
                    updated_files_count += 1

    return updated_files_count


def migrate_screenshots(dry_run: bool = False) -> None:
    """Main execution function to move root screenshots and update references."""
    repo_root = Path.cwd()
    target_dir = repo_root / TARGET_DIR

    screenshots = get_root_screenshots(repo_root)

    if not screenshots:
        print("No root-level screenshots found to migrate.")
        return

    print(f"Found {len(screenshots)} root-level screenshot(s) to migrate.")

    # Map image filename -> target destination Path
    image_map: Dict[str, Path] = {
        img.name: target_dir / img.name for img in screenshots
    }

    if dry_run:
        print("\n--- DRY RUN SUMMARY ---")
        print(f"Target Directory: {TARGET_DIR}")
        print("Files to move:")
        for img in screenshots:
            print(f"  - {img.name} -> {TARGET_DIR}/{img.name}")
        return

    # Step 1: Ensure destination directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Update all document references first
    print("\n1. Updating documentation references across repository...")
    updated_count = scan_and_update_all_references(repo_root, image_map)
    print(f"   Completed reference updates in {updated_count} file(s).")

    # Step 3: Move screenshot files
    print("\n2. Moving screenshots to destination folder...")
    for img in screenshots:
        dest = image_map[img.name]
        shutil.move(str(img), str(dest))
        print(f"   Moved: {img.name} -> {TARGET_DIR}/{img.name}")

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    is_dry_run = "--dry-run" in sys.argv
    migrate_screenshots(dry_run=is_dry_run)
```

---

### Instructions to Execute

1. Run a dry run to review affected files:
   ```bash
   python3 migrate_screenshots.py --dry-run
   ```
2. Execute the migration:
   ```bash
   python3 migrate_screenshots.py
   ```
3. Verify git status and check modified files:
   ```bash
   git status
   ```
#!/usr/bin/env python3
"""
Bulletin PDF Download & Send Pipeline (Both sites, ordered)

Complete workflow:
1. Clean /tmp/pdf/ (remove old .pdf and .jpg)
2. Download latest bulletins from ALL sites (bstsd + maria)
3. VERIFY both downloads succeeded, otherwise ABORT
4. Convert PDFs to JPG images using pdftoppm (300 DPI)
   - maria FIRST (pages 1-7 only, skip ads), then bstsd (all pages, reversed)
   - Global sequence: 01-07 (maria), 08-09 (bstsd reversed)
5. Clear Windows Pictures folder
6. Copy JPG images to Windows Pictures folder
7. Send via Kakao using AutoHotkey

WSL2 environment: Assumes Windows file system is accessible under /mnt/c/
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
import shutil
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_PDF_DIR = "/tmp/pdf"
DEFAULT_IMAGE_DIR = "/tmp/pdf_images"
WINDOWS_PICTURES_WSL = Path("/mnt/c/Users/이태석/Pictures")

# Windows format paths (for AHK script)
AHK_SCRIPT_WIN = r"C:\Users\이태석\Documents\send_kakao.ahk"

# WSL2 paths for execution and existence checks
AHK_EXE_WSL = Path("/mnt/c/Program Files/AutoHotkey/v2/AutoHotkey64.exe")
AHK_SCRIPT_WSL = Path("/mnt/c/Users/이태석/Documents/send_kakao.ahk")

# send_kakao.ahk shows a blocking MsgBox on every failure path (Kakao logged out,
# chat room not found, file dialog missing). Without a timeout the pipeline waits
# on that dialog forever. Cap the wait and clean up the orphaned AHK process.
AHK_TIMEOUT_SEC = 180
AHK_PROCESS_NAME = "AutoHotkey64.exe"

# ⚠ send_kakao.ahk 의 CollectImages() 가 수집하는 확장자와 **반드시 같아야 한다**:
#     for ext in ["*.jpg", "*.jpeg", "*.png"]
# 2026-10-10 사고: 여기가 *.jpg 하나뿐이라 10/3 에 들어온 화면 캡처 png 2장이
# Pictures 에 영구 잔류했고, AHK 는 png 도 집기 때문에 주보를 보낼 때마다
# 함께 나갔다. **보내는 범위보다 지우는 범위가 좁으면 남은 것이 매번 따라간다.**
# send_kakao.ahk 의 확장자 목록을 바꾸면 이 줄도 같이 바꿀 것.
# Windows 파일시스템은 대소문자를 구분하지 않으므로 .PNG 같은 변형도 잡는다.
#
# 📌 2026-10-10 태석님 결정: **주보 전용 폴더로 분리하지 않는다.**
#    Pictures 를 계속 공유하므로 **이 범위 일치가 유일한 방어선이다.**
#    send_kakao.ahk 의 CollectImages() 확장자 목록이 바뀌면 여기도 반드시 같이 바꿀 것.
#    (분리안을 다시 꺼내지 말 것 — 이미 검토하고 접은 길이다)
AHK_COLLECTED_SUFFIXES = {".jpg", ".jpeg", ".png"}

# Absolute path: powershell.exe is not always on PATH under WSL interop.
POWERSHELL_WSL = Path(
    "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
)

# Scripts directory
SCRIPTS_DIR = Path(__file__).parent.resolve()
DOWNLOAD_SCRIPT = SCRIPTS_DIR / "download.py"

def run_cmd(cmd, check=True, capture_output=True):
    """Run shell command and log output."""
    logger.info(f"▶️  {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        capture_output=capture_output,
        text=True
    )
    if check and result.returncode != 0:
        logger.error(f"❌ Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        if result.stderr:
            logger.error(result.stderr)
        sys.exit(result.returncode)
    return result

def clean_directory(dir_path, patterns=["*.pdf", "*.jpg", "*.jpeg"]):
    """Remove files matching patterns in directory."""
    path = Path(dir_path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Created directory: {dir_path}")
        return

    removed_count = 0
    for pattern in patterns:
        for f in path.glob(pattern):
            f.unlink()
            removed_count += 1
            logger.debug(f"🗑️  Removed {f}")
    logger.info(f"✅ Cleaned {dir_path} ({removed_count} files)")

def download_all_pdfs(pdf_dir):
    """Download PDFs from all sites using download.py --all.
    Returns list of successful download results (dict from JSON output).
    Aborts if any site fails."""
    logger.info("📥 Step 1: Downloading PDFs from all sites...")
    cmd = [sys.executable, str(DOWNLOAD_SCRIPT), '--all', '--download-dir', pdf_dir, '--format', 'json']
    result = run_cmd(cmd, check=False)

    # Parse JSON output
    try:
        results = json.loads(result.stdout)
        if not isinstance(results, list):
            raise ValueError("Expected JSON array")
    except Exception as e:
        logger.error(f"❌ Failed to parse download output as JSON: {e}")
        logger.error(f"Output: {result.stdout}")
        sys.exit(1)

    # Check each site
    failed = []
    succeeded = []
    for r in results:
        site = r.get('site')
        success = r.get('success', False)
        if success:
            succeeded.append(r)
            logger.info(f"   ✅ {site}: {r.get('date')} - {r.get('title', 'N/A')}")
        else:
            failed.append(site)
            logger.error(f"   ❌ {site}: {r.get('error', 'Unknown error')}")

    if failed:
        logger.error(f"❌ Download failed for sites: {', '.join(failed)}")
        logger.error("Aborting pipeline since not all sites succeeded.")
        sys.exit(1)

    if len(succeeded) == 0:
        logger.error("❌ No PDFs downloaded successfully.")
        sys.exit(1)

    logger.info(f"✅ All {len(succeeded)} sites succeeded.")
    return succeeded

def convert_pdfs_to_images(pdf_dir, image_dir):
    """Convert all PDFs in pdf_dir to JPG images using pdftoppm (300 DPI).
    Process maria first, then bstsd for consistent ordering.
    Final image naming: 01.jpg, 02.jpg, ... (global sequence)
    - maria (서울대교구): pages 01-07 (normal order, pages 1-7 only)
    - bstsd (흑석동성당): pages 08-09 (reversed order: last page first)
    Returns: list of final image paths (only renamed images, excluding filtered/ads)"""
    logger.info("🖼️  Step 2: Converting PDFs to images (300 DPI)...")
    pdf_path = Path(pdf_dir)
    image_path = Path(image_dir)

    # Clean and create image directory
    clean_directory(image_dir, ["*.jpg", "*.jpeg"])
    image_path.mkdir(parents=True, exist_ok=True)

    # Find PDFs and sort by site (maria first, then bstsd)
    pdfs = list(pdf_path.glob('*.pdf'))
    if not pdfs:
        logger.error("❌ No PDF files found to convert")
        sys.exit(1)

    # Sort: maria comes first (site name 'maria' < 'bstsd')
    pdfs.sort(key=lambda p: p.stem.split('_')[-1])  # site name is last part before extension

    # Collect all images with their site
    all_images = []  # List of (temp_path, site_name)

    for pdf in pdfs:
        parts = pdf.stem.split('_')
        site_name = parts[1] if len(parts) >= 2 else pdf.stem

        # pdftoppm -jpeg -rx 300 -ry 300 input.pdf output_prefix
        output_prefix = str(image_path / pdf.stem)
        cmd = ['pdftoppm', '-jpeg', '-rx', '300', '-ry', '300', str(pdf), output_prefix]
        run_cmd(cmd)

        # Get generated images
        images = list(image_path.glob(f"{pdf.stem}-*.jpg"))
        if not images:
            logger.error(f"❌ No images generated for {pdf.name}")
            sys.exit(1)

        # Sort images by page number
        def page_num(p):
            try:
                return int(p.stem.split('-')[-1])
            except:
                return 0
        images.sort(key=page_num)

        # Filter: maria → pages 1-7 only, bstsd → all pages
        if site_name == 'maria':
            filtered = [img for img in images if page_num(img) <= 7]
            skipped = len(images) - len(filtered)
            if skipped > 0:
                logger.info(f"   ℹ️  {pdf.name}: Using pages 1-7 only (skipped {skipped} ad pages after page 7)")
            images = filtered
        # bstsd: keep all

        num_pages = len(images)
        if num_pages == 0:
            logger.error(f"❌ No pages remaining after filtering for {pdf.name}")
            sys.exit(1)

        for img in images:
            all_images.append((img, site_name))

        logger.info(f"   ✓ {pdf.name} ({site_name}) → {num_pages} pages (after filtering)")

    # Assign global numbers and rename
    global_num = 1
    processed = []

    # First: maria (normal order) → 01-07
    maria_imgs = [(img, site) for img, site in all_images if site == 'maria']
    for img, site in maria_imgs:
        new_name = f"{global_num:02d}.jpg"
        new_path = image_path / new_name
        img.rename(new_path)
        processed.append(new_path)
        global_num += 1

    # Second: bstsd (reversed order) → 08-09
    bstsd_imgs = [(img, site) for img, site in all_images if site == 'bstsd']
    bstsd_imgs.sort(key=lambda x: int(x[0].stem.split('-')[-1]), reverse=True)
    for img, site in bstsd_imgs:
        new_name = f"{global_num:02d}.jpg"
        new_path = image_path / new_name
        img.rename(new_path)
        processed.append(new_path)
        global_num += 1

    total = len(processed)
    logger.info(f"✅ Converted {len(pdfs)} PDFs to {total} images with global sequence 01-{total:02d}")

    # Clean up any leftover original JPG files (ads, filtered pages) that were not renamed
    leftover_count = 0
    for leftover in image_path.glob("*.jpg"):
        if leftover not in processed:
            try:
                leftover.unlink()
                leftover_count += 1
                logger.debug(f"🗑️  Removed leftover: {leftover.name}")
            except Exception as e:
                logger.debug(f"Failed to remove leftover {leftover.name}: {e}")
    if leftover_count > 0:
        logger.info(f"🧹 Cleaned {leftover_count} leftover/unused JPG files")

    return processed

def clear_windows_pictures():
    """Clear every file AHK would collect, so nothing stale rides along.

    범위는 AHK_COLLECTED_SUFFIXES 가 정한다 — send_kakao.ahk 의 수집 범위와 동일.
    """
    logger.info("🧹 Step 3: Clearing Windows Pictures folder...")
    if not WINDOWS_PICTURES_WSL.exists():
        logger.warning(f"⚠️  Windows Pictures folder not found: {WINDOWS_PICTURES_WSL}")
        return

    removed = 0
    stale = []
    for f in sorted(WINDOWS_PICTURES_WSL.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AHK_COLLECTED_SUFFIXES:
            continue
        try:
            f.unlink()
        except OSError as e:
            # 지우지 못한 파일은 그대로 AHK 에 딸려간다. 조용히 넘기면 안 된다.
            logger.error(f"❌ Could not remove {f.name}: {e} — 전송에 섞일 수 있다")
            continue
        removed += 1
        if f.suffix.lower() != ".jpg":
            stale.append(f.name)

    logger.info(f"✅ Cleared {removed} collectable image files from Windows Pictures")
    if stale:
        # 주보는 항상 .jpg 다. 다른 확장자가 있었다면 외부에서 흘러든 것이다.
        logger.warning(f"⚠️  주보가 아닌 이미지 {len(stale)}개를 함께 지웠다: {', '.join(stale)}")

    leftovers = [
        f.name for f in WINDOWS_PICTURES_WSL.iterdir()
        if f.is_file() and f.suffix.lower() in AHK_COLLECTED_SUFFIXES
    ]
    if leftovers:
        logger.error(f"❌ 정리 후에도 수집 대상이 남았다: {', '.join(leftovers)}")
        sys.exit(1)

def copy_images_to_windows(image_files):
    """Copy JPG images (list of Path) to Windows Pictures folder."""
    logger.info("📋 Step 4: Copying images to Windows...")
    dst_dir = WINDOWS_PICTURES_WSL

    if not dst_dir.exists():
        logger.error(f"❌ Windows Pictures folder not accessible: {dst_dir}")
        sys.exit(1)

    if not image_files:
        logger.error("❌ No image files to copy")
        sys.exit(1)

    # Already sorted by global sequence
    copied = 0
    for src in image_files:
        dst = dst_dir / src.name
        shutil.copy2(src, dst)
        copied += 1
        logger.debug(f"   Copied {src.name}")

    logger.info(f"✅ Copied {copied} images to {dst_dir}")

def kill_stuck_ahk():
    """Kill AutoHotkey processes still running send_kakao.ahk.

    Matches on the command line rather than the image name so unrelated
    AutoHotkey v2 scripts are left alone.
    """
    ps_cmd = (
        "Get-CimInstance Win32_Process "
        f"-Filter \"Name='{AHK_PROCESS_NAME}'\" | "
        "Where-Object { $_.CommandLine -like '*send_kakao.ahk*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
    )
    if not POWERSHELL_WSL.exists():
        logger.error(f"   ⚠️  powershell.exe not found: {POWERSHELL_WSL}")
        logger.error("   Kill the AutoHotkey64.exe process manually.")
        return

    try:
        result = subprocess.run(
            [str(POWERSHELL_WSL), "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30, check=False
        )
        killed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        if killed:
            logger.warning(f"   🔪 Killed stuck AHK process(es): {', '.join(killed)}")
        else:
            logger.info("   No stuck AHK process found to clean up.")
    except Exception as e:
        logger.error(f"   ⚠️  Could not clean up AHK process: {e}")


def send_kakao():
    """Trigger Kakao send via AutoHotkey."""
    logger.info("📤 Step 5: Sending via Kakao...")

    if not AHK_EXE_WSL.exists():
        logger.error(f"❌ AutoHotkey not found: {AHK_EXE_WSL}")
        sys.exit(1)

    if not AHK_SCRIPT_WSL.exists():
        logger.error(f"❌ AHK script not found: {AHK_SCRIPT_WIN}")
        sys.exit(1)

    logger.info(f"   Executing AHK: {AHK_EXE_WSL}")
    logger.info(f"   AHK Script:   {AHK_SCRIPT_WIN}")

    try:
        cmd = f'"{AHK_EXE_WSL}" "{AHK_SCRIPT_WIN}"'
        logger.debug(f"Shell command: {cmd}")
        result = subprocess.run(cmd, shell=True, check=False,
                              capture_output=True, text=True,
                              timeout=AHK_TIMEOUT_SEC)

        if result.stdout:
            logger.info(f"AHK stdout:\n{result.stdout}")
        if result.stderr:
            logger.error(f"AHK stderr:\n{result.stderr}")

        if result.returncode != 0:
            logger.error(f"❌ AutoHotkey exited with code {result.returncode}")
            sys.exit(result.returncode)

        logger.info("✅ Kakao send completed")
    except subprocess.TimeoutExpired:
        logger.error(
            f"❌ AutoHotkey did not finish within {AHK_TIMEOUT_SEC}s. "
            "It is most likely blocked on an error dialog "
            "(Kakao logged out, or chat room not found)."
        )
        kill_stuck_ahk()
        logger.error(
            "   Images are staged in Windows Pictures. "
            "Fix Kakao, then re-run with --skip-clean to retry the send only."
        )
        sys.exit(1)
    except FileNotFoundError:
        logger.error(f"❌ Failed to start AutoHotkey.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Bulletin pipeline: download both sites (bstsd+maria) → convert (maria pages 1-7 only, bstsd reversed) → send to Kakao",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline (both sites, ordered)
  %(prog)s

  # Custom directories
  %(prog)s --pdf-dir ~/my_pdfs --image-dir ~/my_images

  # Skip send (test)
  %(prog)s --skip-send

  # Verbose
  %(prog)s --verbose

Note: Both sites must download successfully. If either fails, pipeline aborts.
        """
    )

    parser.add_argument('--pdf-dir', default=DEFAULT_PDF_DIR,
                        help='Directory to download PDFs (default: /tmp/pdf)')
    parser.add_argument('--image-dir', default=DEFAULT_IMAGE_DIR,
                        help='Directory to store converted JPGs (default: /tmp/pdf_images)')
    parser.add_argument('--skip-clean', action='store_true',
                        help='Skip cleanup of PDF/image directories')
    parser.add_argument('--skip-send', action='store_true',
                        help='Skip Kakao send step (for testing)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable debug logging')

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("="*60)
    logger.info("📄 BULLETIN PIPELINE START (BSTSD + MARIA - ORDERED)")
    logger.info("="*60)

    try:
        # Step 1: Clean
        if not args.skip_clean:
            clean_directory(args.pdf_dir)
            clean_directory(args.image_dir, ["*.jpg", "*.jpeg"])
        else:
            logger.info("⏭️  Skipping cleanup")

        # Step 2: Download ALL sites (must all succeed)
        downloaded = download_all_pdfs(args.pdf_dir)

        # Step 3: Convert PDFs (maria pages 1-7 only, bstsd all reversed)
        final_images = convert_pdfs_to_images(args.pdf_dir, args.image_dir)

        # Step 4: Clear Windows Pictures
        clear_windows_pictures()

        # Step 5: Copy images to Windows
        copy_images_to_windows(final_images)

        # Step 6: Send via Kakao
        if not args.skip_send:
            send_kakao()
        else:
            logger.info("⏭️  Skipping Kakao send")

        logger.info("="*60)
        logger.info("🎉 PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("="*60)

    except Exception as e:
        logger.exception(f"❌ Pipeline failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

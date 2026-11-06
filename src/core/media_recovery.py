"""
Dedicated recovery pipeline for deleted/lost photos and videos.

Combines:
  1. NTFS $MFT deleted entries with media extensions or image/video content
  2. Recycle Bin media files
  3. Aggressive signature carving tuned for JPEG, PNG, GIF, WebP, BMP, MP4, MOV, AVI

Validates recovered image bytes with Pillow when available so false positives
are filtered before they appear in the results list.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Callable, List, Optional, Set

from .scanner import RecoverableItem, RecoveryScanner
from .signatures import get_image_signatures, get_video_signatures
from .carver import FileCarver, CarvedFile

logger = logging.getLogger("Zolvagraph")

ProgressCB = Optional[Callable[[float, str], None]]

MEDIA_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".3gp", ".webm",
}


def _is_media_name(name: str) -> bool:
    return Path(name).suffix.lower() in MEDIA_EXTENSIONS


def validate_image_bytes(data: bytes) -> bool:
    """Return True if Pillow (or header checks) accept the data as an image."""
    if not data or len(data) < 16:
        return False
    # Fast header checks
    if data[:3] == b"\xFF\xD8\xFF":
        return b"\xFF\xD9" in data or len(data) > 128
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return b"IHDR" in data[8:32]
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data[:2] == b"BM":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        img.verify()
        return True
    except Exception:
        return False


def validate_video_bytes(data: bytes) -> bool:
    if not data or len(data) < 12:
        return False
    if data[4:8] == b"ftyp":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return True
    if data[:4] == b"\x1A\x45\xDF\xA3":  # EBML / MKV
        return True
    if data[:3] == b"FLV":
        return True
    return False


def refine_jpeg_size(data: bytes, max_size: int) -> int:
    """Find last valid EOI marker within limit for tighter JPEG extraction."""
    limit = min(len(data), max_size)
    # Search from start for SOS then EOI; take last EOI after first SOS if possible
    eoi = data.rfind(b"\xFF\xD9", 0, limit)
    if eoi != -1 and eoi > 20:
        return eoi + 2
    return min(limit, max_size)


def refine_png_size(data: bytes, max_size: int) -> int:
    limit = min(len(data), max_size)
    if len(data) < 24:
        return limit
    pos = 8
    while pos + 12 <= limit:
        length = int.from_bytes(data[pos: pos + 4], "big")
        if length < 0 or length > 50_000_000:
            break
        chunk_type = data[pos + 4: pos + 8]
        pos += 12 + length
        if chunk_type == b"IEND":
            return min(pos, limit)
    # fallback: search IEND trailer
    idx = data.find(b"IEND\xaeB`\x82", 0, limit)
    if idx != -1:
        return idx + 8
    return min(limit, max_size)


def refine_mp4_size(data: bytes, max_size: int) -> int:
    """Walk top-level boxes to estimate MP4/MOV length."""
    limit = min(len(data), max_size)
    pos = 0
    last_end = 0
    while pos + 8 <= limit:
        size = int.from_bytes(data[pos: pos + 4], "big")
        typ = data[pos + 4: pos + 8]
        if size == 0:
            # extends to EOF — take remaining capped
            return min(limit, max_size)
        if size == 1 and pos + 16 <= limit:
            size = int.from_bytes(data[pos + 8: pos + 16], "big")
        if size < 8 or pos + size > limit + 1024 * 1024:
            break
        if not all(32 <= b < 127 for b in typ):
            break
        last_end = pos + size
        pos = last_end
        if last_end >= limit:
            break
    if last_end >= 32:
        return min(last_end, max_size)
    return min(max(limit, 1024 * 1024), max_size)


class MediaCarver(FileCarver):
    """Carver specialized for photos and videos with tighter size refinement."""

    def __init__(self, progress_callback=None, max_files: int = 20_000):
        sigs = get_image_signatures() + get_video_signatures()
        super().__init__(signatures=sigs, progress_callback=progress_callback, max_files=max_files)

    def _estimate_size(self, data: bytes, footer, max_size: int, name: str) -> int:
        if name == "JPEG":
            return refine_jpeg_size(data, max_size)
        if name == "PNG":
            return refine_png_size(data, max_size)
        if name in ("MP4", "MOV"):
            return refine_mp4_size(data, max_size)
        if name == "BMP" and len(data) >= 6:
            declared = int.from_bytes(data[2:6], "little")
            if 14 <= declared <= min(len(data), max_size):
                return declared
        if name == "WebP" and len(data) >= 12:
            # RIFF size at offset 4 is size of file minus 8
            riff_size = int.from_bytes(data[4:8], "little") + 8
            if 12 <= riff_size <= max_size:
                return min(riff_size, len(data), max_size)
        if name == "AVI" and len(data) >= 12:
            riff_size = int.from_bytes(data[4:8], "little") + 8
            if 12 <= riff_size <= max_size:
                return min(riff_size, len(data), max_size)
        return super()._estimate_size(data, footer, max_size, name)


def filter_and_validate_media(items: List[RecoverableItem]) -> List[RecoverableItem]:
    """Keep media items; boost confidence when bytes validate as real images/videos."""
    out: List[RecoverableItem] = []
    for it in items:
        is_media = it.file_type in ("image", "video") or _is_media_name(it.name)
        if not is_media:
            # keep if data validates as media anyway (carved without type)
            if it.data and (validate_image_bytes(it.data) or validate_video_bytes(it.data)):
                it.file_type = "image" if validate_image_bytes(it.data) else "video"
                is_media = True
        if not is_media:
            continue

        if it.data:
            if it.file_type == "image" or (it.data[:3] == b"\xFF\xD8\xFF" or it.data[:8] == b"\x89PNG\r\n\x1a\n"):
                if validate_image_bytes(it.data):
                    it.confidence = min(0.99, max(it.confidence, 0.85))
                    it.file_type = "image"
                else:
                    # likely false positive carve
                    if it.source == "carved" and it.confidence < 0.7:
                        continue
            elif it.file_type == "video" or (len(it.data) > 12 and it.data[4:8] == b"ftyp"):
                if validate_video_bytes(it.data):
                    it.confidence = min(0.99, max(it.confidence, 0.8))
                    it.file_type = "video"

        out.append(it)
    # Prefer items with recoverable data
    out.sort(key=lambda x: (-int(bool(x.data or x.original_path)), -x.confidence, x.name.lower()))
    return out


class MediaRecoveryEngine:
    """
    End-to-end recovery of deleted/lost pictures and videos from a Windows
    volume, disk image, or folder.
    """

    def __init__(self, scanner: RecoveryScanner, progress: ProgressCB = None):
        self.scanner = scanner
        self.progress = progress
        self.carver = MediaCarver(progress_callback=progress)

    def _report(self, p: float, msg: str) -> None:
        if self.progress:
            self.progress(p, msg)
        logger.info(msg)

    def recover_media(self, target: str) -> List[RecoverableItem]:
        """
        Full media recovery pass:
          Phase 1 – NTFS deleted media
          Phase 2 – Recycle Bin media
          Phase 3 – Aggressive media signature carve
        """
        combined: List[RecoverableItem] = []

        # Phase 1: NTFS deleted
        self._report(0.02, "Phase 1/3 – Scanning NTFS for deleted photos & videos…")
        try:
            ntfs_items = self.scanner.scan_ntfs_deleted(target)
            media_ntfs = [
                it for it in ntfs_items
                if it.file_type in ("image", "video") or _is_media_name(it.name)
            ]
            combined.extend(media_ntfs)
            self._report(0.33, f"NTFS: {len(media_ntfs)} deleted media file(s)")
        except Exception as e:
            logger.warning("NTFS media phase: %s", e)
            self._report(0.33, f"NTFS phase skipped: {e}")

        if self.scanner._stop:
            return filter_and_validate_media(combined)

        # Phase 2: Recycle Bin
        self._report(0.35, "Phase 2/3 – Recycle Bin photos & videos…")
        try:
            rb = self.scanner.scan_recycle_bin()
            media_rb = [
                it for it in rb
                if it.file_type in ("image", "video") or _is_media_name(it.name)
            ]
            combined.extend(media_rb)
            self._report(0.55, f"Recycle Bin: {len(media_rb)} media file(s)")
        except Exception as e:
            logger.warning("Recycle media phase: %s", e)

        if self.scanner._stop:
            return filter_and_validate_media(combined)

        # Phase 3: Signature carve (media only, improved carver)
        self._report(0.58, "Phase 3/3 – Carving lost photos & videos from disk data…")
        try:
            from .disk_access import open_source
            stream, size = open_source(target)
            try:
                carved = self.carver.carve_stream(stream, size, source_name=Path(target).name)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

            for c in carved:
                ftype = "image" if c.name in ("JPEG", "PNG", "GIF", "BMP", "TIFF", "WebP") else "video"
                # Validate before adding
                ok = validate_image_bytes(c.data) if ftype == "image" else validate_video_bytes(c.data)
                conf = c.confidence
                if ok:
                    conf = min(0.99, max(conf, 0.82))
                elif conf < 0.55:
                    continue
                combined.append(RecoverableItem(
                    id=f"media_{c.offset:012X}",
                    name=c.display_name,
                    path=f"{target}@0x{c.offset:X}",
                    size=c.size,
                    file_type=ftype,
                    source="carved",
                    confidence=conf,
                    offset=c.offset,
                    data=c.data,
                ))
            self._report(0.95, f"Carve: found media candidates")
        except Exception as e:
            logger.warning("Media carve phase: %s", e)
            self._report(0.95, f"Carve phase issue: {e}")

        result = filter_and_validate_media(combined)
        # Deduplicate by (name, size) roughly
        seen = set()
        unique: List[RecoverableItem] = []
        for it in result:
            key = (it.name.lower(), it.size, it.source)
            if key in seen:
                continue
            seen.add(key)
            unique.append(it)

        self._report(1.0, f"Media recovery complete – {len(unique)} photo/video file(s)")
        return unique

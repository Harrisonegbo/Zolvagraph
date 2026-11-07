"""
Python bindings for the Zolvagraph native C scan engine.

Falls back to pure-Python search if the shared library is not available.
The C engine uses Boyer-Moore-Horspool + specialized 3/4-byte finders for
high-throughput multi-signature scanning of large buffers.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger("Zolvagraph")

# Match layout must mirror scan_engine.c
class ZgMatch(ctypes.Structure):
    _fields_ = [
        ("offset", ctypes.c_uint64),
        ("pattern_id", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


_lib = None
_engine_cls = None


def _candidate_lib_paths() -> List[Path]:
    here = Path(__file__).resolve()
    roots = [
        here.parents[2] / "native",  # project/native
        here.parents[1] / "native",
        Path.cwd() / "native",
        Path(sys.executable).resolve().parent / "native",
        Path(sys.executable).resolve().parent,
    ]
    names = [
        "libzolvagraph_scan.so",
        "zolvagraph_scan.dll",
        "libzolvagraph_scan.dylib",
    ]
    paths = []
    for root in roots:
        for name in names:
            paths.append(root / name)
    return paths


def load_native() -> bool:
    global _lib
    if _lib is not None:
        return True
    for path in _candidate_lib_paths():
        if not path.is_file():
            continue
        try:
            _lib = ctypes.CDLL(str(path))
            _lib.zg_engine_create.restype = ctypes.c_void_p
            _lib.zg_engine_destroy.argtypes = [ctypes.c_void_p]
            _lib.zg_engine_add_pattern.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32
            ]
            _lib.zg_engine_add_pattern.restype = ctypes.c_int
            _lib.zg_engine_clear_patterns.argtypes = [ctypes.c_void_p]
            _lib.zg_engine_scan.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_size_t,
                ctypes.c_uint64,
                ctypes.POINTER(ZgMatch),
                ctypes.c_int,
            ]
            _lib.zg_engine_scan.restype = ctypes.c_int
            _lib.zg_engine_version.restype = ctypes.c_char_p
            ver = _lib.zg_engine_version()
            logger.info("Native scan engine loaded: %s (%s)", path.name, ver.decode() if ver else "?")
            return True
        except OSError as e:
            logger.debug("Failed loading %s: %s", path, e)
            _lib = None
    logger.info("Native scan engine not found – using pure-Python search")
    return False


class NativeScanner:
    """
    Multi-pattern scanner. patterns: list of (pattern_bytes, pattern_id).
    """

    def __init__(self, patterns: Sequence[Tuple[bytes, int]]):
        self.patterns = [(p if isinstance(p, bytes) else bytes(p), int(pid)) for p, pid in patterns]
        self._eng = None
        if load_native() and _lib is not None:
            self._eng = _lib.zg_engine_create()
            if self._eng:
                for pat, pid in self.patterns:
                    rc = _lib.zg_engine_add_pattern(self._eng, pat, len(pat), pid)
                    if rc != 0:
                        logger.warning("add_pattern failed for id=%s rc=%s", pid, rc)

    def close(self) -> None:
        if self._eng and _lib is not None:
            _lib.zg_engine_destroy(self._eng)
            self._eng = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @property
    def using_native(self) -> bool:
        return self._eng is not None

    def scan(self, data: bytes, base_offset: int = 0, max_matches: int = 100_000) -> List[Tuple[int, int]]:
        """
        Returns list of (absolute_offset, pattern_id).
        """
        if not data:
            return []
        if self._eng and _lib is not None:
            return self._scan_native(data, base_offset, max_matches)
        return self._scan_python(data, base_offset, max_matches)

    def _scan_native(self, data: bytes, base_offset: int, max_matches: int) -> List[Tuple[int, int]]:
        assert _lib is not None and self._eng is not None
        out_n = min(max_matches, 200_000)
        arr = (ZgMatch * out_n)()
        # ctypes needs a c_char_p-compatible buffer; use create_string_buffer for large data
        buf = ctypes.create_string_buffer(data, len(data))
        n = _lib.zg_engine_scan(
            self._eng,
            ctypes.cast(buf, ctypes.c_char_p),
            len(data),
            ctypes.c_uint64(base_offset),
            arr,
            out_n,
        )
        if n < 0:
            return self._scan_python(data, base_offset, max_matches)
        return [(int(arr[i].offset), int(arr[i].pattern_id)) for i in range(n)]

    def _scan_python(self, data: bytes, base_offset: int, max_matches: int) -> List[Tuple[int, int]]:
        hits: List[Tuple[int, int]] = []
        for pat, pid in self.patterns:
            start = 0
            while len(hits) < max_matches:
                idx = data.find(pat, start)
                if idx < 0:
                    break
                hits.append((base_offset + idx, pid))
                start = idx + 1
        return hits


def native_available() -> bool:
    return load_native()

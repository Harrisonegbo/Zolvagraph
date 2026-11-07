# Zolvagraph Native Scan Engine

High-performance multi-signature scanner written in C (Boyer–Moore–Horspool + fast 3/4-byte finders).

## Build

```bash
cd native
make          # Linux/macOS → libzolvagraph_scan.so
# or
gcc -O3 -fPIC -shared -o libzolvagraph_scan.so scan_engine.c
```

Windows (MinGW):

```bash
gcc -O3 -shared -o zolvagraph_scan.dll scan_engine.c
```

Place the library next to the app or under `native/` so Python `ctypes` can load it.

## Integration

Python loads the library via `src/core/native_scan.py`. If the library is missing, Zolvagraph falls back to pure-Python `bytes.find` automatically.

## Scope

This accelerates **header discovery** during carving. Full forensic lab platforms used by law enforcement also include validated write-blockers, evidence databases, and formal tool testing (e.g. NIST CFTT). Zolvagraph is a high-performance open-source recovery suite, not a certified replacement for those systems.

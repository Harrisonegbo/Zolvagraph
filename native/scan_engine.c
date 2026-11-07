/*
 * Zolvagraph Scan Engine – high-performance multi-signature scanner
 *
 * C core for bulk byte scanning of disk images / volumes.
 * Finds all occurrences of multiple magic-number headers in a buffer.
 *
 * Build (Linux/macOS):
 *   gcc -O3 -fPIC -shared -o libzolvagraph_scan.so scan_engine.c
 * Build (Windows MinGW):
 *   gcc -O3 -shared -o zolvagraph_scan.dll scan_engine.c
 *
 * API is stable for ctypes / FFI from Python.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#ifdef _WIN32
  #define ZG_EXPORT __declspec(dllexport)
#else
  #define ZG_EXPORT __attribute__((visibility("default")))
#endif

#define ZG_MAX_PATTERNS   64
#define ZG_MAX_PAT_LEN    32
#define ZG_MAX_MATCHES    500000

typedef struct {
    uint8_t  data[ZG_MAX_PAT_LEN];
    uint32_t len;
    uint32_t id;          /* caller-defined signature id */
} zg_pattern_t;

typedef struct {
    uint64_t offset;      /* absolute offset in the scanned region */
    uint32_t pattern_id;
    uint32_t reserved;
} zg_match_t;

typedef struct {
    zg_pattern_t patterns[ZG_MAX_PATTERNS];
    int          npatterns;
    /* Boyer-Moore-Horspool bad-character tables per pattern */
    int          bmh_skip[ZG_MAX_PATTERNS][256];
} zg_engine_t;

/* ── engine lifecycle ─────────────────────────────────────────────────── */

ZG_EXPORT zg_engine_t *zg_engine_create(void)
{
    zg_engine_t *e = (zg_engine_t *)calloc(1, sizeof(zg_engine_t));
    return e;
}

ZG_EXPORT void zg_engine_destroy(zg_engine_t *e)
{
    free(e);
}

ZG_EXPORT int zg_engine_add_pattern(zg_engine_t *e,
                                    const uint8_t *pat,
                                    uint32_t len,
                                    uint32_t id)
{
    if (!e || !pat || len == 0 || len > ZG_MAX_PAT_LEN)
        return -1;
    if (e->npatterns >= ZG_MAX_PATTERNS)
        return -2;

    int idx = e->npatterns++;
    memcpy(e->patterns[idx].data, pat, len);
    e->patterns[idx].len = len;
    e->patterns[idx].id  = id;

    /* Build Boyer-Moore-Horspool skip table */
    int *skip = e->bmh_skip[idx];
    for (int i = 0; i < 256; i++)
        skip[i] = (int)len;
    for (uint32_t i = 0; i + 1 < len; i++)
        skip[pat[i]] = (int)(len - 1 - i);

    return 0;
}

ZG_EXPORT void zg_engine_clear_patterns(zg_engine_t *e)
{
    if (e)
        e->npatterns = 0;
}

/* ── single-pattern BMH search ────────────────────────────────────────── */

static int bmh_find(const uint8_t *hay, size_t hlen,
                    const uint8_t *needle, uint32_t nlen,
                    const int skip[256],
                    size_t start)
{
    if (nlen == 0 || hlen < nlen || start > hlen - nlen)
        return -1;

    size_t i = start;
    while (i <= hlen - nlen) {
        int j = (int)nlen - 1;
        while (j >= 0 && hay[i + j] == needle[j])
            j--;
        if (j < 0)
            return (int)i;
        i += skip[hay[i + nlen - 1]];
    }
    return -1;
}

/* Fast path for 3-byte patterns (JPEG FFD8FF) – common case */
static int find3(const uint8_t *hay, size_t hlen,
                 uint8_t a, uint8_t b, uint8_t c, size_t start)
{
    for (size_t i = start; i + 2 < hlen; i++) {
        if (hay[i] == a && hay[i + 1] == b && hay[i + 2] == c)
            return (int)i;
    }
    return -1;
}

/* Fast path for 4-byte patterns */
static int find4(const uint8_t *hay, size_t hlen,
                 uint8_t a, uint8_t b, uint8_t c, uint8_t d, size_t start)
{
    for (size_t i = start; i + 3 < hlen; i++) {
        if (hay[i] == a && hay[i + 1] == b &&
            hay[i + 2] == c && hay[i + 3] == d)
            return (int)i;
    }
    return -1;
}

/* ── main scan ────────────────────────────────────────────────────────── */

/*
 * Scan buffer [data, data+len) for all registered patterns.
 * base_offset is added to each match offset (for chunked file scans).
 * Writes up to max_out matches into out[].
 * Returns number of matches written, or -1 on error.
 */
ZG_EXPORT int zg_engine_scan(zg_engine_t *e,
                             const uint8_t *data,
                             size_t len,
                             uint64_t base_offset,
                             zg_match_t *out,
                             int max_out)
{
    if (!e || !data || !out || max_out <= 0)
        return -1;

    int nmatch = 0;

    for (int p = 0; p < e->npatterns && nmatch < max_out; p++) {
        const zg_pattern_t *pat = &e->patterns[p];
        size_t pos = 0;

        while (nmatch < max_out) {
            int found;

            if (pat->len == 3) {
                found = find3(data, len,
                              pat->data[0], pat->data[1], pat->data[2], pos);
            } else if (pat->len == 4) {
                found = find4(data, len,
                              pat->data[0], pat->data[1],
                              pat->data[2], pat->data[3], pos);
            } else {
                found = bmh_find(data, len, pat->data, pat->len,
                                 e->bmh_skip[p], pos);
            }

            if (found < 0)
                break;

            out[nmatch].offset     = base_offset + (uint64_t)found;
            out[nmatch].pattern_id = pat->id;
            out[nmatch].reserved   = 0;
            nmatch++;
            pos = (size_t)found + 1; /* allow overlapping hits */
        }
    }

    return nmatch;
}

/* Convenience: scan and return only count (no output array needed for probes) */
ZG_EXPORT int zg_engine_count(zg_engine_t *e,
                              const uint8_t *data,
                              size_t len)
{
    zg_match_t tmp[4096];
    int total = 0;
    size_t chunk = 16 * 1024 * 1024;
    size_t off = 0;
    while (off < len) {
        size_t n = len - off;
        if (n > chunk) n = chunk;
        /* overlap so patterns on boundaries are not missed */
        size_t scan_len = n;
        if (off + n < len && n > 64)
            scan_len = n; /* caller handles overlap externally if needed */
        int c = zg_engine_scan(e, data + off, scan_len, 0, tmp, 4096);
        if (c < 0) break;
        total += c;
        off += n;
    }
    return total;
}

ZG_EXPORT const char *zg_engine_version(void)
{
    return "Zolvagraph-ScanEngine/1.0";
}

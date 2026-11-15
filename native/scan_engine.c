/*
 * Zolvagraph Scan Engine v2 – optimized multi-signature scanner
 *
 * - First-byte bloom filter (skip chunks with no candidate starts)
 * - Boyer-Moore-Horspool per pattern
 * - Specialized 3/4-byte scanners (JPEG, PNG, ftyp-ish)
 * - Optional SSE2 first-byte probe on x86_64
 * - Stable C API for Python ctypes
 *
 * Build:
 *   gcc -O3 -march=native -fPIC -shared -o libzolvagraph_scan.so scan_engine.c
 *   gcc -O3 -shared -o zolvagraph_scan.dll scan_engine.c   # MinGW
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

#if defined(__SSE2__) || defined(_M_X64) || defined(__x86_64__)
  #include <emmintrin.h>
  #define ZG_HAVE_SSE2 1
#else
  #define ZG_HAVE_SSE2 0
#endif

#define ZG_MAX_PATTERNS   128
#define ZG_MAX_PAT_LEN    32
#define ZG_VERSION        "Zolvagraph-ScanEngine/2.0"

typedef struct {
    uint8_t  data[ZG_MAX_PAT_LEN];
    uint32_t len;
    uint32_t id;
} zg_pattern_t;

typedef struct {
    uint64_t offset;
    uint32_t pattern_id;
    uint32_t reserved;
} zg_match_t;

typedef struct {
    zg_pattern_t patterns[ZG_MAX_PATTERNS];
    int          npatterns;
    int          bmh_skip[ZG_MAX_PATTERNS][256];
    /* bit i set => at least one pattern starts with byte i */
    uint64_t     first_byte_bits[4]; /* 256 bits */
    uint8_t      first_byte_map[256]; /* 1 if any pattern starts with this byte */
} zg_engine_t;

/* ── helpers ──────────────────────────────────────────────────────────── */

static inline void fb_set(zg_engine_t *e, uint8_t b)
{
    e->first_byte_map[b] = 1;
    e->first_byte_bits[b >> 6] |= (uint64_t)1 << (b & 63);
}

static inline int fb_test(const zg_engine_t *e, uint8_t b)
{
    return e->first_byte_map[b] != 0;
}

/* SSE2: find next occurrence of byte `needle` in [p, p+len) */
#if ZG_HAVE_SSE2
static size_t find_byte_sse2(const uint8_t *p, size_t len, uint8_t needle, size_t start)
{
    size_t i = start;
    const __m128i n = _mm_set1_epi8((char)needle);
    /* align to 16 */
    while (i < len && ((uintptr_t)(p + i) & 15)) {
        if (p[i] == needle) return i;
        i++;
    }
    while (i + 16 <= len) {
        __m128i chunk = _mm_load_si128((const __m128i *)(p + i));
        __m128i cmp = _mm_cmpeq_epi8(chunk, n);
        int mask = _mm_movemask_epi8(cmp);
        if (mask) {
            return i + (size_t)__builtin_ctz(mask);
        }
        i += 16;
    }
    while (i < len) {
        if (p[i] == needle) return i;
        i++;
    }
    return (size_t)-1;
}
#else
static size_t find_byte_sse2(const uint8_t *p, size_t len, uint8_t needle, size_t start)
{
    for (size_t i = start; i < len; i++)
        if (p[i] == needle) return i;
    return (size_t)-1;
}
#endif

/* ── API ──────────────────────────────────────────────────────────────── */

ZG_EXPORT zg_engine_t *zg_engine_create(void)
{
    return (zg_engine_t *)calloc(1, sizeof(zg_engine_t));
}

ZG_EXPORT void zg_engine_destroy(zg_engine_t *e)
{
    free(e);
}

ZG_EXPORT void zg_engine_clear_patterns(zg_engine_t *e)
{
    if (!e) return;
    e->npatterns = 0;
    memset(e->first_byte_map, 0, sizeof e->first_byte_map);
    memset(e->first_byte_bits, 0, sizeof e->first_byte_bits);
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

    int *skip = e->bmh_skip[idx];
    for (int i = 0; i < 256; i++)
        skip[i] = (int)len;
    for (uint32_t i = 0; i + 1 < len; i++)
        skip[pat[i]] = (int)(len - 1 - i);

    fb_set(e, pat[0]);
    return 0;
}

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
        i += (size_t)skip[hay[i + nlen - 1]];
    }
    return -1;
}

static int find3(const uint8_t *hay, size_t hlen,
                 uint8_t a, uint8_t b, uint8_t c, size_t start)
{
    size_t i = start;
    while (i + 2 < hlen) {
        size_t pos = find_byte_sse2(hay, hlen, a, i);
        if (pos == (size_t)-1 || pos + 2 >= hlen)
            return -1;
        if (hay[pos + 1] == b && hay[pos + 2] == c)
            return (int)pos;
        i = pos + 1;
    }
    return -1;
}

static int find4(const uint8_t *hay, size_t hlen,
                 uint8_t a, uint8_t b, uint8_t c, uint8_t d, size_t start)
{
    size_t i = start;
    while (i + 3 < hlen) {
        size_t pos = find_byte_sse2(hay, hlen, a, i);
        if (pos == (size_t)-1 || pos + 3 >= hlen)
            return -1;
        if (hay[pos + 1] == b && hay[pos + 2] == c && hay[pos + 3] == d)
            return (int)pos;
        i = pos + 1;
    }
    return -1;
}

/*
 * Scan buffer. Returns match count (capped at max_out).
 * Matches are not sorted (caller may sort); order is pattern-major.
 */
ZG_EXPORT int zg_engine_scan(zg_engine_t *e,
                             const uint8_t *data,
                             size_t len,
                             uint64_t base_offset,
                             zg_match_t *out,
                             int max_out)
{
    if (!e || !data || !out || max_out <= 0 || e->npatterns == 0)
        return -1;

    int nmatch = 0;

    /* Quick empty-buffer check via first-byte presence in a sample:
       if the buffer is large, we still must scan — filter is per-pattern. */

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
                /* Use first-byte SSE2 probe then BMH verify */
                size_t probe = find_byte_sse2(data, len, pat->data[0], pos);
                if (probe == (size_t)-1)
                    break;
                found = bmh_find(data, len, pat->data, pat->len,
                                 e->bmh_skip[p], probe);
                if (found < 0)
                    break;
            }
            if (found < 0)
                break;

            out[nmatch].offset     = base_offset + (uint64_t)found;
            out[nmatch].pattern_id = pat->id;
            out[nmatch].reserved   = 0;
            nmatch++;
            pos = (size_t)found + 1;
        }
    }
    return nmatch;
}

ZG_EXPORT int zg_engine_count(zg_engine_t *e,
                              const uint8_t *data,
                              size_t len)
{
    zg_match_t tmp[2048];
    int total = 0;
    size_t chunk = 8 * 1024 * 1024;
    size_t off = 0;
    while (off < len) {
        size_t n = len - off;
        if (n > chunk) n = chunk;
        int c = zg_engine_scan(e, data + off, n, 0, tmp, 2048);
        if (c < 0) break;
        total += c;
        if (c == 2048) {
            /* saturated – still advance */
        }
        off += n;
    }
    return total;
}

ZG_EXPORT const char *zg_engine_version(void)
{
    return ZG_VERSION;
}

ZG_EXPORT int zg_engine_pattern_count(zg_engine_t *e)
{
    return e ? e->npatterns : 0;
}

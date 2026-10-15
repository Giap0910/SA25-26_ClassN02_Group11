#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <limits.h>

typedef struct { int32_t available, reserved, va, vr, quantity; uint32_t action; } Input;
typedef struct { int32_t available, reserved, va, vr; int state, variant; } Stock;

static int32_t java_add(int32_t a, int32_t b) {
    int64_t sum = (int64_t)a + b;
    if (sum > INT32_MAX) sum -= INT64_C(4294967296);
    if (sum < INT32_MIN) sum += INT64_C(4294967296);
    return (int32_t)sum;
}

static int reserve(Stock *s, int32_t q) {
    if (q < 1 || q > 100) return 1;
    if (s->available < q) return 2;
    if ((int64_t)s->reserved + q > INT32_MAX) return 3;
    if (s->variant && s->va < q) return 4;
    if (s->variant && (int64_t)s->vr + q > INT32_MAX) return 5;
    s->available -= q; s->reserved += q;
    if (s->variant) { s->va -= q; s->vr += q; }
    s->state = 1;
    return 0;
}

static int settle(Stock *s, int32_t q, int restore) {
    if (s->state != 1) return 0;
    if (s->reserved < q || (s->variant && s->vr < q)) return 6;
    if (restore && s->variant && (int64_t)s->va + q > INT32_MAX) return 7;
    s->reserved -= q;
    if (restore) s->available = java_add(s->available, q);
    if (s->variant) { s->vr -= q; if (restore) s->va += q; }
    s->state = restore ? 2 : 3;
    return 0;
}

static int simulate(Input in) {
    int variant = (in.action & 8u) != 0;
    Stock s = {in.available, in.reserved, in.va, in.vr, 0, variant};
    if (in.available < 0 || in.reserved < 0 || (variant && (in.va < 0 || in.vr < 0
        || in.available != in.va || in.reserved != in.vr))) {
        printf("{\"status\":\"invalid_fixture\"}\n"); return 0;
    }
    int result = reserve(&s, in.quantity);
    if (!result && (in.action & 3u) != 0) result = settle(&s, in.quantity, (in.action & 3u) == 1);
    if (!result && (in.action & 4u) && (in.action & 3u) != 0)
        result = settle(&s, in.quantity, (in.action & 3u) == 1);
    if (result) s = (Stock){in.available, in.reserved, in.va, in.vr, 0, variant};
    printf("{\"status\":\"%s\",\"code\":%d,\"available\":%" PRId32
        ",\"reserved\":%" PRId32 ",\"variant_available\":%" PRId32
        ",\"variant_reserved\":%" PRId32 ",\"state\":%d}\n",
        result ? "rejected" : "accepted", result, s.available, s.reserved, s.va, s.vr, s.state);
    return s.available < 0 || s.reserved < 0 || (variant && (s.va < 0 || s.vr < 0)) ? 10 : 0;
}

static uint32_t read_u32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int32_t read_i32(const unsigned char *p) {
    uint32_t value = read_u32(p);
    return value <= INT32_MAX ? (int32_t)value : (int32_t)((int64_t)value - INT64_C(4294967296));
}

static int decode(const unsigned char *buf, size_t len) {
    if (len != 28) { puts("{\"status\":\"invalid_length\"}"); return 0; }
    if (buf[0] != 'B') { puts("{\"status\":\"header_0\"}"); return 0; }
    if (buf[1] != 'D') { puts("{\"status\":\"header_1\"}"); return 0; }
    if (buf[2] != 'M') { puts("{\"status\":\"header_2\"}"); return 0; }
    if (buf[3] != 'N') { puts("{\"status\":\"header_3\"}"); return 0; }
    Input in = {read_i32(buf+4), read_i32(buf+8), read_i32(buf+12),
        read_i32(buf+16), read_i32(buf+20), read_u32(buf+24)};
    return simulate(in);
}

int main(int argc, char **argv) {
    if (argc != 2) { fputs("Usage: stock_simulator INPUT_FILE\n", stderr); return 64; }
    FILE *file = fopen(argv[1], "rb");
    if (!file) { perror("input"); return 66; }
    unsigned char buf[29];
    size_t len = fread(buf, 1, sizeof buf, file);
    if (ferror(file)) { fclose(file); return 74; }
    fclose(file);
    return decode(buf, len);
}

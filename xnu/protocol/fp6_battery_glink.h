/* Transport-independent FP6 read-only battery protocol.
 * Wire layout: Fairphone qti_battery_charger.c and pmic_glink.h.
 * Not a driver: caller must supply an authenticated, live ADSP GLINK channel.
 */
#ifndef FP6_BATTERY_GLINK_H
#define FP6_BATTERY_GLINK_H
#include <stddef.h>
#include <stdint.h>

#define FP6_BC_OWNER 32778u
#define FP6_BC_GET_BATTERY 0x30u
#define FP6_BC_GET_USB 0x32u
#define FP6_BC_WIRE_SIZE 24u
enum fp6_bc_property {
    FP6_BC_STATUS = 0, FP6_BC_HEALTH = 1, FP6_BC_PRESENT = 2,
    FP6_BC_CAPACITY = 4, /* hundredths of one percent */
    FP6_BC_VOLTAGE = 7, /* microvolts */
    FP6_BC_CURRENT = 9, /* signed microamps, retained as wire bits */
    FP6_BC_TEMP = 12, /* signed hundredths of Celsius */
    FP6_BC_CHARGE_COUNTER = 14, FP6_BC_CYCLES = 15,
    FP6_BC_DESIGN_CAPACITY = 16, FP6_BC_FULL_CAPACITY = 17
};
enum fp6_bc_result {
    FP6_BC_OK = 0, FP6_BC_BAD_MESSAGE = -1, FP6_BC_REMOTE_ERROR = -2
};
static inline uint32_t fp6_bc_get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline void fp6_bc_put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
/* Only numeric GETs, battery zero and USB port zero. No charger writes. */
static inline int fp6_bc_make_get(uint8_t *out, size_t size,
    uint32_t opcode, uint32_t property)
{
    if (!out || size != FP6_BC_WIRE_SIZE ||
        !((opcode == FP6_BC_GET_BATTERY && property < 18u) ||
          (opcode == FP6_BC_GET_USB && property == 0u)))
        return FP6_BC_BAD_MESSAGE;
    fp6_bc_put32(out, FP6_BC_OWNER); fp6_bc_put32(out + 4, 1);
    fp6_bc_put32(out + 8, opcode); fp6_bc_put32(out + 12, 0);
    fp6_bc_put32(out + 16, property); fp6_bc_put32(out + 20, 0);
    return FP6_BC_OK;
}
/* Serialize requests: protocol has no transaction identifier. A timeout must
 * reset/drain the channel before another request for the same property.
 * Caller must discard cached validity on link/PDR down. Output is unchanged
 * on malformed, mismatched or remote-error replies.
 */
static inline int fp6_bc_parse_reply(const uint8_t *msg, size_t size,
    uint32_t opcode, uint32_t property, uint32_t *value)
{
    if (!msg || !value || size != FP6_BC_WIRE_SIZE ||
        !((opcode == FP6_BC_GET_BATTERY && property < 18u) ||
          (opcode == FP6_BC_GET_USB && property == 0u)) ||
        fp6_bc_get32(msg) != FP6_BC_OWNER || fp6_bc_get32(msg + 4) != 1 ||
        fp6_bc_get32(msg + 8) != opcode ||
        fp6_bc_get32(msg + 12) != property)
        return FP6_BC_BAD_MESSAGE;
    if (fp6_bc_get32(msg + 20) != 0) return FP6_BC_REMOTE_ERROR;
    *value = fp6_bc_get32(msg + 16);
    return FP6_BC_OK;
}
#endif

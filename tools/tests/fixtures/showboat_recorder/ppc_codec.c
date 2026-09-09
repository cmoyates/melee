/* Syntax-only probe of the ACTUAL codec in its native-header translation unit.
 * Not a host stub, executable, target object, MWCC ABI or target runtime test. */
#include <melee/mod/showboat_recorder.c>

#if !defined(__powerpc__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error This probe must be checked with the big-endian PPC target
#endif

typedef char TestBinary32[(sizeof(float) == 4 && sizeof(u32) == 4) ? 1 : -1];
typedef char TestLineCapacity[(sizeof(((SR_Line*) 0)->text) == 1024) ? 1 : -1];

bool ShowboatTest_PPCCodecSyntax(void)
{
    /* Type-check the bounded writer, bit transfer, INT_MIN path and bool emit
     * result against native types. These calls are NEVER executed by tests. */
    SR_Line line;
    SR_Segment segment;
    SR_Sample sample;
    u8 reasons[SBR_TACTICS] = { 1, 4, 7, 10, 13 };
    u32 bits = 0x80000000U;
    float value;
    memset(&line, 0, sizeof(line));
    memset(&segment, 0, sizeof(segment));
    memset(&sample, 0, sizeof(sample));
    line.ok = true;
    memcpy(&value, &bits, sizeof(value));
    SR_F32(&line, &value);
    bits = 0x00000001U;
    memcpy(&value, &bits, sizeof(value));
    SR_F32(&line, &value);
    bits = 0x7f7fffffU;
    memcpy(&value, &bits, sizeof(value));
    SR_F32(&line, &value);
    SR_Int(&line, (-2147483647 - 1));
    SR_UInt(&line, 0xFFFFFFFFU);
    SR_FighterText(&line, &sample.self);
    return SR_Emit(&segment, 0, &sample, 85U, reasons);
}

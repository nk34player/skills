"""PKWARE DCL (implode/explode) ported from StormLib src/pklib (Ladislav Zezula, 2003).

ASCII mode + 4096-byte dictionary reproduces what NI Multisim writes in .ms14/.ewprj.
"""

MAX_REP_LENGTH = 0x204

DistBits = [
    0x02, 0x04, 0x04, 0x05, 0x05, 0x05, 0x05, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06,
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
    0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08,
]

DistCode = [
    0x03, 0x0D, 0x05, 0x19, 0x09, 0x11, 0x01, 0x3E, 0x1E, 0x2E, 0x0E, 0x36, 0x16, 0x26, 0x06, 0x3A,
    0x1A, 0x2A, 0x0A, 0x32, 0x12, 0x22, 0x42, 0x02, 0x7C, 0x3C, 0x5C, 0x1C, 0x6C, 0x2C, 0x4C, 0x0C,
    0x74, 0x34, 0x54, 0x14, 0x64, 0x24, 0x44, 0x04, 0x78, 0x38, 0x58, 0x18, 0x68, 0x28, 0x48, 0x08,
    0xF0, 0x70, 0xB0, 0x30, 0xD0, 0x50, 0x90, 0x10, 0xE0, 0x60, 0xA0, 0x20, 0xC0, 0x40, 0x80, 0x00,
]

ExLenBits = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]

LenBase = [
    0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x0007,
    0x0008, 0x000A, 0x000E, 0x0016, 0x0026, 0x0046, 0x0086, 0x0106,
]

LenBits = [0x03, 0x02, 0x03, 0x03, 0x04, 0x04, 0x04, 0x05, 0x05, 0x05, 0x05, 0x06, 0x06, 0x06, 0x07, 0x07]

LenCode = [0x05, 0x03, 0x01, 0x06, 0x0A, 0x02, 0x0C, 0x14, 0x04, 0x18, 0x08, 0x30, 0x10, 0x20, 0x40, 0x00]

ChBitsAsc = [
    0x0B, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x08, 0x07, 0x0C, 0x0C, 0x07, 0x0C, 0x0C,
    0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0D, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x04, 0x0A, 0x08, 0x0C, 0x0A, 0x0C, 0x0A, 0x08, 0x07, 0x07, 0x08, 0x09, 0x07, 0x06, 0x07, 0x08,
    0x07, 0x06, 0x07, 0x07, 0x07, 0x07, 0x08, 0x07, 0x07, 0x08, 0x08, 0x0C, 0x0B, 0x07, 0x09, 0x0B,
    0x0C, 0x06, 0x07, 0x06, 0x06, 0x05, 0x07, 0x08, 0x08, 0x06, 0x0B, 0x09, 0x06, 0x07, 0x06, 0x06,
    0x07, 0x0B, 0x06, 0x06, 0x06, 0x07, 0x09, 0x08, 0x09, 0x09, 0x0B, 0x08, 0x0B, 0x09, 0x0C, 0x08,
    0x0C, 0x05, 0x06, 0x06, 0x06, 0x05, 0x06, 0x06, 0x06, 0x05, 0x0B, 0x07, 0x05, 0x06, 0x05, 0x05,
    0x06, 0x0A, 0x05, 0x05, 0x05, 0x05, 0x08, 0x07, 0x08, 0x08, 0x0A, 0x0B, 0x0B, 0x0C, 0x0C, 0x0C,
    0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D,
    0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D,
    0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D,
    0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x0D, 0x0C, 0x0D, 0x0D, 0x0D, 0x0C, 0x0D, 0x0D, 0x0D, 0x0C, 0x0D, 0x0D, 0x0D, 0x0D, 0x0C, 0x0D,
    0x0D, 0x0D, 0x0C, 0x0C, 0x0C, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D, 0x0D,
]

ChCodeAsc = [
    0x0490, 0x0FE0, 0x07E0, 0x0BE0, 0x03E0, 0x0DE0, 0x05E0, 0x09E0,
    0x01E0, 0x00B8, 0x0062, 0x0EE0, 0x06E0, 0x0022, 0x0AE0, 0x02E0,
    0x0CE0, 0x04E0, 0x08E0, 0x00E0, 0x0F60, 0x0760, 0x0B60, 0x0360,
    0x0D60, 0x0560, 0x1240, 0x0960, 0x0160, 0x0E60, 0x0660, 0x0A60,
    0x000F, 0x0250, 0x0038, 0x0260, 0x0050, 0x0C60, 0x0390, 0x00D8,
    0x0042, 0x0002, 0x0058, 0x01B0, 0x007C, 0x0029, 0x003C, 0x0098,
    0x005C, 0x0009, 0x001C, 0x006C, 0x002C, 0x004C, 0x0018, 0x000C,
    0x0074, 0x00E8, 0x0068, 0x0460, 0x0090, 0x0034, 0x00B0, 0x0710,
    0x0860, 0x0031, 0x0054, 0x0011, 0x0021, 0x0017, 0x0014, 0x00A8,
    0x0028, 0x0001, 0x0310, 0x0130, 0x003E, 0x0064, 0x001E, 0x002E,
    0x0024, 0x0510, 0x000E, 0x0036, 0x0016, 0x0044, 0x0030, 0x00C8,
    0x01D0, 0x00D0, 0x0110, 0x0048, 0x0610, 0x0150, 0x0060, 0x0088,
    0x0FA0, 0x0007, 0x0026, 0x0006, 0x003A, 0x001B, 0x001A, 0x002A,
    0x000A, 0x000B, 0x0210, 0x0004, 0x0013, 0x0032, 0x0003, 0x001D,
    0x0012, 0x0190, 0x000D, 0x0015, 0x0005, 0x0019, 0x0008, 0x0078,
    0x00F0, 0x0070, 0x0290, 0x0410, 0x0010, 0x07A0, 0x0BA0, 0x03A0,
    0x0240, 0x1C40, 0x0C40, 0x1440, 0x0440, 0x1840, 0x0840, 0x1040,
    0x0040, 0x1F80, 0x0F80, 0x1780, 0x0780, 0x1B80, 0x0B80, 0x1380,
    0x0380, 0x1D80, 0x0D80, 0x1580, 0x0580, 0x1980, 0x0980, 0x1180,
    0x0180, 0x1E80, 0x0E80, 0x1680, 0x0680, 0x1A80, 0x0A80, 0x1280,
    0x0280, 0x1C80, 0x0C80, 0x1480, 0x0480, 0x1880, 0x0880, 0x1080,
    0x0080, 0x1F00, 0x0F00, 0x1700, 0x0700, 0x1B00, 0x0B00, 0x1300,
    0x0DA0, 0x05A0, 0x09A0, 0x01A0, 0x0EA0, 0x06A0, 0x0AA0, 0x02A0,
    0x0CA0, 0x04A0, 0x08A0, 0x00A0, 0x0F20, 0x0720, 0x0B20, 0x0320,
    0x0D20, 0x0520, 0x0920, 0x0120, 0x0E20, 0x0620, 0x0A20, 0x0220,
    0x0C20, 0x0420, 0x0820, 0x0020, 0x0FC0, 0x07C0, 0x0BC0, 0x03C0,
    0x0DC0, 0x05C0, 0x09C0, 0x01C0, 0x0EC0, 0x06C0, 0x0AC0, 0x02C0,
    0x0CC0, 0x04C0, 0x08C0, 0x00C0, 0x0F40, 0x0740, 0x0B40, 0x0340,
    0x0300, 0x0D40, 0x1D00, 0x0D00, 0x1500, 0x0540, 0x0500, 0x1900,
    0x0900, 0x0940, 0x1100, 0x0100, 0x1E00, 0x0E00, 0x0140, 0x1600,
    0x0600, 0x1A00, 0x0E40, 0x0640, 0x0A40, 0x0A00, 0x1200, 0x0200,
    0x1C00, 0x0C00, 0x1400, 0x0400, 0x1800, 0x0800, 0x1000, 0x0000,
]


# ---------------------------------------------------------------- explode ----

def _gen_decode_tabs(start_indexes, length_bits, elements, size=0x100):
    positions = bytearray(size)
    for i in range(elements):
        step = 1 << length_bits[i]
        for index in range(start_indexes[i], size, step):
            positions[index] = i
    return positions


class _DecodeTabs:
    def __init__(self):
        self.ChBitsAsc = list(ChBitsAsc)
        self.offs2C34 = bytearray(0x100)
        self.offs2D34 = bytearray(0x100)
        self.offs2E34 = bytearray(0x80)
        self.offs2EB4 = bytearray(0x100)
        # GenAscTabs
        for count in range(0xFF, -1, -1):
            bits_asc = self.ChBitsAsc[count]
            acc = ChCodeAsc[count]
            if bits_asc <= 8:
                add = 1 << bits_asc
                while acc < 0x100:
                    self.offs2C34[acc] = count
                    acc += add
            elif acc & 0xFF:
                self.offs2C34[acc & 0xFF] = 0xFF
                if acc & 0x3F:
                    bits_asc -= 4
                    self.ChBitsAsc[count] = bits_asc
                    add = 1 << bits_asc
                    acc >>= 4
                    while acc < 0x100:
                        self.offs2D34[acc] = count
                        acc += add
                else:
                    bits_asc -= 6
                    self.ChBitsAsc[count] = bits_asc
                    add = 1 << bits_asc
                    acc >>= 6
                    while acc < 0x80:
                        self.offs2E34[acc] = count
                        acc += add
            else:
                bits_asc -= 8
                self.ChBitsAsc[count] = bits_asc
                add = 1 << bits_asc
                acc >>= 8
                while acc < 0x100:
                    self.offs2EB4[acc] = count
                    acc += add


def explode(src):
    """Decompress one PKWARE DCL implode block."""
    if len(src) <= 4:
        raise ValueError("CMP_BAD_DATA")
    ctype, dsize_bits = src[0], src[1]
    if not 4 <= dsize_bits <= 6:
        raise ValueError("CMP_INVALID_DICTSIZE")
    if ctype not in (0, 1):
        raise ValueError("CMP_INVALID_MODE")

    tabs = _DecodeTabs() if ctype == 1 else None
    LengthCodes = _gen_decode_tabs(LenCode, LenBits, 0x10)
    DistPosCodes = _gen_decode_tabs(DistCode, DistBits, 0x40)
    dsize_mask = 0xFFFF >> (0x10 - dsize_bits)

    out_buff = bytearray(0x2204)
    out_pos = 0x1000
    result = bytearray()

    pos = 3
    bit_buff = src[2]
    extra_bits = 0

    def waste(n):
        nonlocal pos, bit_buff, extra_bits
        if n <= extra_bits:
            extra_bits -= n
            bit_buff >>= n
            return 0
        bit_buff >>= extra_bits
        if pos >= len(src):
            return 1
        bit_buff |= src[pos] << 8
        pos += 1
        bit_buff >>= n - extra_bits
        extra_bits = extra_bits - n + 8
        return 0

    def decode_lit():
        nonlocal bit_buff
        if bit_buff & 1:
            if waste(1):
                return 0x306
            length_code = LengthCodes[bit_buff & 0xFF]
            if waste(LenBits[length_code]):
                return 0x306
            extra = ExLenBits[length_code]
            if extra:
                extra_length = bit_buff & ((1 << extra) - 1)
                if waste(extra):
                    if length_code + extra_length != 0x10E:
                        return 0x306
                length_code = LenBase[length_code] + extra_length
            return length_code + 0x100

        if waste(1):
            return 0x306
        if ctype == 0:
            value = bit_buff & 0xFF
            if waste(8):
                return 0x306
            return value

        if bit_buff & 0xFF:
            value = tabs.offs2C34[bit_buff & 0xFF]
            if value == 0xFF:
                if bit_buff & 0x3F:
                    if waste(4):
                        return 0x306
                    value = tabs.offs2D34[bit_buff & 0xFF]
                else:
                    if waste(6):
                        return 0x306
                    value = tabs.offs2E34[bit_buff & 0x7F]
        else:
            if waste(8):
                return 0x306
            value = tabs.offs2EB4[bit_buff & 0xFF]
        return 0x306 if waste(tabs.ChBitsAsc[value]) else value

    def decode_dist(rep_length):
        nonlocal bit_buff
        code = DistPosCodes[bit_buff & 0xFF]
        if waste(DistBits[code]):
            return 0
        if rep_length == 2:
            distance = (code << 2) | (bit_buff & 0x03)
            if waste(2):
                return 0
        else:
            distance = (code << dsize_bits) | (bit_buff & dsize_mask)
            if waste(dsize_bits):
                return 0
        return distance + 1

    while True:
        lit = decode_lit()
        if lit >= 0x305:
            break
        if lit >= 0x100:
            rep_length = lit - 0xFE
            dist = decode_dist(rep_length)
            if dist == 0:
                raise ValueError("bad distance")
            src_pos = out_pos - dist
            for _ in range(rep_length):
                out_buff[out_pos] = out_buff[src_pos]
                out_pos += 1
                src_pos += 1
        else:
            out_buff[out_pos] = lit
            out_pos += 1

        if out_pos >= 0x2000:
            result += out_buff[0x1000:0x2000]
            out_buff[0:out_pos - 0x1000] = out_buff[0x1000:out_pos]
            out_pos -= 0x1000

    result += out_buff[0x1000:out_pos]
    return bytes(result)


# ---------------------------------------------------------------- implode ----

def implode(data, ctype=1, dsize=0x1000):
    """Compress bytes into one PKWARE DCL implode block (ASCII mode, 4096 dict)."""
    if dsize not in (0x400, 0x800, 0x1000):
        raise ValueError("CMP_INVALID_DICTSIZE")
    if ctype not in (0, 1):
        raise ValueError("CMP_INVALID_MODE")

    if dsize == 0x1000:
        dsize_bits, dsize_mask = 6, 0x3F
    elif dsize == 0x800:
        dsize_bits, dsize_mask = 5, 0x1F
    else:
        dsize_bits, dsize_mask = 4, 0x0F

    nChBits = [0] * 0x306
    nChCodes = [0] * 0x306
    for i in range(0x100):
        if ctype == 0:
            nChBits[i], nChCodes[i] = 9, i * 2
        else:
            nChBits[i] = ChBitsAsc[i] + 1
            nChCodes[i] = ChCodeAsc[i] * 2
    n = 0x100
    for i in range(0x10):
        for k in range(1 << ExLenBits[i]):
            nChBits[n] = ExLenBits[i] + LenBits[i] + 1
            nChCodes[n] = ((k << (LenBits[i] + 1)) | (LenCode[i] * 2) | 1) & 0xFFFF
            n += 1

    work = bytearray(dsize + 0x1000 + MAX_REP_LENGTH + 0x10)
    phash_to_index = [0] * 0x900
    phash_offs = [0] * 0x2400
    offs09BC = [0] * 0x208

    out_buff = bytearray(0x802)
    out_buff[0] = ctype
    out_buff[1] = dsize_bits
    out_bytes = [2]
    out_bits = [0]
    out = bytearray()
    distance = [0]

    def flush_buf():
        out.extend(out_buff[0:0x800])
        save_ch1 = out_buff[0x800]
        save_ch2 = out_buff[out_bytes[0]]
        out_bytes[0] -= 0x800
        out_buff[:] = bytes(0x802)
        if out_bytes[0] != 0:
            out_buff[0] = save_ch1
        if out_bits[0] != 0:
            out_buff[out_bytes[0]] = save_ch2

    def output_bits(nbits, bit_buff):
        if nbits > 8:
            output_bits(8, bit_buff & 0xFF)
            bit_buff >>= 8
            nbits -= 8
        ob = out_bits[0]
        out_buff[out_bytes[0]] |= (bit_buff << ob) & 0xFF
        out_bits[0] += nbits
        if out_bits[0] > 8:
            out_bytes[0] += 1
            bit_buff >>= 8 - ob
            out_buff[out_bytes[0]] = bit_buff & 0xFF
            out_bits[0] &= 7
        else:
            out_bits[0] &= 7
            if out_bits[0] == 0:
                out_bytes[0] += 1
        if out_bytes[0] >= 0x800:
            flush_buf()

    def sort_buffer(bb, be):
        for i in range(0x900):
            phash_to_index[i] = 0
        for p in range(bb, be):
            phash_to_index[work[p] * 4 + work[p + 1] * 5] += 1
        total = 0
        for i in range(0x900):
            total = (total + phash_to_index[i]) & 0xFFFF
            phash_to_index[i] = total
        for p in range(be - 1, bb - 1, -1):
            h = work[p] * 4 + work[p + 1] * 5
            phash_to_index[h] -= 1
            phash_offs[phash_to_index[h]] = p
        for p in range(total, 0x2400):
            phash_offs[p] = 0xFFFF

    def find_rep(inp):
        h = work[inp] * 4 + work[inp + 1] * 5
        min_offs = inp - dsize + 1
        idx = phash_to_index[h]
        while phash_offs[idx] < min_offs:
            idx += 1
        phash_to_index[h] = idx

        prev = phash_offs[idx]
        limit = inp - 1
        if prev >= limit:
            return 0

        rep_length = 1
        while True:
            if work[inp] == work[prev] and work[inp + rep_length - 1] == work[prev + rep_length - 1]:
                pr = prev + 1
                ip = inp + 1
                equal = 2
                while equal < MAX_REP_LENGTH:
                    pr += 1
                    ip += 1
                    if work[pr] != work[ip]:
                        break
                    equal += 1
                if equal >= rep_length:
                    distance[0] = (inp - pr + equal - 1) & 0xFFFFFFFF
                    rep_length = equal
                    if rep_length > 10:
                        break

            idx += 1
            prev = phash_offs[idx]
            if prev >= limit:
                return rep_length if rep_length >= 2 else 0

        if rep_length == MAX_REP_LENGTH:
            distance[0] -= 1
            return rep_length
        if phash_offs[idx + 1] >= limit:
            return rep_length

        # look for a longer match starting later inside the found match
        offs09BC[0] = 0xFFFF
        offs09BC[1] = 0
        di_val = 0
        offs_in_rep = 1
        while offs_in_rep < rep_length:
            if work[inp + offs_in_rep] != work[inp + di_val]:
                di_val = offs09BC[di_val]
                if di_val != 0xFFFF:
                    continue
            offs_in_rep += 1
            di_val = (di_val + 1) & 0xFFFF
            offs09BC[offs_in_rep] = di_val

        prev = phash_offs[idx]
        prev_end = prev + rep_length
        rep_length2 = rep_length

        while True:
            rep_length2 = offs09BC[rep_length2] if rep_length2 <= MAX_REP_LENGTH else 0
            if rep_length2 == 0xFFFF:
                rep_length2 = 0

            while True:
                idx += 1
                prev = phash_offs[idx]
                if prev >= limit:
                    return rep_length
                if prev + rep_length2 >= prev_end:
                    break

            pre_last = work[inp + rep_length - 2]
            if pre_last == work[prev + rep_length - 2]:
                if prev + rep_length2 != prev_end:
                    prev_end = prev
                    rep_length2 = 0
            else:
                while True:
                    idx += 1
                    prev = phash_offs[idx]
                    if prev >= limit:
                        return rep_length
                    if work[prev + rep_length - 2] == pre_last and work[prev] == work[inp]:
                        break
                prev_end = prev + 2
                rep_length2 = 2

            while work[prev_end] == work[inp + rep_length2]:
                rep_length2 += 1
                if rep_length2 >= MAX_REP_LENGTH:
                    break
                prev_end += 1

            if rep_length2 >= rep_length:
                distance[0] = (inp - prev - 1) & 0xFFFFFFFF
                rep_length = rep_length2
                if rep_length == MAX_REP_LENGTH:
                    return rep_length
                while offs_in_rep < rep_length2:
                    if work[inp + offs_in_rep] != work[inp + di_val]:
                        di_val = offs09BC[di_val]
                        if di_val != 0xFFFF:
                            continue
                    offs_in_rep += 1
                    di_val = (di_val + 1) & 0xFFFF
                    offs09BC[offs_in_rep] = di_val

    def emit_rep(rep_length):
        output_bits(nChBits[rep_length + 0xFE], nChCodes[rep_length + 0xFE])
        d = distance[0]
        if rep_length == 2:
            output_bits(DistBits[d >> 2], DistCode[d >> 2])
            output_bits(2, d & 3)
        else:
            output_bits(DistBits[d >> dsize_bits], DistCode[d >> dsize_bits])
            output_bits(dsize_bits, dsize_mask & d)

    read_pos = 0
    inp = dsize + MAX_REP_LENGTH
    phase = 0
    input_ended = False

    while not input_ended:
        room = 0x1000
        loaded = 0
        while room:
            chunk = data[read_pos:read_pos + room]
            if not chunk:
                if loaded == 0 and phase == 0:
                    input_ended = True
                    break
                input_ended = True
                break
            work[dsize + MAX_REP_LENGTH + loaded:dsize + MAX_REP_LENGTH + loaded + len(chunk)] = chunk
            read_pos += len(chunk)
            loaded += len(chunk)
            room -= len(chunk)

        if loaded == 0 and phase == 0:
            break

        input_end = dsize + loaded + (MAX_REP_LENGTH if input_ended else 0)

        if phase == 0:
            sort_buffer(inp, input_end + 1)
            phase = 1
            if dsize != 0x1000:
                phase = 2
        elif phase == 1:
            sort_buffer(inp - dsize + MAX_REP_LENGTH, input_end + 1)
            phase = 2
        else:
            sort_buffer(inp - dsize, input_end + 1)

        while inp < input_end:
            rep_length = find_rep(inp)
            advanced = False
            while rep_length:
                if rep_length == 2 and distance[0] >= 0x100:
                    break
                if input_ended and inp + rep_length > input_end:
                    rep_length = input_end - inp
                    if rep_length < 2:
                        break
                    if rep_length == 2 and distance[0] >= 0x100:
                        break
                elif not (rep_length >= 8 or inp + 1 >= input_end):
                    save_len = rep_length
                    save_dist = distance[0]
                    rep_length = find_rep(inp + 1)
                    if rep_length > save_len and (rep_length > save_len + 1 or save_dist > 0x80):
                        output_bits(nChBits[work[inp]], nChCodes[work[inp]])
                        inp += 1
                        advanced = True
                        continue
                    rep_length = save_len
                    distance[0] = save_dist

                emit_rep(rep_length)
                inp += rep_length
                advanced = True
                break

            if advanced:
                continue
            output_bits(nChBits[work[inp]], nChCodes[work[inp]])
            inp += 1

        if not input_ended:
            inp -= 0x1000
            work[0:dsize + MAX_REP_LENGTH] = work[0x1000:0x1000 + dsize + MAX_REP_LENGTH]

    output_bits(nChBits[0x305], nChCodes[0x305])
    if out_bits[0] != 0:
        out_bytes[0] += 1
    out.extend(out_buff[0:out_bytes[0]])
    return bytes(out)


if __name__ == "__main__":
    for blob in (
        b"A",
        b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        bytes(range(256)) * 8,
        b"<?xml version=\"1.0\"?><a>text text text</a>" * 40,
    ):
        enc = implode(blob)
        dec = explode(enc)
        assert dec == blob, (blob[:24], len(blob), len(dec))
    print("pklib self-check ok")

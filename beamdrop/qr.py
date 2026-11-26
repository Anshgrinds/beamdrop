"""
Zero-dependency, pure-Python QR Code generator.
Supports QR Code Version 1-10 with standard byte encoding and Reed-Solomon error correction.
Outputs ASCII terminal blocks and SVG vector format.
"""

import math
from typing import List, Tuple, Optional


# Galois Field GF(2^8) with primitive polynomial 0x11D (x^8 + x^4 + x^3 + x^2 + 1)
_EXP = [0] * 512
_LOG = [0] * 256

def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _EXP[i + 255] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    _LOG[0] = 0

_init_gf()

def _gf_mul(x: int, y: int) -> int:
    if x == 0 or y == 0:
        return 0
    return _EXP[_LOG[x] + _LOG[y]]

def _rs_poly_mul(p1: List[int], p2: List[int]) -> List[int]:
    res = [0] * (len(p1) + len(p2) - 1)
    for i, a in enumerate(p1):
        for j, b in enumerate(p2):
            res[i + j] ^= _gf_mul(a, b)
    return res

def _rs_generator_poly(num_ec: int) -> List[int]:
    g = [1]
    for i in range(num_ec):
        g = _rs_poly_mul(g, [1, _EXP[i]])
    return g

def _rs_encode(data: List[int], num_ec: int) -> List[int]:
    gen = _rs_generator_poly(num_ec)
    padded = data + [0] * num_ec
    for i in range(len(data)):
        lead = padded[i]
        if lead != 0:
            for j in range(len(gen)):
                padded[i + j] ^= _gf_mul(gen[j], lead)
    return padded[len(data):]


# Version specifications: (total_cw, ec_per_block, num_b1, data_b1, num_b2, data_b2)
# Error correction Level M
_VERSION_SPECS_M = {
    1: (26, 10, 1, 16, 0, 0),
    2: (44, 16, 1, 28, 0, 0),
    3: (70, 26, 1, 44, 0, 0),
    4: (100, 18, 2, 32, 0, 0),
    5: (134, 24, 2, 43, 0, 0),
    6: (172, 16, 4, 27, 0, 0),
    7: (196, 18, 4, 31, 0, 0),
    8: (242, 22, 2, 38, 2, 39),
    9: (292, 22, 3, 36, 2, 37),
    10: (346, 26, 4, 43, 1, 44),
}

# Alignment pattern centers for versions 1..10
_ALIGNMENT_PATTERNS = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
}


class QRCode:
    def __init__(self, data: str):
        self.data_str = data
        self.data_bytes = data.encode("utf-8")
        self.version = self._choose_version()
        self.spec = _VERSION_SPECS_M[self.version]
        self.size = 17 + 4 * self.version
        
        # Modules: True = black/dark, False = white/light, None = unassigned
        self.modules: List[List[Optional[bool]]] = [[None] * self.size for _ in range(self.size)]
        self.is_function: List[List[bool]] = [[False] * self.size for _ in range(self.size)]
        
        self._build()

    def _choose_version(self) -> int:
        n = len(self.data_bytes)
        for ver in range(1, 11):
            spec = _VERSION_SPECS_M[ver]
            total_data_bytes = spec[2] * spec[3] + spec[4] * spec[5]
            # In byte mode: 4 bits mode + 8 bits length count + 8 * n bits
            bits_needed = 4 + 8 + 8 * n
            bytes_needed = math.ceil(bits_needed / 8)
            if bytes_needed <= total_data_bytes:
                return ver
        raise ValueError(f"Content too long ({n} bytes) for supported QR versions (max ~213 bytes)")

    def _encode_data(self) -> List[int]:
        spec = self.spec
        total_data = spec[2] * spec[3] + spec[4] * spec[5]
        
        # Bit stream
        bits = []
        # Mode indicator: Byte mode is 0100
        bits.extend([0, 1, 0, 0])
        # Character count indicator (8 bits for version 1..9, 16 bits for version 10+ in byte mode)
        length_bits = 8 if self.version < 10 else 16
        for i in range(length_bits - 1, -1, -1):
            bits.append((len(self.data_bytes) >> i) & 1)
        # Data bits
        for b in self.data_bytes:
            for i in range(7, -1, -1):
                bits.append((b >> i) & 1)
                
        # Terminator: up to 4 zero bits
        bits_capacity = total_data * 8
        rem = bits_capacity - len(bits)
        bits.extend([0] * min(4, rem))
        
        # Pad to multiple of 8
        while len(bits) % 8 != 0:
            bits.append(0)
            
        # Convert to bytes
        bytes_out = []
        for i in range(0, len(bits), 8):
            val = 0
            for b in bits[i:i+8]:
                val = (val << 1) | b
            bytes_out.append(val)
            
        # Alternate pad bytes 0xEC and 0x11
        pad = [0xEC, 0x11]
        pad_idx = 0
        while len(bytes_out) < total_data:
            bytes_out.append(pad[pad_idx % 2])
            pad_idx += 1
            
        return bytes_out

    def _interleave_blocks(self, data_bytes: List[int]) -> List[int]:
        spec = self.spec
        num_ec = spec[1]
        num_b1, data_b1 = spec[2], spec[3]
        num_b2, data_b2 = spec[4], spec[5]
        
        data_blocks = []
        ec_blocks = []
        
        offset = 0
        for _ in range(num_b1):
            block = data_bytes[offset:offset + data_b1]
            data_blocks.append(block)
            ec_blocks.append(_rs_encode(block, num_ec))
            offset += data_b1
            
        for _ in range(num_b2):
            block = data_bytes[offset:offset + data_b2]
            data_blocks.append(block)
            ec_blocks.append(_rs_encode(block, num_ec))
            offset += data_b2
            
        # Interleave data
        interleaved = []
        max_data_len = max(data_b1, data_b2)
        for i in range(max_data_len):
            for block in data_blocks:
                if i < len(block):
                    interleaved.append(block[i])
                    
        # Interleave error correction
        for i in range(num_ec):
            for block in ec_blocks:
                interleaved.append(block[i])
                
        return interleaved

    def _set_func(self, r: int, c: int, val: bool):
        self.modules[r][c] = val
        self.is_function[r][c] = True

    def _place_finder(self, row: int, col: int):
        for r in range(-1, 8):
            for c in range(-1, 8):
                dr = row + r
                dc = col + c
                if 0 <= dr < self.size and 0 <= dc < self.size:
                    if 0 <= r <= 6 and 0 <= c <= 6:
                        if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                            self._set_func(dr, dc, True)
                        else:
                            self._set_func(dr, dc, False)
                    else:
                        # Separator
                        self._set_func(dr, dc, False)

    def _place_alignment(self, row: int, col: int):
        for r in range(-2, 3):
            for c in range(-2, 3):
                dr = row + r
                dc = col + c
                if not self.is_function[dr][dc]:
                    if abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0):
                        self._set_func(dr, dc, True)
                    else:
                        self._set_func(dr, dc, False)

    def _build(self):
        # 1. Place finders
        self._place_finder(0, 0)
        self._place_finder(0, self.size - 7)
        self._place_finder(self.size - 7, 0)
        
        # 2. Timing patterns
        for i in range(8, self.size - 8):
            val = (i % 2 == 0)
            if not self.is_function[6][i]:
                self._set_func(6, i, val)
            if not self.is_function[i][6]:
                self._set_func(i, 6, val)
                
        # 3. Alignment patterns
        pos = _ALIGNMENT_PATTERNS.get(self.version, [])
        for r in pos:
            for c in pos:
                # Skip if conflicts with finder patterns
                if (r < 9 and c < 9) or (r < 9 and c > self.size - 10) or (r > self.size - 10 and c < 9):
                    continue
                self._place_alignment(r, c)
                
        # 4. Dark module
        self._set_func(4 * self.version + 9, 8, True)
        
        # 5. Reserve format information areas
        for i in range(9):
            if not self.is_function[8][i]:
                self.is_function[8][i] = True
            if not self.is_function[i][8]:
                self.is_function[i][8] = True
        for i in range(8):
            if not self.is_function[8][self.size - 1 - i]:
                self.is_function[8][self.size - 1 - i] = True
            if not self.is_function[self.size - 1 - i][8]:
                self.is_function[self.size - 1 - i][8] = True
                
        # 6. Encode data & EC
        raw_data = self._encode_data()
        interleaved = self._interleave_blocks(raw_data)
        
        # Convert interleaved bytes to bits
        all_bits = []
        for byte in interleaved:
            for i in range(7, -1, -1):
                all_bits.append((byte >> i) & 1)
                
        # 7. Place data bits in matrix (up/down zigzag)
        bit_idx = 0
        right = self.size - 1
        upward = True
        
        while right > 0:
            if right == 6:  # Skip vertical timing column
                right -= 1
                
            cols = [right, right - 1]
            rows = range(self.size - 1, -1, -1) if upward else range(self.size)
            
            for r in rows:
                for c in cols:
                    if not self.is_function[r][c]:
                        bit_val = all_bits[bit_idx] if bit_idx < len(all_bits) else 0
                        self.modules[r][c] = (bit_val == 1)
                        bit_idx += 1
                        
            right -= 2
            upward = not upward
            
        # 8. Mask selection (apply best mask)
        best_mask = self._choose_best_mask()
        self._apply_mask(best_mask)
        self._write_format_info(best_mask)

    def _choose_best_mask(self) -> int:
        best_mask = 0
        min_penalty = float('inf')
        for mask in range(8):
            penalty = self._calc_penalty(mask)
            if penalty < min_penalty:
                min_penalty = penalty
                best_mask = mask
        return best_mask

    def _is_masked(self, mask: int, r: int, c: int) -> bool:
        if mask == 0: return (r + c) % 2 == 0
        if mask == 1: return r % 2 == 0
        if mask == 2: return c % 3 == 0
        if mask == 3: return (r + c) % 3 == 0
        if mask == 4: return (r // 2 + c // 3) % 2 == 0
        if mask == 5: return ((r * c) % 2) + ((r * c) % 3) == 0
        if mask == 6: return (((r * c) % 2) + ((r * c) % 3)) % 2 == 0
        if mask == 7: return (((r + c) % 2) + ((r * c) % 3)) % 2 == 0
        return False

    def _calc_penalty(self, mask: int) -> int:
        penalty = 0
        size = self.size
        # Construct temporary grid with this mask applied
        grid = [[(self.modules[r][c] ^ self._is_masked(mask, r, c)) if not self.is_function[r][c] else self.modules[r][c]
                 for c in range(size)] for r in range(size)]
                 
        # N1: 5 or more same color in a row/col
        for r in range(size):
            run_color, run_len = None, 0
            for c in range(size):
                val = grid[r][c]
                if val == run_color:
                    run_len += 1
                else:
                    if run_len >= 5:
                        penalty += 3 + (run_len - 5)
                    run_color, run_len = val, 1
            if run_len >= 5:
                penalty += 3 + (run_len - 5)
                
        for c in range(size):
            run_color, run_len = None, 0
            for r in range(size):
                val = grid[r][c]
                if val == run_color:
                    run_len += 1
                else:
                    if run_len >= 5:
                        penalty += 3 + (run_len - 5)
                    run_color, run_len = val, 1
            if run_len >= 5:
                penalty += 3 + (run_len - 5)
                
        # N2: 2x2 blocks of same color
        for r in range(size - 1):
            for c in range(size - 1):
                val = grid[r][c]
                if val == grid[r+1][c] == grid[r][c+1] == grid[r+1][c+1]:
                    penalty += 3
                    
        return penalty

    def _apply_mask(self, mask: int):
        for r in range(self.size):
            for c in range(self.size):
                if not self.is_function[r][c]:
                    if self._is_masked(mask, r, c):
                        self.modules[r][c] = not self.modules[r][c]

    def _write_format_info(self, mask: int):
        # Format info: EC Level M (00) -> 0, mask pattern (3 bits)
        # 15-bit BCH code
        data = (0 << 3) | mask
        rem = data << 10
        gen = 0x537
        for i in range(14, 9, -1):
            if (rem >> i) & 1:
                rem ^= gen << (i - 10)
        fmt = ((data << 10) | rem) ^ 0x5412
        
        # Place format bits
        for i in range(6):
            bit = bool((fmt >> i) & 1)
            self.modules[8][i] = bit
            self.modules[self.size - 1 - i][8] = bit
            
        self.modules[8][7] = bool((fmt >> 6) & 1)
        self.modules[self.size - 7][8] = bool((fmt >> 6) & 1)
        
        self.modules[8][8] = bool((fmt >> 7) & 1)
        self.modules[8][self.size - 8] = bool((fmt >> 7) & 1)
        
        self.modules[7][8] = bool((fmt >> 8) & 1)
        self.modules[8][self.size - 7] = bool((fmt >> 8) & 1)
        
        for i in range(9, 15):
            bit = bool((fmt >> i) & 1)
            self.modules[14 - i][8] = bit
            self.modules[8][self.size - 15 + i] = bit

    def to_ascii(self, border: int = 2) -> str:
        """
        Renders QR code to an ANSI/ASCII terminal string using unicode half-blocks.
        '▀' (upper half block) allows rendering two matrix rows in one text line!
        """
        lines = []
        pad_module = False
        full_size = self.size + border * 2
        
        # Build expanded grid with border
        grid = [[pad_module] * full_size for _ in range(full_size)]
        for r in range(self.size):
            for c in range(self.size):
                grid[r + border][c + border] = self.modules[r][c]
                
        # Invert representation for typical dark terminal (white background / black QR modules)
        # Using white blocks: upper, lower, full, space
        for r in range(0, full_size, 2):
            row_str = []
            for c in range(full_size):
                top = grid[r][c]
                bot = grid[r + 1][c] if r + 1 < full_size else pad_module
                
                # Standard terminals are dark backgrounds:
                # Top dark + Bot dark -> "  " (black/empty)
                # Top light + Bot light -> "█" (full white)
                # Top light + Bot dark  -> "▀"
                # Top dark  + Bot light -> "▄"
                if not top and not bot:
                    row_str.append("█")
                elif not top and bot:
                    row_str.append("▀")
                elif top and not bot:
                    row_str.append("▄")
                else:
                    row_str.append(" ")
            lines.append("".join(row_str))
            
        return "\n".join(lines)

    def to_svg(self, scale: int = 8, border: int = 4) -> str:
        """Renders QR code to an SVG string."""
        total_dim = (self.size + border * 2) * scale
        rects = []
        for r in range(self.size):
            for c in range(self.size):
                if self.modules[r][c]:
                    x = (c + border) * scale
                    y = (r + border) * scale
                    rects.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="#0f172a"/>')
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_dim} {total_dim}" '
            f'width="{total_dim}" height="{total_dim}">\n'
            f'<rect width="100%" height="100%" fill="#ffffff" rx="{scale * 2}"/>\n'
            f'{"".join(rects)}\n'
            f'</svg>'
        )

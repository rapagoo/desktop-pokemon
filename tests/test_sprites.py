"""스프라이트 몸 경계 계산 테스트: 직접 만든 PNG를 Tk 없이 읽어 투명도·경계가 맞는지."""
import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from pokepet.sprites import frame_bounds, png_alpha


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def encode_png(width, rows_rgba, filters):
    """RGBA 행들을 행마다 주어진 PNG 필터(0~4)로 인코딩한 PNG 바이트."""
    out, prev = b"", bytes(width * 4)
    for row, f in zip(rows_rgba, filters):
        enc = bytearray()
        for i, x in enumerate(row):
            a = row[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            pred = (0, a, b, (a + b) >> 1, paeth(a, b, c))[f]
            enc.append((x - pred) & 255)
        out += bytes([f]) + bytes(enc)
        prev = row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", width, len(rows_rgba), 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(out)) + chunk(b"IEND", b"")


class TestPngAlpha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        path = Path(self.tmp.name) / "t.png"
        path.write_bytes(data)
        return path

    def test_all_filters_decode_exactly(self):
        rng = random.Random(7)
        w, h = 13, 15
        rows = [bytes(rng.randrange(256) for _ in range(w * 4)) for _ in range(h)]
        filters = [y % 5 for y in range(h)]                 # 0,1,2,3,4 골고루
        pw, ph, alpha = png_alpha(self.write(encode_png(w, rows, filters)))
        self.assertEqual((pw, ph), (w, h))
        self.assertEqual(alpha, [row[3::4] for row in rows])

    def test_other_formats_are_skipped(self):
        data = encode_png(2, [bytes(8)], [0]).replace(b"\x08\x06\x00\x00\x00", b"\x08\x02\x00\x00\x00", 1)
        self.assertIsNone(png_alpha(self.write(data)))


class TestFrameBounds(unittest.TestCase):
    def test_bounds_inside_cell(self):
        # 8x6 시트에서 (2,1)부터 4x4 칸, 그 안의 (1,1)~(2,3)이 불투명
        rows = [bytearray(8) for _ in range(6)]
        for y in (2, 3, 4):
            for x in (3, 4):
                rows[y][x] = 255
        rows = [bytes(r) for r in rows]
        self.assertEqual(frame_bounds(rows, 2, 1, 4, 4), (1, 1, 2, 3))

    def test_empty_cell(self):
        rows = [bytes(8) for _ in range(4)]
        self.assertIsNone(frame_bounds(rows, 0, 0, 4, 4))


if __name__ == "__main__":
    unittest.main()

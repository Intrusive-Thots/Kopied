"""Generate C:\\Kopied\\assets\\kopied.ico (16/32/48/64/128/256) and a PNG preview."""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZES = (16, 32, 48, 64, 128, 256)
TEAL = (16, 116, 122, 255)
TEAL_DARK = (10, 84, 90, 255)
PAPER = (250, 252, 252, 255)
PAPER_EDGE = (214, 232, 232, 255)
GOLD = (212, 168, 75, 255)
GOLD_DARK = (168, 126, 42, 255)
LINE = (16, 116, 122, 255)


def _rr(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=max(1, radius), fill=fill)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def u(n: float) -> float:
        return n * size / 256.0

    if size == 16:
        _rr(d, [0, 0, 15, 15], 3, TEAL)
        _rr(d, [3, 3, 12, 14], 1, PAPER)
        d.rectangle([6, 1, 9, 4], fill=GOLD)
        d.rectangle([5, 7, 10, 8], fill=LINE)
        d.rectangle([5, 10, 9, 11], fill=LINE)
        return img

    if size == 32:
        _rr(d, [0, 0, 31, 31], 7, TEAL_DARK)
        _rr(d, [0, 0, 31, 30], 7, TEAL)
        _rr(d, [8, 6, 23, 27], 2, PAPER_EDGE)
        _rr(d, [9, 7, 22, 26], 2, PAPER)
        _rr(d, [12, 3, 19, 10], 1, GOLD_DARK)
        _rr(d, [13, 4, 18, 9], 1, GOLD)
        d.rectangle([11, 13, 20, 15], fill=LINE)
        d.rectangle([11, 17, 18, 19], fill=LINE)
        d.rectangle([11, 21, 20, 23], fill=LINE)
        return img

    _rr(d, [u(8), u(12), u(248), u(252)], u(56), TEAL_DARK)
    _rr(d, [u(8), u(8), u(248), u(248)], u(56), TEAL)
    br = max(u(16), 2)
    _rr(d, [u(70), u(52), u(186), u(214)], br, PAPER_EDGE)
    _rr(d, [u(74), u(56), u(182), u(210)], br, PAPER)
    cr = max(u(8), 1)
    _rr(d, [u(102), u(36), u(154), u(78)], cr, GOLD_DARK)
    _rr(d, [u(104), u(38), u(152), u(74)], cr, GOLD)
    if size >= 64:
        _rr(d, [u(116), u(48), u(140), u(66)], max(u(6), 1), TEAL)
    else:
        d.rectangle([u(118), u(50), u(138), u(64)], fill=TEAL)

    t = {48: 4, 64: 5, 128: 8, 256: 10}.get(size, max(3, int(u(10))))
    for y, rgt in zip((100, 126, 152, 178), (166, 150, 166, 138)):
        y1 = u(y)
        _rr(d, [u(90), y1, u(rgt), y1 + t], t / 2, LINE)
    return img


def write_ico(path: Path, images_by_size: dict[int, Image.Image]) -> None:
    sizes = sorted(images_by_size)
    entries, payloads = [], []
    offset = 6 + 16 * len(sizes)
    for s in sizes:
        buf = io.BytesIO()
        images_by_size[s].convert("RGBA").save(buf, format="PNG")
        data = buf.getvalue()
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        entries.append((w, h, len(data), offset))
        payloads.append(data)
        offset += len(data)
    with path.open("wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        for w, h, nbytes, off in entries:
            f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, nbytes, off))
        for payload in payloads:
            f.write(payload)


def main() -> int:
    here = Path(__file__).resolve().parent
    images = {s: make_icon(s) for s in SIZES}
    preview = here / "kopied-icon-preview.png"
    ico = here / "kopied.ico"
    images[256].save(preview, "PNG")
    write_ico(ico, images)
    print(f"Wrote {ico}")
    print(f"Wrote {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

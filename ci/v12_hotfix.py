from pathlib import Path
import struct
import sys
import zlib

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")
textures = root / "src/main/resources/assets/pipecore/textures/item"
textures.mkdir(parents=True, exist_ok=True)

W = H = 16
TRANSPARENT = (0, 0, 0, 0)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path: Path, pixels):
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += png_chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
    payload += png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    payload += png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def make_card(p):
    px = [[TRANSPARENT for _ in range(W)] for _ in range(H)]

    def rect(x0, y0, x1, y1, color):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if 0 <= x < W and 0 <= y < H:
                    px[y][x] = color

    # Front-facing premium sci-fi card chassis.
    rect(2, 1, 12, 14, p["outline"])
    rect(1, 2, 13, 13, p["outline"])
    rect(2, 2, 12, 13, p["base"])
    rect(3, 3, 11, 12, p["mid"])

    # Beveled shell and recessed central panel.
    rect(3, 3, 11, 3, p["hi"])
    rect(3, 4, 3, 11, p["hi2"])
    rect(3, 12, 11, 12, p["low"])
    rect(4, 5, 10, 10, p["panel"])
    rect(4, 5, 10, 5, p["panel_hi"])
    rect(4, 10, 10, 10, p["panel_low"])

    # Small hardware nodes, vertical seam and side tech rail.
    for x, y in ((3, 4), (11, 4), (3, 11), (11, 11)):
        px[y][x] = p["node"]
    rect(2, 8, 2, 11, p["seam"])
    rect(13, 4, 13, 11, p["rail_dark"])
    for y in (4, 7, 10):
        rect(14, y, 15, y + 1, p["rail"])
        px[y + 1][15] = p["rail_hi"]

    # Abstract core mark only; intentionally no letters or text.
    for x, y, color in p["emblem"]:
        px[y][x] = color

    return px


palettes = {
    "basic_upgrade_card": {
        "outline": (25, 30, 33, 255), "base": (64, 73, 79, 255), "mid": (82, 93, 100, 255),
        "hi": (130, 142, 150, 255), "hi2": (105, 117, 124, 255), "low": (45, 52, 57, 255),
        "panel": (97, 108, 115, 255), "panel_hi": (138, 151, 158, 255), "panel_low": (58, 66, 71, 255),
        "node": (189, 198, 203, 255), "rail_dark": (42, 48, 53, 255), "rail": (113, 124, 131, 255),
        "rail_hi": (180, 189, 194, 255), "seam": (50, 58, 63, 255),
        "emblem": [
            (6, 6, (220, 227, 230, 255)), (7, 6, (236, 241, 243, 255)), (8, 6, (220, 227, 230, 255)),
            (5, 7, (220, 227, 230, 255)), (6, 7, (245, 248, 249, 255)), (7, 7, (245, 248, 249, 255)),
            (8, 7, (245, 248, 249, 255)), (9, 7, (220, 227, 230, 255)),
            (6, 8, (220, 227, 230, 255)), (7, 8, (245, 248, 249, 255)), (8, 8, (220, 227, 230, 255)),
            (7, 9, (198, 207, 212, 255)),
        ],
    },
    "improved_upgrade_card": {
        "outline": (42, 29, 18, 255), "base": (102, 67, 20, 255), "mid": (147, 96, 25, 255),
        "hi": (221, 157, 49, 255), "hi2": (180, 119, 32, 255), "low": (75, 46, 16, 255),
        "panel": (121, 75, 20, 255), "panel_hi": (190, 128, 34, 255), "panel_low": (82, 49, 15, 255),
        "node": (247, 193, 74, 255), "rail_dark": (73, 47, 18, 255), "rail": (198, 135, 35, 255),
        "rail_hi": (252, 205, 90, 255), "seam": (82, 51, 18, 255),
        "emblem": [
            (6, 6, (255, 223, 103, 255)), (7, 6, (255, 238, 133, 255)), (8, 6, (255, 223, 103, 255)),
            (5, 7, (235, 182, 57, 255)), (6, 7, (255, 235, 114, 255)), (7, 7, (255, 247, 165, 255)),
            (8, 7, (255, 235, 114, 255)), (9, 7, (235, 182, 57, 255)),
            (6, 8, (247, 201, 72, 255)), (7, 8, (255, 232, 100, 255)), (8, 8, (247, 201, 72, 255)),
            (7, 9, (194, 128, 31, 255)),
        ],
    },
    "advanced_upgrade_card": {
        "outline": (29, 39, 43, 255), "base": (179, 201, 205, 255), "mid": (211, 226, 228, 255),
        "hi": (242, 249, 249, 255), "hi2": (226, 238, 239, 255), "low": (122, 143, 148, 255),
        "panel": (187, 215, 218, 255), "panel_hi": (233, 247, 247, 255), "panel_low": (135, 166, 171, 255),
        "node": (82, 215, 224, 255), "rail_dark": (41, 78, 84, 255), "rail": (55, 202, 214, 255),
        "rail_hi": (133, 244, 248, 255), "seam": (140, 166, 171, 255),
        "emblem": [
            (7, 5, (100, 231, 238, 255)), (6, 6, (73, 207, 219, 255)), (7, 6, (171, 248, 249, 255)),
            (8, 6, (73, 207, 219, 255)), (5, 7, (85, 218, 228, 255)), (6, 7, (154, 244, 247, 255)),
            (7, 7, (226, 255, 255, 255)), (8, 7, (154, 244, 247, 255)), (9, 7, (85, 218, 228, 255)),
            (6, 8, (73, 207, 219, 255)), (7, 8, (171, 248, 249, 255)), (8, 8, (73, 207, 219, 255)),
            (7, 9, (76, 177, 188, 255)),
        ],
    },
    "ultimate_upgrade_card": {
        "outline": (22, 19, 17, 255), "base": (47, 39, 34, 255), "mid": (61, 49, 42, 255),
        "hi": (91, 73, 59, 255), "hi2": (76, 60, 50, 255), "low": (31, 26, 23, 255),
        "panel": (54, 43, 37, 255), "panel_hi": (83, 66, 53, 255), "panel_low": (34, 28, 24, 255),
        "node": (151, 116, 85, 255), "rail_dark": (35, 28, 24, 255), "rail": (110, 82, 62, 255),
        "rail_hi": (170, 129, 92, 255), "seam": (40, 33, 29, 255),
        "emblem": [
            (6, 6, (136, 107, 79, 255)), (7, 6, (178, 139, 98, 255)), (8, 6, (136, 107, 79, 255)),
            (5, 7, (95, 76, 62, 255)), (6, 7, (154, 121, 88, 255)), (7, 7, (203, 160, 108, 255)),
            (8, 7, (154, 121, 88, 255)), (9, 7, (95, 76, 62, 255)),
            (6, 8, (121, 96, 75, 255)), (7, 8, (170, 132, 94, 255)), (8, 8, (121, 96, 75, 255)),
            (7, 9, (84, 68, 56, 255)),
        ],
    },
    "filter_card": {
        "outline": (14, 38, 28, 255), "base": (27, 96, 61, 255), "mid": (35, 133, 77, 255),
        "hi": (63, 196, 117, 255), "hi2": (49, 166, 95, 255), "low": (19, 68, 46, 255),
        "panel": (28, 105, 64, 255), "panel_hi": (55, 172, 102, 255), "panel_low": (21, 75, 50, 255),
        "node": (92, 239, 147, 255), "rail_dark": (18, 69, 46, 255), "rail": (55, 189, 109, 255),
        "rail_hi": (121, 255, 168, 255), "seam": (22, 77, 50, 255),
        "emblem": [
            (5, 6, (89, 246, 151, 255)), (6, 6, (89, 246, 151, 255)), (7, 6, (89, 246, 151, 255)),
            (8, 6, (89, 246, 151, 255)), (9, 6, (89, 246, 151, 255)),
            (6, 7, (63, 220, 127, 255)), (7, 7, (109, 255, 170, 255)), (8, 7, (63, 220, 127, 255)),
            (7, 8, (109, 255, 170, 255)), (7, 9, (71, 232, 137, 255)),
        ],
    },
    "void_filter_card": {
        "outline": (27, 17, 33, 255), "base": (57, 29, 73, 255), "mid": (76, 37, 99, 255),
        "hi": (114, 55, 147, 255), "hi2": (94, 44, 121, 255), "low": (37, 21, 47, 255),
        "panel": (62, 31, 81, 255), "panel_hi": (98, 47, 128, 255), "panel_low": (41, 23, 54, 255),
        "node": (185, 88, 238, 255), "rail_dark": (46, 25, 58, 255), "rail": (142, 70, 185, 255),
        "rail_hi": (214, 121, 255, 255), "seam": (44, 25, 56, 255),
        "emblem": [
            (6, 6, (152, 70, 212, 255)), (7, 6, (206, 113, 255, 255)), (8, 6, (166, 76, 225, 255)),
            (5, 7, (121, 51, 177, 255)), (6, 7, (186, 91, 241, 255)), (7, 7, (228, 150, 255, 255)),
            (8, 7, (186, 91, 241, 255)), (9, 7, (121, 51, 177, 255)),
            (6, 8, (139, 61, 196, 255)), (7, 8, (206, 113, 255, 255)), (8, 8, (139, 61, 196, 255)),
            (7, 9, (92, 39, 134, 255)),
        ],
    },
}

for name, palette in palettes.items():
    write_png(textures / f"{name}.png", make_card(palette))

props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.8" not in p:
    raise SystemExit("Expected mod_version=1.3.8 before V12 card texture patch")
props.write_text(p.replace("mod_version=1.3.8", "mod_version=1.3.9", 1), encoding="utf-8")

print("Applied Pipe Core V12: redesigned six card textures, version 1.3.9")

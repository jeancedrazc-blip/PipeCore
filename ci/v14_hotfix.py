from pathlib import Path
import json
import re
import struct
import sys
import zlib

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")

# 1) Configurator: force Shift right-click through the NeoForge interaction event.
pipe_block = root / "src/main/java/com/pipecore/block/PipeBlock.java"
text = pipe_block.read_text(encoding="utf-8")
old = "    private static Direction interactionFace(BlockState state, BlockPos pos, BlockHitResult hit) {"
new = "    public static Direction interactionFace(BlockState state, BlockPos pos, BlockHitResult hit) {"
if old not in text:
    raise SystemExit("PipeBlock interactionFace visibility pattern not found")
text = text.replace(old, new, 1)
pipe_block.write_text(text, encoding="utf-8")

events_dir = root / "src/main/java/com/pipecore/event"
events_dir.mkdir(parents=True, exist_ok=True)
(events_dir / "PipeInteractionEvents.java").write_text('''package com.pipecore.event;

import com.pipecore.PipeCore;
import com.pipecore.block.PipeBlock;
import com.pipecore.block.PipeBlockEntity;
import net.minecraft.core.Direction;
import net.minecraft.util.TriState;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;

/** Forces Configurator handling before vanilla sneak-use can bypass Block#useItemOn. */
public final class PipeInteractionEvents {

    @SubscribeEvent
    public void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        Player player = event.getEntity();
        ItemStack held = player.getItemInHand(event.getHand());

        if (!player.isShiftKeyDown() || held.getItem() != PipeCore.CONFIGURATOR.get()) {
            return;
        }

        BlockState state = event.getLevel().getBlockState(event.getPos());
        if (!(state.getBlock() instanceof PipeBlock)) {
            return;
        }

        BlockEntity blockEntity = event.getLevel().getBlockEntity(event.getPos());
        if (!(blockEntity instanceof PipeBlockEntity pipe)) {
            return;
        }

        Direction face = PipeBlock.interactionFace(state, event.getPos(), event.getHitVec());
        if (!event.getLevel().isClientSide()) {
            pipe.cycleFaceMode(face);
        }

        event.setUseItem(TriState.TRUE);
        event.setCancellationResult(InteractionResult.SUCCESS);
        event.setCanceled(true);
    }
}
''', encoding="utf-8")

pipe_core = root / "src/main/java/com/pipecore/PipeCore.java"
text = pipe_core.read_text(encoding="utf-8")
if "import com.pipecore.event.PipeInteractionEvents;" not in text:
    text = text.replace(
        "package com.pipecore;\n",
        "package com.pipecore;\n\nimport com.pipecore.event.PipeInteractionEvents;\nimport net.neoforged.neoforge.common.NeoForge;\n",
        1,
    )
anchor = "        TABS.register(modBus);\n"
if anchor not in text:
    raise SystemExit("PipeCore constructor registration anchor not found")
if "NeoForge.EVENT_BUS.register(new PipeInteractionEvents());" not in text:
    text = text.replace(anchor, anchor + "        NeoForge.EVENT_BUS.register(new PipeInteractionEvents());\n", 1)
pipe_core.write_text(text, encoding="utf-8")

# 2) Energy pipes are bidirectional endpoints by default.
entity_file = root / "src/main/java/com/pipecore/block/PipeBlockEntity.java"
text = entity_file.read_text(encoding="utf-8")

old = '''        } else {
            // External endpoint: NORMAL -> OUTPUT(extract) -> DISCONNECTED -> NORMAL.
            faceModes[index] = faceModes[index].next();
        }
'''
new = '''        } else if (kind() == PipeKind.ENERGY) {
            // Energy is inherently bidirectional. The configurator only connects/disconnects it.
            faceModes[index] = faceModes[index] == FaceMode.DISCONNECTED
                    ? FaceMode.NORMAL
                    : FaceMode.DISCONNECTED;
        } else {
            // Item/fluid/chemical endpoint: NORMAL -> OUTPUT(extract) -> DISCONNECTED -> NORMAL.
            faceModes[index] = faceModes[index].next();
        }
'''
if old not in text:
    raise SystemExit("cycleFaceMode external endpoint pattern not found")
text = text.replace(old, new, 1)

server_pattern = re.compile(
    r'''    public static void serverTick\(Level level, BlockPos pos, BlockState state, PipeBlockEntity pipe\) \{.*?\n    \}\n\n    private int transferFromOutput''',
    re.S,
)
server_replacement = '''    public static void serverTick(Level level, BlockPos pos, BlockState state, PipeBlockEntity pipe) {
        if (level.isClientSide()) return;

        if ((level.getGameTime() + Math.floorMod(pos.asLong(), 4)) % 4L == 0L) {
            pipe.syncVisualState(level, false);
        }

        List<Direction> activeFaces = new ArrayList<>();
        for (Direction direction : Direction.values()) {
            FaceMode mode = pipe.getFaceMode(direction);

            if (pipe.kind() == PipeKind.ENERGY) {
                if (mode == FaceMode.DISCONNECTED) continue;
                BlockPos endpoint = pos.relative(direction);
                if (!pipe.isExternalEndpoint(level, endpoint)) continue;
            } else {
                if (mode != FaceMode.OUTPUT) continue;
            }

            int interval = pipe.upgradeTier(direction).intervalTicks();
            if ((level.getGameTime() + Math.floorMod(pos.asLong() + direction.ordinal(), interval)) % interval == 0L) {
                activeFaces.add(direction);
            }
        }

        if (activeFaces.isEmpty()) return;

        activeFaces.sort(Comparator.comparingInt(pipe::priority).reversed());
        List<PipeBlockEntity> network = pipe.discoverNetwork(level);
        pipe.networkSize = network.size();

        int moved = 0;
        for (Direction direction : activeFaces) {
            moved += pipe.transferFromOutput(level, network, direction);
        }
        pipe.lastMoved = moved;
    }

    private int transferFromOutput'''
text2, n = server_pattern.subn(server_replacement, text, count=1)
if n != 1:
    raise SystemExit("serverTick method pattern not found")
text = text2

old = "        if (getFaceMode(sourceFace) != FaceMode.OUTPUT) return 0;\n"
new = '''        if (kind() == PipeKind.ENERGY) {
            if (getFaceMode(sourceFace) == FaceMode.DISCONNECTED) return 0;
        } else if (getFaceMode(sourceFace) != FaceMode.OUTPUT) {
            return 0;
        }
'''
if old not in text:
    raise SystemExit("transferFromOutput guard pattern not found")
text = text.replace(old, new, 1)

old = "                if (targetPipe.getFaceMode(targetSide) != FaceMode.NORMAL) continue;\n"
new = "                if (targetPipe.getFaceMode(targetSide) == FaceMode.DISCONNECTED) continue;\n"
energy_start = text.find("    private int transferEnergy(")
energy_end = text.find("    private int transferChemicals", energy_start)
if energy_start < 0 or energy_end < 0:
    raise SystemExit("transferEnergy boundaries not found")
energy = text[energy_start:energy_end]
if old not in energy:
    raise SystemExit("transferEnergy target-mode pattern not found")
energy = energy.replace(old, new, 1)
text = text[:energy_start] + energy + text[energy_end:]
entity_file.write_text(text, encoding="utf-8")

# 3) Texture transparency + thicker Configurator icon.
textures = root / "src/main/resources/assets/pipecore/textures"

def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

def read_rgba_png_filter0(path: Path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path.name}: not a PNG")
    pos = 8
    idat = bytearray()
    width = height = None
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        payload = data[pos+8:pos+8+length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if (bit_depth, color_type, interlace) != (8, 6, 0):
                raise SystemExit(f"{path.name}: unsupported PNG format")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    pixels = []
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        if filter_type != 0:
            raise SystemExit(f"{path.name}: expected filter 0, got {filter_type}")
        offset += 1
        row = []
        for x in range(width):
            i = offset + x * 4
            row.append(tuple(raw[i:i+4]))
        pixels.append(row)
        offset += stride
    return width, height, pixels

def write_rgba_png(path: Path, width: int, height: int, pixels):
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for rgba in row:
            raw.extend(rgba)
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out.extend(png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    out.extend(png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
    out.extend(png_chunk(b"IEND", b""))
    path.write_bytes(bytes(out))

# 31/34/38 is the dark filler between gray rail and colored core.
# Keep 57/62/67 square hardware pixels opaque.
for path in sorted((textures / "block").glob("*_pipe_vertical.png")):
    w, h, px = read_rgba_png_filter0(path)
    changed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[y][x]
            if (r, g, b) == (31, 34, 38):
                px[y][x] = (r, g, b, 0)
                changed += 1
    if changed == 0:
        raise SystemExit(f"{path.name}: dark filler color not found")
    write_rgba_png(path, w, h, px)

models = root / "src/main/resources/assets/pipecore/models/block"
for name in [
    "pipe_arm_base.json",
    "pipe_arm_up_base.json",
    "pipe_arm_down_base.json",
    "pipe_straight_ns_base.json",
    "pipe_straight_vertical_base.json",
]:
    path = models / name
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    data["render_type"] = "minecraft:cutout"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

W = H = 16
transparent = (0, 0, 0, 0)
px = [[transparent for _ in range(W)] for _ in range(H)]

def put(x, y, color):
    if 0 <= x < W and 0 <= y < H:
        px[y][x] = color

def rect(x0, y0, x1, y1, color):
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            put(xx, yy, color)

dark = (31, 35, 39, 255)
mid = (86, 99, 106, 255)
light = (150, 166, 174, 255)
hi = (207, 220, 226, 255)
cyan = (54, 222, 231, 255)
cyan_hi = (116, 247, 250, 255)

rect(2, 10, 5, 14, dark)
rect(3, 11, 5, 13, mid)
rect(4, 11, 5, 12, light)
for i in range(7):
    x = 5 + i
    y = 10 - i
    put(x, y, dark)
    put(x, y + 1, dark)
    put(x + 1, y, dark)
for x, y in [(7, 9), (8, 8), (8, 9), (9, 8), (9, 7)]:
    put(x, y, cyan)
put(8, 8, cyan_hi)
for x, y in [(10, 4), (11, 3), (12, 2), (13, 2), (10, 5), (11, 5), (12, 5), (13, 4), (11, 2), (13, 3)]:
    put(x, y, light)
for x, y in [(11, 4), (12, 3), (12, 4)]:
    put(x, y, transparent)
for x, y in [(12, 1), (13, 1), (14, 2), (14, 3)]:
    put(x, y, hi)
write_rgba_png(textures / "item/configurator.png", W, H, px)

# 4) Version.
props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.10" not in p:
    raise SystemExit("Expected mod_version=1.3.10 before V14 hotfix")
props.write_text(p.replace("mod_version=1.3.10", "mod_version=1.3.11", 1), encoding="utf-8")

print("Applied Pipe Core V14: transparent side filler, thicker Configurator, forced Shift event, bidirectional energy, version 1.3.11")

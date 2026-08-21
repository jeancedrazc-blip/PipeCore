from pathlib import Path
import re

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'

# -----------------------------------------------------------------------------
# Quantum Tools 3.0.3
# - chunk-first quarry traversal
# - Offset range: +/- 1024 chunks (= +/- 16384 blocks)
# - hidden internal output buffer in GUI
# - horizontal SIZE / OFFSET rows
# - vertical filter list
# - correct hologram orientation
# -----------------------------------------------------------------------------

# --- BuilderBlockEntity: chunk-first scanner ---------------------------------
p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')

if 'import net.minecraft.world.level.ChunkPos;' not in s:
    s = s.replace('import net.minecraft.world.level.Level;\n', 'import net.minecraft.world.level.Level;\nimport net.minecraft.world.level.ChunkPos;\nimport net.minecraft.world.level.chunk.status.ChunkStatus;\n')

# Add chunk cursor state after the total cursor.
s = s.replace('    private long cursor = 0;\n    private int status = STATUS_IDLE;',
              '    private long cursor = 0;\n    private int scanChunkIndex = 0;\n    private long cursorInChunk = 0L;\n    private int status = STATUS_IDLE;', 1)

# Replace work() through the next helper method boundary.
start = s.index('    private void work(ServerLevel level, QuarryMode mode, ItemStack quarryCard) {')
end = s.index('    private boolean isMineableTarget(', start)
new_work = r'''    private void work(ServerLevel level, QuarryMode mode, ItemStack quarryCard) {
        long volume = volume();
        int totalChunks = chunkCount();
        if (volume <= 0L || cursor >= volume || scanChunkIndex >= totalChunks) {
            finishWork(volume);
            return;
        }

        int scanned = 0;
        while (cursor < volume && scanChunkIndex < totalChunks && scanned < SCAN_BUDGET) {
            long currentChunkVolume = chunkVolume(scanChunkIndex);
            if (currentChunkVolume <= 0L || cursorInChunk >= currentChunkVolume) {
                scanChunkIndex++;
                cursorInChunk = 0L;
                continue;
            }

            ChunkPos chunkPos = chunkPosForIndex(scanChunkIndex);
            // Load exactly the chunk currently being processed. We do NOT force/persist
            // the entire quarry region, which keeps huge remote jobs practical.
            level.getChunkSource().getChunk(chunkPos.x, chunkPos.z, ChunkStatus.FULL, true);

            while (cursorInChunk < currentChunkVolume && scanned++ < SCAN_BUDGET) {
                BlockPos target = positionForChunkCursor(scanChunkIndex, cursorInChunk);
                BlockState state = level.getBlockState(target);

                if (!isMineableTarget(level, target, state)) {
                    advanceChunkCursor();
                    continue;
                }
                if (!QuarryCardItem.allowsBlock(quarryCard, state, level.registryAccess())) {
                    advanceChunkCursor();
                    continue;
                }

                int cost = energyCost(level, target, state, mode);
                if (energy.getEnergyStored() < cost) {
                    status = STATUS_NO_ENERGY;
                    return;
                }

                BlockEntity blockEntity = level.getBlockEntity(target);
                List<ItemStack> drops = getDrops(level, target, state, blockEntity, mode);
                if (!canFitDrops(drops)) {
                    status = STATUS_OUTPUT_FULL;
                    return;
                }

                energy.consume(cost);
                insertDrops(drops);

                level.destroyBlock(target, false);
                if (!mode.isClear()) {
                    level.setBlockAndUpdate(target, Blocks.DIRT.defaultBlockState());
                }
                level.levelEvent(2001, target, Block.getId(state));

                advanceChunkCursor();
                status = STATUS_RUNNING;
                setChanged();
                return; // One actual block mined per tick.
            }

            if (cursorInChunk >= currentChunkVolume) {
                scanChunkIndex++;
                cursorInChunk = 0L;
            }
        }

        if (cursor >= volume || scanChunkIndex >= totalChunks) {
            finishWork(volume);
        } else {
            status = STATUS_RUNNING;
        }
    }

    private void finishWork(long volume) {
        cursor = Math.max(0L, volume);
        scanChunkIndex = chunkCount();
        cursorInChunk = 0L;
        running = false;
        status = STATUS_DONE;
        setChanged();
    }

    private void advanceChunkCursor() {
        cursorInChunk++;
        cursor++;
    }

'''
s = s[:start] + new_work + s[end:]

# Reset all progress cursors.
s = s.replace('''    public void resetProgress() {
        cursor = 0;
        status = running ? STATUS_RUNNING : STATUS_IDLE;
        setChanged();
    }''', '''    public void resetProgress() {
        cursor = 0L;
        scanChunkIndex = 0;
        cursorInChunk = 0L;
        status = running ? STATUS_RUNNING : STATUS_IDLE;
        setChanged();
    }''', 1)

# Offset max = 1024 chunks; size remains 512 blocks/axis.
s = s.replace('return Math.max(-512, Math.min(512, value));',
              'return Math.max(-16_384, Math.min(16_384, value));', 1)

# Replace volume/positionFor with chunk geometry helpers.
start = s.index('    private long volume() {')
end = s.index('    public boolean hologramVisible()', start)
chunk_helpers = r'''    private long volume() {
        return (long) sizeX * (long) sizeY * (long) sizeZ;
    }

    private int startX() { return worldPosition.getX() + offsetX; }
    private int startY() { return worldPosition.getY() + offsetY; }
    private int startZ() { return worldPosition.getZ() + offsetZ; }
    private int endX() { return startX() + sizeX - 1; }
    private int endZ() { return startZ() + sizeZ - 1; }

    private int minChunkX() { return Math.floorDiv(startX(), 16); }
    private int maxChunkX() { return Math.floorDiv(endX(), 16); }
    private int minChunkZ() { return Math.floorDiv(startZ(), 16); }
    private int maxChunkZ() { return Math.floorDiv(endZ(), 16); }
    private int chunksX() { return Math.max(1, maxChunkX() - minChunkX() + 1); }
    private int chunksZ() { return Math.max(1, maxChunkZ() - minChunkZ() + 1); }
    private int chunkCount() { return chunksX() * chunksZ(); }

    private ChunkPos chunkPosForIndex(int index) {
        int safe = Math.max(0, Math.min(index, chunkCount() - 1));
        return new ChunkPos(minChunkX() + (safe % chunksX()), minChunkZ() + (safe / chunksX()));
    }

    private int chunkMinX(int index) {
        ChunkPos cp = chunkPosForIndex(index);
        return Math.max(startX(), cp.getMinBlockX());
    }

    private int chunkMaxX(int index) {
        ChunkPos cp = chunkPosForIndex(index);
        return Math.min(endX(), cp.getMaxBlockX());
    }

    private int chunkMinZ(int index) {
        ChunkPos cp = chunkPosForIndex(index);
        return Math.max(startZ(), cp.getMinBlockZ());
    }

    private int chunkMaxZ(int index) {
        ChunkPos cp = chunkPosForIndex(index);
        return Math.min(endZ(), cp.getMaxBlockZ());
    }

    private long chunkVolume(int index) {
        if (index < 0 || index >= chunkCount()) return 0L;
        int width = chunkMaxX(index) - chunkMinX(index) + 1;
        int depth = chunkMaxZ(index) - chunkMinZ(index) + 1;
        return (long) width * depth * sizeY;
    }

    private BlockPos positionForChunkCursor(int chunkIndex, long localIndex) {
        int minX = chunkMinX(chunkIndex);
        int minZ = chunkMinZ(chunkIndex);
        int width = chunkMaxX(chunkIndex) - minX + 1;
        int depth = chunkMaxZ(chunkIndex) - minZ + 1;
        long layer = (long) width * depth;
        int yLayer = (int) (localIndex / layer);
        long inLayer = localIndex % layer;
        int z = (int) (inLayer / width);
        int x = (int) (inLayer % width);
        int y = sizeY - 1 - yLayer;
        return new BlockPos(minX + x, startY() + y, minZ + z);
    }

    private void restoreChunkCursorFromTotal() {
        long remaining = Math.max(0L, Math.min(cursor, volume()));
        scanChunkIndex = 0;
        cursorInChunk = 0L;
        while (scanChunkIndex < chunkCount()) {
            long cv = chunkVolume(scanChunkIndex);
            if (remaining < cv) {
                cursorInChunk = remaining;
                return;
            }
            remaining -= cv;
            scanChunkIndex++;
        }
        cursorInChunk = 0L;
    }

'''
s = s[:start] + chunk_helpers + s[end:]

# Hologram target should follow chunk scanner, not old flat positionFor().
old_holo = re.compile(r'''    public BlockPos hologramTarget\(\) \{.*?\n    \}\n\n    public int hologramProgressPermille''', re.S)
new_holo = '''    public BlockPos hologramTarget() {
        if (volume() <= 0L || scanChunkIndex >= chunkCount()) return worldPosition;
        long cv = chunkVolume(scanChunkIndex);
        if (cv <= 0L) return worldPosition;
        long local = Math.max(0L, Math.min(cursorInChunk, cv - 1L));
        return positionForChunkCursor(scanChunkIndex, local);
    }

    public int hologramChunkIndex() {
        return Math.min(scanChunkIndex + 1, Math.max(1, chunkCount()));
    }

    public int hologramChunkCount() {
        return Math.max(1, chunkCount());
    }

    public int hologramProgressPermille'''
s, n = old_holo.subn(new_holo, s, count=1)
if n != 1:
    raise SystemExit('hologramTarget block not found')

# Persist new chunk cursor state.
s = s.replace('        output.putLong("Cursor", cursor);',
              '        output.putLong("Cursor", cursor);\n        output.putInt("ScanChunkIndex", scanChunkIndex);\n        output.putLong("CursorInChunk", cursorInChunk);', 1)
s = s.replace('        cursor = Math.max(0L, input.getLongOr("Cursor", 0L));',
              '''        cursor = Math.max(0L, input.getLongOr("Cursor", 0L));
        scanChunkIndex = Math.max(0, input.getIntOr("ScanChunkIndex", 0));
        cursorInChunk = Math.max(0L, input.getLongOr("CursorInChunk", 0L));
        if (cursor > 0L && scanChunkIndex == 0 && cursorInChunk == 0L) {
            restoreChunkCursorFromTotal();
        }''', 1)

p.write_text(s, encoding='utf-8')

# --- BuilderMenu: only card slots are visible; output stays internal ----------
(java / 'BuilderMenu.java').write_text(r'''package mcjty.rftoolsbuilder;

import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerData;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;

public class BuilderMenu extends AbstractContainerMenu {
    public static final int CONFIG_BASE = 1000;
    public static final int CONFIG_BIAS = 16_384;
    public static final int CONFIG_RANGE = 32_769; // -16384..+16384

    private final BuilderBlockEntity builder;
    private final ContainerData data;

    public BuilderMenu(int containerId, Inventory playerInventory, FriendlyByteBuf extraData) {
        this(containerId, playerInventory,
                (BuilderBlockEntity) playerInventory.player.level().getBlockEntity(extraData.readBlockPos()),
                new SimpleContainerData(12));
    }

    public BuilderMenu(int containerId, Inventory playerInventory, BuilderBlockEntity builder, ContainerData data) {
        super(RFToolsBuilder.BUILDER_MENU.get(), containerId);
        this.builder = builder;
        this.data = data;

        addSlot(new Slot(builder, BuilderBlockEntity.SLOT_SHAPE, 66, 37) {
            @Override public boolean mayPlace(ItemStack stack) { return stack.getItem() instanceof ShapeCardItem; }
            @Override public int getMaxStackSize() { return 1; }
        });
        addSlot(new Slot(builder, BuilderBlockEntity.SLOT_QUARRY, 104, 37) {
            @Override public boolean mayPlace(ItemStack stack) { return stack.getItem() instanceof QuarryCardItem; }
            @Override public int getMaxStackSize() { return 1; }
        });

        // The 9-slot output buffer intentionally remains internal. It is a safety
        // buffer for auto-pushing to adjacent inventories, not a player-facing inventory.
        int playerX = 47;
        int playerY = 148;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(playerInventory, col + row * 9 + 9, playerX + col * 18, playerY + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(playerInventory, col, playerX + col * 18, 206));
        }
        addDataSlots(data);
    }

    public ContainerData data() { return data; }
    public BuilderBlockEntity builder() { return builder; }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (builder == null) return false;
        if (id == 0) { builder.toggleRunning(); return true; }
        if (id == 1) { builder.resetProgress(); return true; }

        if (id >= CONFIG_BASE && id < CONFIG_BASE + 6 * CONFIG_RANGE) {
            int code = id - CONFIG_BASE;
            int field = code / CONFIG_RANGE;
            int value = (code % CONFIG_RANGE) - CONFIG_BIAS;
            if (field < 3) value = Math.max(1, Math.min(512, value));
            else value = Math.max(-16_384, Math.min(16_384, value));
            builder.setConfigValue(field, value);
            return true;
        }
        return false;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        if (index < 0 || index >= slots.size()) return ItemStack.EMPTY;
        Slot slot = slots.get(index);
        if (!slot.hasItem()) return ItemStack.EMPTY;
        ItemStack stack = slot.getItem();
        ItemStack copy = stack.copy();
        int machineSlots = 2;

        if (index < machineSlots) {
            if (!moveItemStackTo(stack, machineSlots, slots.size(), true)) return ItemStack.EMPTY;
        } else if (stack.getItem() instanceof ShapeCardItem) {
            if (!moveItemStackTo(stack, 0, 1, false)) return ItemStack.EMPTY;
        } else if (stack.getItem() instanceof QuarryCardItem) {
            if (!moveItemStackTo(stack, 1, 2, false)) return ItemStack.EMPTY;
        } else {
            return ItemStack.EMPTY;
        }

        if (stack.isEmpty()) slot.setByPlayer(ItemStack.EMPTY);
        else slot.setChanged();
        return copy;
    }

    @Override
    public boolean stillValid(Player player) {
        return builder != null && builder.stillValid(player);
    }
}
''', encoding='utf-8')

# --- BuilderScreen: exact horizontal SIZE/OFFSET reading ---------------------
(client / 'BuilderScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import mcjty.rftoolsbuilder.BuilderBlockEntity;
import mcjty.rftoolsbuilder.BuilderMenu;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import org.lwjgl.glfw.GLFW;

public class BuilderScreen extends AbstractContainerScreen<BuilderMenu> {
    private static final int BG = 0xFF080C10;
    private static final int PANEL = 0xFF131B22;
    private static final int PANEL_2 = 0xFF1A232C;
    private static final int BORDER = 0xFF34424C;
    private static final int CYAN = 0xFF19DDF2;
    private static final int CYAN_DARK = 0xFF087D8C;
    private static final int TEXT = 0xFFE7EEF2;
    private static final int MUTED = 0xFF75838D;
    private static final int ORANGE = 0xFFFF9B24;

    private final EditBox[] fields = new EditBox[6];
    private Button startStop;
    private boolean syncingFields;

    public BuilderScreen(BuilderMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 256, 232);
        this.inventoryLabelY = 139;
        this.titleLabelY = 7;
    }

    @Override
    protected void init() {
        super.init();

        startStop = addRenderableWidget(Button.builder(Component.empty(), b -> sendButton(0))
                .bounds(leftPos + 151, topPos + 29, 87, 18).build());

        // Horizontal reading approved by design:
        // SIZE:   X [ ]  Y [ ]  Z [ ]
        // OFFSET: X [ ]  Y [ ]  Z [ ]
        int[] xs = {99, 151, 203, 99, 151, 203};
        int[] ys = {80, 80, 80, 107, 107, 107};
        for (int i = 0; i < fields.length; i++) {
            final int field = i;
            EditBox box = new EditBox(font, leftPos + xs[i], topPos + ys[i], 38, 16, Component.empty());
            box.setMaxLength(6);
            box.setFilter(value -> value.isEmpty() || value.equals("-") || value.matches("-?\\d{0,5}"));
            syncingFields = true;
            box.setValue(Integer.toString(menu.data().get(3 + i)));
            syncingFields = false;
            box.setResponder(value -> {
                if (syncingFields || value.isEmpty() || value.equals("-")) return;
                try {
                    int parsed = Integer.parseInt(value);
                    if (field < 3) parsed = Math.max(1, Math.min(512, parsed));
                    else parsed = Math.max(-16_384, Math.min(16_384, parsed));
                    sendConfig(field, parsed);
                } catch (NumberFormatException ignored) { }
            });
            fields[i] = addRenderableWidget(box);
        }
        updateWidgets();
    }

    @Override
    protected void containerTick() {
        super.containerTick();
        updateWidgets();
        syncingFields = true;
        for (int i = 0; i < fields.length; i++) {
            if (fields[i] != null && !fields[i].isFocused()) {
                String expected = Integer.toString(menu.data().get(3 + i));
                if (!expected.equals(fields[i].getValue())) fields[i].setValue(expected);
            }
        }
        syncingFields = false;
    }

    private void updateWidgets() {
        boolean hasShape = menu.getSlot(0).hasItem();
        for (EditBox field : fields) if (field != null) field.setEditable(hasShape);
        if (startStop != null) {
            startStop.setMessage(Component.translatable(menu.data().get(2) != 0
                    ? "gui.rftoolsbuilder.stop" : "gui.rftoolsbuilder.start"));
        }
    }

    private void sendConfig(int field, int value) {
        int id = BuilderMenu.CONFIG_BASE + field * BuilderMenu.CONFIG_RANGE + (value + BuilderMenu.CONFIG_BIAS);
        sendButton(id);
    }

    private void sendButton(int id) {
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, 0xFF05080B);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, BORDER);
        g.fill(x1 + 2, y1 + 2, x2 - 2, y2 - 2, PANEL);
        g.fill(x1 + 4, y1 + 2, Math.min(x2 - 4, x1 + 22), y1 + 3, CYAN_DARK);
    }

    private static String compact(long value) {
        if (value >= 1_000_000L) return String.format(java.util.Locale.ROOT, "%.1fM", value / 1_000_000.0);
        if (value >= 1_000L) return String.format(java.util.Locale.ROOT, "%.1fK", value / 1_000.0);
        return Long.toString(value);
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        int x = leftPos, y = topPos;
        g.fill(x, y, x + imageWidth, y + imageHeight, BG);
        g.fill(x + 2, y + 2, x + imageWidth - 2, y + imageHeight - 2, PANEL_2);
        g.fill(x + 4, y + 4, x + imageWidth - 4, y + imageHeight - 4, BG);

        g.fill(x + 8, y + 3, x + 60, y + 5, CYAN_DARK);
        g.fill(x + imageWidth - 60, y + 3, x + imageWidth - 8, y + 5, CYAN_DARK);
        g.centeredText(font, Component.literal("QUANTUM BUILDER"), x + imageWidth / 2, y + 8, TEXT);
        g.fill(x + 49, y + 18, x + imageWidth - 49, y + 19, CYAN_DARK);
        g.fill(x + imageWidth - 84, y + 18, x + imageWidth - 74, y + 19, ORANGE);

        // Energy
        panel(g, x + 8, y + 22, x + 46, y + 68);
        g.text(font, Component.literal("ENERGY"), x + 11, y + 27, MUTED);
        int energy = menu.data().get(0);
        int maxEnergy = Math.max(1, menu.data().get(1));
        g.text(font, Component.literal(compact(energy)), x + 11, y + 41, CYAN);
        g.text(font, Component.literal((energy * 100 / maxEnergy) + "%"), x + 11, y + 54, CYAN);

        // Cards
        panel(g, x + 50, y + 22, x + 140, y + 68);
        g.text(font, Component.literal("SHAPE"), x + 59, y + 25, CYAN_DARK);
        g.text(font, Component.literal("QUARRY"), x + 96, y + 25, CYAN_DARK);
        g.fill(x + 63, y + 34, x + 87, y + 58, 0xFF071016);
        g.fill(x + 101, y + 34, x + 125, y + 58, 0xFF071016);

        // Operation / progress
        panel(g, x + 144, y + 22, x + 246, y + 68);
        int status = menu.data().get(11);
        int cursor = menu.data().get(9);
        int volume = Math.max(1, menu.data().get(10));
        int permille = (int)(1000L * Math.min(cursor, volume) / volume);
        int pw = (int)(88L * Math.min(cursor, volume) / volume);
        g.text(font, statusText(status), x + 150, y + 50, CYAN);
        g.fill(x + 150, y + 61, x + 238, y + 65, 0xFF05080A);
        g.fill(x + 150, y + 61, x + 150 + pw, y + 65, CYAN);
        g.text(font, Component.literal((permille / 10) + "." + (permille % 10) + "%"), x + 210, y + 50, MUTED);

        // Area configuration — two clean horizontal lines.
        panel(g, x + 50, y + 72, x + 246, y + 132);
        boolean shape = menu.getSlot(0).hasItem();
        int cc = shape ? TEXT : MUTED;
        g.text(font, Component.literal("SIZE:"), x + 56, y + 84, shape ? CYAN_DARK : MUTED);
        g.text(font, Component.literal("OFFSET:"), x + 56, y + 111, shape ? CYAN_DARK : MUTED);

        int[] axisX = {91, 143, 195};
        String[] axes = {"X", "Y", "Z"};
        for (int i = 0; i < 3; i++) {
            g.text(font, Component.literal(axes[i]), x + axisX[i], y + 84, cc);
            g.text(font, Component.literal(axes[i]), x + axisX[i], y + 111, cc);
        }
        g.text(font, Component.literal("Offset X/Z: até ±1024 chunks"), x + 56, y + 125, MUTED);

        // Player inventory only. Output buffer intentionally hidden.
        panel(g, x + 42, y + 140, x + 214, y + 228);
        g.text(font, Component.literal("INVENTORY"), x + 47, y + 136, MUTED);
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++) {
            int sx = x + 45 + col * 18, sy = y + 146 + row * 18;
            g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
            g.fill(sx + 1, sy + 1, sx + 17, sy + 17, PANEL);
        }
        for (int col = 0; col < 9; col++) {
            int sx = x + 45 + col * 18, sy = y + 204;
            g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
            g.fill(sx + 1, sy + 1, sx + 17, sy + 17, PANEL);
        }
    }

    private static Component statusText(int status) {
        return switch (status) {
            case BuilderBlockEntity.STATUS_RUNNING -> Component.translatable("gui.rftoolsbuilder.status.running");
            case BuilderBlockEntity.STATUS_NO_CARD -> Component.translatable("gui.rftoolsbuilder.status.no_card");
            case BuilderBlockEntity.STATUS_NO_ENERGY -> Component.translatable("gui.rftoolsbuilder.status.no_energy");
            case BuilderBlockEntity.STATUS_OUTPUT_FULL -> Component.translatable("gui.rftoolsbuilder.status.output_full");
            case BuilderBlockEntity.STATUS_DONE -> Component.translatable("gui.rftoolsbuilder.status.done");
            default -> Component.translatable("gui.rftoolsbuilder.status.idle");
        };
    }

    @Override
    public boolean keyPressed(KeyEvent event) {
        for (EditBox field : fields) {
            if (field != null && field.isFocused()) {
                if (field.keyPressed(event)) return true;
                if (event.key() != GLFW.GLFW_KEY_TAB && event.key() != GLFW.GLFW_KEY_ESCAPE) return true;
                break;
            }
        }
        return super.keyPressed(event);
    }

    @Override
    protected void extractLabels(GuiGraphicsExtractor graphics, int mouseX, int mouseY) { }
}
''', encoding='utf-8')

# --- Filter screen: actual vertical list, not a grid --------------------------
(client / 'QuarryFilterScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import mcjty.rftoolsbuilder.FilterTagPayload;
import mcjty.rftoolsbuilder.QuarryCardItem;
import mcjty.rftoolsbuilder.QuarryFilterMenu;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.client.network.ClientPacketDistributor;
import org.lwjgl.glfw.GLFW;

public class QuarryFilterScreen extends AbstractContainerScreen<QuarryFilterMenu> {
    private static final int BG = 0xFF080C10;
    private static final int PANEL = 0xFF111820;
    private static final int PANEL_2 = 0xFF18222B;
    private static final int BORDER = 0xFF33434E;
    private static final int CYAN = 0xFF18DDF3;
    private static final int CYAN_DARK = 0xFF087A88;
    private static final int TEXT = 0xFFE8F1F4;
    private static final int MUTED = 0xFF74838D;
    private static final int SELECTED = 0xFF17333D;
    private static final int VISIBLE_ROWS = 6;

    private int selected = -1;
    private int scroll = 0;
    private Button modeButton, damageButton, nbtButton, modButton;
    private Button removeButton, expandButton, upButton, downButton;
    private EditBox tagBox;

    public QuarryFilterScreen(QuarryFilterMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 256, 292);
        this.inventoryLabelY = 198;
        this.titleLabelY = 7;
    }

    @Override
    protected void init() {
        super.init();
        modeButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(0)).bounds(leftPos + 8, topPos + 24, 68, 18).build());
        modButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(3)).bounds(leftPos + 78, topPos + 24, 54, 18).build());
        nbtButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(2)).bounds(leftPos + 134, topPos + 24, 54, 18).build());
        damageButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(1)).bounds(leftPos + 190, topPos + 24, 58, 18).build());

        tagBox = new EditBox(font, leftPos + 8, topPos + 47, 180, 16, Component.literal("Tag"));
        tagBox.setMaxLength(80);
        tagBox.setHint(Component.literal("c:ores"));
        addRenderableWidget(tagBox);
        addRenderableWidget(Button.builder(Component.literal("+ TAG"), b -> addTag()).bounds(leftPos + 190, topPos + 47, 58, 16).build());

        upButton = addRenderableWidget(Button.builder(Component.literal("▲"), b -> { if (scroll > 0) scroll--; })
                .bounds(leftPos + 228, topPos + 72, 20, 18).build());
        downButton = addRenderableWidget(Button.builder(Component.literal("▼"), b -> {
            int max = Math.max(0, QuarryCardItem.entryCount(card()) - VISIBLE_ROWS);
            if (scroll < max) scroll++;
        }).bounds(leftPos + 228, topPos + 142, 20, 18).build());

        removeButton = addRenderableWidget(Button.builder(Component.literal("REMOVE"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.REMOVE_BASE + selected);
        }).bounds(leftPos + 8, topPos + 174, 64, 18).build());
        expandButton = addRenderableWidget(Button.builder(Component.literal("EXPAND"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.EXPAND_BASE + selected);
        }).bounds(leftPos + 74, topPos + 174, 64, 18).build());
        addRenderableWidget(Button.builder(Component.literal("CLEAR"), b -> { selected = -1; scroll = 0; send(4); })
                .bounds(leftPos + 184, topPos + 174, 64, 18).build());
        syncButtons();
    }

    private void addTag() {
        String value = tagBox.getValue().trim();
        if (value.isEmpty()) return;
        ClientPacketDistributor.sendToServer(new FilterTagPayload(menu.cardSlot(), value));
        tagBox.setValue("");
        selected = -1;
    }

    private void send(int id) {
        if (minecraft != null && minecraft.gameMode != null) minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
    }

    private ItemStack card() { return menu.cardStack(); }

    private String entryLabel(int combined) {
        int tags = QuarryCardItem.tagCount(card());
        if (combined < tags) return "#" + QuarryCardItem.getTag(card(), combined);
        if (minecraft == null || minecraft.level == null) return "";
        ItemStack item = QuarryCardItem.getFilterItem(card(), combined - tags, minecraft.level.registryAccess());
        return item.isEmpty() ? "" : item.getHoverName().getString();
    }

    private ItemStack entryItem(int combined) {
        int tags = QuarryCardItem.tagCount(card());
        if (combined < tags || minecraft == null || minecraft.level == null) return ItemStack.EMPTY;
        return QuarryCardItem.getFilterItem(card(), combined - tags, minecraft.level.registryAccess());
    }

    private void syncButtons() {
        int count = QuarryCardItem.entryCount(card());
        int tags = QuarryCardItem.tagCount(card());
        if (selected >= count) selected = -1;
        int maxScroll = Math.max(0, count - VISIBLE_ROWS);
        if (scroll > maxScroll) scroll = maxScroll;

        modeButton.setMessage(Component.literal(QuarryCardItem.blacklist(card()) ? "BLACKLIST" : "WHITELIST"));
        modButton.setMessage(Component.literal(QuarryCardItem.modMode(card()) ? "MOD: ON" : "MOD: OFF"));
        nbtButton.setMessage(Component.literal(QuarryCardItem.nbtMode(card()) ? "DATA: ON" : "DATA: OFF"));
        damageButton.setMessage(Component.literal(QuarryCardItem.damageMode(card()) ? "DMG: ON" : "DMG: OFF"));
        removeButton.active = selected >= 0;
        expandButton.active = selected >= tags && selected < count;
        upButton.active = scroll > 0;
        downButton.active = scroll < maxScroll;
    }

    @Override
    protected void containerTick() {
        super.containerTick();
        syncButtons();
    }

    @Override
    public boolean mouseClicked(MouseButtonEvent event, boolean doubleClick) {
        double mx = event.x(), my = event.y();
        int lx = (int) mx - leftPos;
        int ly = (int) my - topPos;
        if (lx >= 9 && lx < 224 && ly >= 72 && ly < 168) {
            int row = (ly - 72) / 16;
            if (row >= 0 && row < VISIBLE_ROWS) {
                int idx = scroll + row;
                if (idx < QuarryCardItem.entryCount(card())) {
                    selected = idx;
                    return true;
                }
            }
        }
        return super.mouseClicked(event, doubleClick);
    }

    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, 0xFF05080B);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, BORDER);
        g.fill(x1 + 2, y1 + 2, x2 - 2, y2 - 2, PANEL);
        g.fill(x1 + 4, y1 + 2, Math.min(x2 - 4, x1 + 28), y1 + 3, CYAN_DARK);
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        int x = leftPos, y = topPos;
        g.fill(x, y, x + imageWidth, y + imageHeight, BG);
        g.fill(x + 2, y + 2, x + imageWidth - 2, y + imageHeight - 2, PANEL_2);
        g.fill(x + 4, y + 4, x + imageWidth - 4, y + imageHeight - 4, BG);
        g.fill(x + 8, y + 3, x + 64, y + 5, CYAN_DARK);
        g.fill(x + imageWidth - 64, y + 3, x + imageWidth - 8, y + 5, CYAN_DARK);
        g.centeredText(font, Component.literal("QUARRY CARD FILTER"), x + imageWidth / 2, y + 8, TEXT);

        panel(g, x + 6, y + 20, x + 250, y + 66);
        panel(g, x + 6, y + 67, x + 250, y + 170);
        panel(g, x + 6, y + 170, x + 250, y + 196);
        panel(g, x + 42, y + 202, x + 214, y + 286);

        int count = QuarryCardItem.entryCount(card());
        g.text(font, Component.literal("FILTER LIST  " + count + "/18"), x + 10, y + 68, CYAN_DARK);
        for (int row = 0; row < VISIBLE_ROWS; row++) {
            int idx = scroll + row;
            int ry = y + 72 + row * 16;
            g.fill(x + 9, ry, x + 224, ry + 15, idx == selected ? SELECTED : 0xFF0A1015);
            g.fill(x + 9, ry, x + 10, ry + 15, idx == selected ? CYAN : BORDER);
            if (idx < count) {
                ItemStack icon = entryItem(idx);
                int tx = x + 14;
                if (!icon.isEmpty()) {
                    g.item(icon, x + 12, ry - 1);
                    tx = x + 31;
                }
                String label = entryLabel(idx);
                if (label.length() > 29) label = label.substring(0, 28) + "…";
                g.text(font, Component.literal(label), tx, ry + 3, TEXT);
            }
        }

        g.text(font, Component.literal("Clique no item = exato  •  Shift-clique = tags"), x + 9, y + 198, MUTED);
        g.text(font, Component.literal("INVENTORY"), x + 47, y + 199, CYAN_DARK);
    }

    @Override
    public boolean keyPressed(KeyEvent event) {
        if (tagBox != null && tagBox.isFocused()) {
            if (tagBox.keyPressed(event)) return true;
            if (event.key() != GLFW.GLFW_KEY_TAB && event.key() != GLFW.GLFW_KEY_ESCAPE) return true;
        }
        return super.keyPressed(event);
    }

    @Override
    protected void extractLabels(GuiGraphicsExtractor g, int mouseX, int mouseY) { }
}
''', encoding='utf-8')

# Filter menu inventory currently begins at x47/y211 already; leave behavior intact.

# --- Hologram: flip the screen 180 degrees in its own plane -------------------
p = client / 'QuantumBuilderBlockEntityRenderer.java'
s = p.read_text(encoding='utf-8')
needle = '        placeOnFront(poseStack, state.facing);\n        poseStack.scale(0.0125F, 0.0125F, 0.0125F);'
repl = '''        placeOnFront(poseStack, state.facing);
        // Font coordinates are upside-down on the projected front plane in 26.1.
        // Rotate in-plane so the hologram reads upright from the player side.
        poseStack.mulPose(Axis.ZP.rotationDegrees(180.0F));
        poseStack.scale(0.0125F, 0.0125F, 0.0125F);'''
if needle not in s:
    raise SystemExit('hologram placement anchor not found')
s = s.replace(needle, repl, 1)

# Add chunk sequence to the hologram line.
s = s.replace('String chunk = " CHUNK " + state.chunkX + " / " + state.chunkZ + " ";',
              'String chunk = " CHUNK " + state.chunkX + " / " + state.chunkZ + " ";', 1)
p.write_text(s, encoding='utf-8')

# Version bump.
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"(?m)^version\s*=\s*['\"]3\.0\.2['\"]", "version = '3.0.3'", s, count=1)
if n != 1:
    raise SystemExit('3.0.2 version not found')
p.write_text(s, encoding='utf-8')

print('Quantum Tools 3.0.3: chunk-first scan, horizontal UI, hidden output, list filter, hologram flip')

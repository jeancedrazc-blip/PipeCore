from pathlib import Path
import re

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'

# -----------------------------------------------------------------------------
# Shape Card: persistent Size + Offset stored on the ItemStack itself.
# -----------------------------------------------------------------------------
(java / 'ShapeCardItem.java').write_text(r'''package mcjty.rftoolsbuilder;

import net.minecraft.ChatFormatting;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.item.component.TooltipDisplay;

import java.util.function.Consumer;

public class ShapeCardItem extends Item {
    public static final int DEFAULT_SIZE_X = 16;
    public static final int DEFAULT_SIZE_Y = 64;
    public static final int DEFAULT_SIZE_Z = 16;
    public static final int DEFAULT_OFFSET_X = -8;
    public static final int DEFAULT_OFFSET_Y = -64;
    public static final int DEFAULT_OFFSET_Z = -8;

    private static final String[] KEYS = {
            "SizeX", "SizeY", "SizeZ", "OffsetX", "OffsetY", "OffsetZ"
    };
    private static final int[] DEFAULTS = {
            DEFAULT_SIZE_X, DEFAULT_SIZE_Y, DEFAULT_SIZE_Z,
            DEFAULT_OFFSET_X, DEFAULT_OFFSET_Y, DEFAULT_OFFSET_Z
    };

    public ShapeCardItem(Properties properties) {
        super(properties.stacksTo(1));
    }

    public static int getField(ItemStack stack, int field) {
        if (field < 0 || field >= KEYS.length) return 0;
        CustomData data = stack.getOrDefault(DataComponents.CUSTOM_DATA, CustomData.EMPTY);
        CompoundTag tag = data.copyTag();
        return tag.getInt(KEYS[field]).orElse(DEFAULTS[field]);
    }

    public static void setField(ItemStack stack, int field, int value) {
        if (field < 0 || field >= KEYS.length) return;
        CustomData.update(DataComponents.CUSTOM_DATA, stack, tag -> tag.putInt(KEYS[field], value));
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, TooltipDisplay display,
                                Consumer<Component> builder, TooltipFlag flag) {
        super.appendHoverText(stack, context, display, builder, flag);
        builder.accept(Component.literal("Área: " + getField(stack, 0) + " × " + getField(stack, 1) + " × " + getField(stack, 2))
                .withStyle(ChatFormatting.AQUA));
        builder.accept(Component.literal("Offset: " + getField(stack, 3) + ", " + getField(stack, 4) + ", " + getField(stack, 5))
                .withStyle(ChatFormatting.DARK_GRAY));
    }
}
''', encoding='utf-8')

# -----------------------------------------------------------------------------
# Register shape_card_def as the real ShapeCardItem.
# -----------------------------------------------------------------------------
p = java / 'RFToolsBuilder.java'
s = p.read_text(encoding='utf-8')
s = s.replace(
    'public static final DeferredItem<Item> SHAPE_CARD_DEF = ITEMS.registerItem(\n            "shape_card_def", Item::new, properties -> properties.stacksTo(1)\n    );',
    'public static final DeferredItem<ShapeCardItem> SHAPE_CARD_DEF = ITEMS.registerItem(\n            "shape_card_def", ShapeCardItem::new, properties -> properties.stacksTo(1)\n    );'
)
p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# Builder BlockEntity: separate Shape/Quarry slots, Shape Card owns dimensions.
# Keep the rest of mining/output/energy logic intact.
# -----------------------------------------------------------------------------
p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')

s = s.replace(
'''    public static final int SLOT_CARD = 0;
    public static final int FIRST_OUTPUT = 1;
    public static final int OUTPUT_SLOTS = 9;
    public static final int TOTAL_SLOTS = 10;''',
'''    public static final int SLOT_SHAPE = 0;
    public static final int SLOT_QUARRY = 1;
    public static final int FIRST_OUTPUT = 2;
    public static final int OUTPUT_SLOTS = 9;
    public static final int TOTAL_SLOTS = 11;''')

s = s.replace(
'''        ItemStack cardStack = builder.items.get(SLOT_CARD);
        if (!(cardStack.getItem() instanceof QuarryCardItem card)) {
            builder.status = STATUS_NO_CARD;
            return;
        }

        builder.work((ServerLevel) level, card.mode());''',
'''        ItemStack shapeStack = builder.items.get(SLOT_SHAPE);
        ItemStack quarryStack = builder.items.get(SLOT_QUARRY);
        if (!(shapeStack.getItem() instanceof ShapeCardItem) || !(quarryStack.getItem() instanceof QuarryCardItem card)) {
            builder.status = STATUS_NO_CARD;
            return;
        }

        builder.work((ServerLevel) level, card.mode());''')

# Replace adjust() with direct validated typed-field assignment that is persisted to Shape Card.
old_adjust = re.compile(r'''    public void adjust\(int field, int delta\) \{.*?\n    \}\n\n    public void resetProgress\(\)''', re.S)
new_adjust = '''    public boolean hasShapeCard() {
        return items.get(SLOT_SHAPE).getItem() instanceof ShapeCardItem;
    }

    public boolean hasQuarryCard() {
        return items.get(SLOT_QUARRY).getItem() instanceof QuarryCardItem;
    }

    public void setConfigValue(int field, int value) {
        ItemStack shapeStack = items.get(SLOT_SHAPE);
        if (!(shapeStack.getItem() instanceof ShapeCardItem)) return;
        int normalized = field < 3 ? clampSize(value) : clampOffset(value);
        switch (field) {
            case 0 -> sizeX = normalized;
            case 1 -> sizeY = normalized;
            case 2 -> sizeZ = normalized;
            case 3 -> offsetX = normalized;
            case 4 -> offsetY = normalized;
            case 5 -> offsetZ = normalized;
            default -> { return; }
        }
        ShapeCardItem.setField(shapeStack, field, normalized);
        resetProgress();
        setChanged();
    }

    private void loadShapeCardConfig() {
        ItemStack shapeStack = items.get(SLOT_SHAPE);
        if (!(shapeStack.getItem() instanceof ShapeCardItem)) return;
        sizeX = clampSize(ShapeCardItem.getField(shapeStack, 0));
        sizeY = clampSize(ShapeCardItem.getField(shapeStack, 1));
        sizeZ = clampSize(ShapeCardItem.getField(shapeStack, 2));
        offsetX = clampOffset(ShapeCardItem.getField(shapeStack, 3));
        offsetY = clampOffset(ShapeCardItem.getField(shapeStack, 4));
        offsetZ = clampOffset(ShapeCardItem.getField(shapeStack, 5));
    }

    public void resetProgress()'''
s, n = old_adjust.subn(new_adjust, s, count=1)
assert n == 1, 'adjust method not found'

s = s.replace('return Math.max(1, Math.min(128, value));', 'return Math.max(1, Math.min(512, value));')
s = s.replace('return Math.max(-256, Math.min(256, value));', 'return Math.max(-512, Math.min(512, value));')

# setItem validation and card sync.
old_setitem = '''    public void setItem(int slot, ItemStack stack) {
        if (slot == SLOT_CARD && !stack.isEmpty() && !(stack.getItem() instanceof QuarryCardItem)) return;
        items.set(slot, stack);
        if (slot == SLOT_CARD) resetProgress();
        setChanged();
    }'''
new_setitem = '''    public void setItem(int slot, ItemStack stack) {
        if (slot == SLOT_SHAPE && !stack.isEmpty() && !(stack.getItem() instanceof ShapeCardItem)) return;
        if (slot == SLOT_QUARRY && !stack.isEmpty() && !(stack.getItem() instanceof QuarryCardItem)) return;
        items.set(slot, stack);
        if (slot == SLOT_SHAPE) {
            loadShapeCardConfig();
            resetProgress();
        } else if (slot == SLOT_QUARRY) {
            resetProgress();
        }
        setChanged();
    }'''
assert old_setitem in s, 'setItem block not found'
s = s.replace(old_setitem, new_setitem)

p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# Menu: two distinct card slots + encoded direct-value config commands.
# -----------------------------------------------------------------------------
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
    public static final int CONFIG_RANGE = 1025; // -512..+512 encoded as 0..1024

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

        addSlot(new Slot(builder, BuilderBlockEntity.SLOT_SHAPE, 64, 32) {
            @Override public boolean mayPlace(ItemStack stack) { return stack.getItem() instanceof ShapeCardItem; }
            @Override public int getMaxStackSize() { return 1; }
        });
        addSlot(new Slot(builder, BuilderBlockEntity.SLOT_QUARRY, 100, 32) {
            @Override public boolean mayPlace(ItemStack stack) { return stack.getItem() instanceof QuarryCardItem; }
            @Override public int getMaxStackSize() { return 1; }
        });

        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 3; col++) {
                int slot = BuilderBlockEntity.FIRST_OUTPUT + row * 3 + col;
                addSlot(new Slot(builder, slot, 184 + col * 18, 86 + row * 18) {
                    @Override public boolean mayPlace(ItemStack stack) { return false; }
                });
            }
        }

        int playerX = 47;
        int playerY = 166;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(playerInventory, col + row * 9 + 9, playerX + col * 18, playerY + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(playerInventory, col, playerX + col * 18, 224));
        }
        addDataSlots(data);
    }

    public ContainerData data() { return data; }
    public BuilderBlockEntity builder() { return builder; }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        if (builder == null) return false;
        if (id == 0) {
            builder.toggleRunning();
            return true;
        }
        if (id == 1) {
            builder.resetProgress();
            return true;
        }
        if (id >= CONFIG_BASE && id < CONFIG_BASE + 6 * CONFIG_RANGE) {
            int code = id - CONFIG_BASE;
            int field = code / CONFIG_RANGE;
            int value = (code % CONFIG_RANGE) - 512;
            if (field < 3 && value < 1) value = 1;
            builder.setConfigValue(field, value);
            return true;
        }
        return false;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        Slot slot = slots.get(index);
        if (!slot.hasItem()) return ItemStack.EMPTY;
        ItemStack stack = slot.getItem();
        ItemStack copy = stack.copy();
        int machineSlots = 11;

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

# -----------------------------------------------------------------------------
# Cyan industrial UI with typed numeric fields. No +/- controls.
# -----------------------------------------------------------------------------
client = java / 'client'
(client / 'BuilderScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import mcjty.rftoolsbuilder.BuilderBlockEntity;
import mcjty.rftoolsbuilder.BuilderMenu;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;

public class BuilderScreen extends AbstractContainerScreen<BuilderMenu> {
    private static final int BG = 0xFF0A0E12;
    private static final int PANEL = 0xFF141B22;
    private static final int PANEL_2 = 0xFF1A232C;
    private static final int BORDER = 0xFF3A4651;
    private static final int CYAN = 0xFF19DDF2;
    private static final int CYAN_DARK = 0xFF087D8C;
    private static final int TEXT = 0xFFE7EEF2;
    private static final int MUTED = 0xFF75838D;
    private static final int ORANGE = 0xFFFF9B24;

    private final EditBox[] fields = new EditBox[6];
    private Button startStop;
    private boolean syncingFields = false;

    public BuilderScreen(BuilderMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 256, 252);
        this.inventoryLabelY = 154;
        this.titleLabelY = 7;
    }

    @Override
    protected void init() {
        super.init();

        startStop = addRenderableWidget(Button.builder(Component.translatable(menu.data().get(2) != 0
                        ? "gui.rftoolsbuilder.stop" : "gui.rftoolsbuilder.start"),
                b -> sendButton(0)).bounds(leftPos + 150, topPos + 28, 88, 20).build());

        int[] xs = {58, 58, 58, 132, 132, 132};
        int[] ys = {88, 106, 124, 88, 106, 124};
        for (int i = 0; i < fields.length; i++) {
            final int field = i;
            EditBox box = new EditBox(font, leftPos + xs[i], topPos + ys[i], 48, 14, Component.empty());
            box.setMaxLength(4);
            box.setFilter(value -> value.isEmpty() || value.equals("-") || value.matches("-?\\d{0,3}"));
            syncingFields = true;
            box.setValue(Integer.toString(menu.data().get(3 + i)));
            syncingFields = false;
            box.setResponder(value -> {
                if (syncingFields || value.isEmpty() || value.equals("-")) return;
                try {
                    int parsed = Integer.parseInt(value);
                    if (field < 3) parsed = Math.max(1, Math.min(512, parsed));
                    else parsed = Math.max(-512, Math.min(512, parsed));
                    sendConfig(field, parsed);
                } catch (NumberFormatException ignored) { }
            });
            fields[i] = addRenderableWidget(box);
        }
        updateFieldState();
    }

    @Override
    public void tick() {
        super.tick();
        updateFieldState();
        if (startStop != null) {
            startStop.setMessage(Component.translatable(menu.data().get(2) != 0
                    ? "gui.rftoolsbuilder.stop" : "gui.rftoolsbuilder.start"));
        }
        syncingFields = true;
        for (int i = 0; i < fields.length; i++) {
            if (fields[i] != null && !fields[i].isFocused()) {
                String expected = Integer.toString(menu.data().get(3 + i));
                if (!expected.equals(fields[i].getValue())) fields[i].setValue(expected);
            }
        }
        syncingFields = false;
    }

    private void updateFieldState() {
        boolean enabled = menu.getSlot(0).hasItem();
        for (EditBox field : fields) {
            if (field != null) field.setEditable(enabled);
        }
    }

    private void sendConfig(int field, int value) {
        int id = BuilderMenu.CONFIG_BASE + field * BuilderMenu.CONFIG_RANGE + (value + 512);
        sendButton(id);
    }

    private void sendButton(int id) {
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, BORDER);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, PANEL);
    }

    private void cyanFrame(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y1 + 1, CYAN_DARK);
        g.fill(x1, y2 - 1, x2, y2, CYAN_DARK);
        g.fill(x1, y1, x1 + 1, y2, CYAN_DARK);
        g.fill(x2 - 1, y1, x2, y2, CYAN_DARK);
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        int x = leftPos;
        int y = topPos;
        g.fill(x, y, x + imageWidth, y + imageHeight, BG);
        g.fill(x + 2, y + 2, x + imageWidth - 2, y + imageHeight - 2, PANEL_2);
        g.fill(x + 4, y + 4, x + imageWidth - 4, y + imageHeight - 4, BG);

        // Cyan industrial edge accents.
        g.fill(x + 8, y + 3, x + 56, y + 5, CYAN_DARK);
        g.fill(x + imageWidth - 56, y + 3, x + imageWidth - 8, y + 5, CYAN_DARK);
        g.fill(x + 3, y + 20, x + 5, y + 92, CYAN_DARK);
        g.fill(x + imageWidth - 5, y + 20, x + imageWidth - 3, y + 92, CYAN_DARK);

        g.centeredText(font, Component.literal("BUILDER"), x + imageWidth / 2, y + 8, TEXT);

        // Energy panel.
        panel(g, x + 8, y + 22, x + 46, y + 144);
        g.text(font, Component.literal("ENERGY"), x + 11, y + 27, MUTED);
        g.fill(x + 15, y + 42, x + 25, y + 127, 0xFF05080A);
        g.fill(x + 16, y + 43, x + 24, y + 126, 0xFF102129);
        int energy = menu.data().get(0);
        int maxEnergy = Math.max(1, menu.data().get(1));
        int h = (int)(82L * energy / maxEnergy);
        g.fill(x + 16, y + 126 - h, x + 24, y + 126, CYAN);
        g.text(font, Component.literal(Integer.toString(energy)), x + 27, y + 56, CYAN);
        g.text(font, Component.literal("FE"), x + 27, y + 68, MUTED);
        g.text(font, Component.literal((energy * 100 / maxEnergy) + "%"), x + 27, y + 87, CYAN);

        // Card section.
        panel(g, x + 50, y + 22, x + 140, y + 62);
        cyanFrame(g, x + 59, y + 27, x + 85, y + 55);
        cyanFrame(g, x + 95, y + 27, x + 121, y + 55);
        g.text(font, Component.literal("SHAPE"), x + 58, y + 17, MUTED);
        g.text(font, Component.literal("QUARRY"), x + 96, y + 17, MUTED);

        // Status/progress area.
        panel(g, x + 144, y + 22, x + 246, y + 76);
        g.text(font, Component.literal("STATUS"), x + 150, y + 52, MUTED);
        g.text(font, statusText(menu.data().get(11)), x + 188, y + 52, CYAN);
        int cursor = menu.data().get(9);
        int volume = Math.max(1, menu.data().get(10));
        int pw = (int)(88L * Math.min(cursor, volume) / volume);
        g.fill(x + 150, y + 64, x + 238, y + 69, 0xFF05080A);
        g.fill(x + 150, y + 64, x + 150 + pw, y + 69, CYAN);

        // Typed size/offset configuration.
        panel(g, x + 50, y + 80, x + 176, y + 146);
        boolean shape = menu.getSlot(0).hasItem();
        int configColor = shape ? CYAN : MUTED;
        g.text(font, Component.literal("SIZE"), x + 54, y + 78, configColor);
        g.text(font, Component.literal("OFFSET"), x + 123, y + 78, configColor);
        String[] axis = {"X", "Y", "Z"};
        for (int i = 0; i < 3; i++) {
            g.text(font, Component.literal(axis[i]), x + 51, y + 91 + i * 18, configColor);
            g.text(font, Component.literal(axis[i]), x + 125, y + 91 + i * 18, configColor);
        }
        if (!shape) {
            g.text(font, Component.literal("Insira um Shape Card"), x + 69, y + 137, MUTED);
        }

        // Output buffer.
        panel(g, x + 180, y + 80, x + 244, y + 146);
        g.text(font, Component.literal("OUTPUT"), x + 187, y + 78, MUTED);
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 3; col++) {
                int sx = x + 182 + col * 18;
                int sy = y + 84 + row * 18;
                g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
                g.fill(sx + 1, sy + 1, sx + 17, sy + 17, 0xFF141B22);
            }
        }

        // Inventory framing.
        panel(g, x + 42, y + 158, x + 214, y + 246);
        g.text(font, Component.literal("INVENTORY"), x + 47, y + 151, MUTED);
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++) {
            int sx = x + 45 + col * 18;
            int sy = y + 164 + row * 18;
            g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
            g.fill(sx + 1, sy + 1, sx + 17, sy + 17, 0xFF141B22);
        }
        for (int col = 0; col < 9; col++) {
            int sx = x + 45 + col * 18;
            int sy = y + 222;
            g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
            g.fill(sx + 1, sy + 1, sx + 17, sy + 17, 0xFF141B22);
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
    protected void extractLabels(GuiGraphicsExtractor graphics, int mouseX, int mouseY) {
        // All labels are drawn by the styled background.
    }
}
''', encoding='utf-8')

# Bump project version for the new functional/UI revision.
build = root / 'build.gradle'
bs = build.read_text(encoding='utf-8')
bs = re.sub(r"(?m)^version\s*=\s*['\"][^'\"]+['\"]", "version = '7.0.5-port.2'", bs, count=1)
build.write_text(bs, encoding='utf-8')

print('Applied Builder port.2: dual Shape/Quarry cards, typed Size/Offset, cyan industrial UI')

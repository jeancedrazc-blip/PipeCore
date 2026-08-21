from pathlib import Path
import re, struct, zlib

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'
res = root / 'src/main/resources'

# -----------------------------------------------------------------------------
# Quantum Tools 3.0.4
# - restore visible energy bar + value + percentage
# - widen and brighten card sprites so graphite cards do not disappear on dark UI
# - realign/fix Quarry Card player inventory
# - keep the filter as a vertical scrolling list
# -----------------------------------------------------------------------------

# --- Builder screen -----------------------------------------------------------
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
    private static final int CARD_BORDER = 0xFF697985;
    private static final int CARD_SLOT = 0xFF26333D;
    private static final int CYAN = 0xFF19DDF2;
    private static final int CYAN_BRIGHT = 0xFF72F4FF;
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
                .bounds(leftPos + 155, topPos + 29, 83, 18).build());

        // Horizontal reading:
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

    private void drawEnergyBar(GuiGraphicsExtractor g, int x, int y, int energy, int maxEnergy) {
        int barX1 = x + 13;
        int barY1 = y + 36;
        int barX2 = x + 21;
        int barY2 = y + 64;
        g.fill(barX1, barY1, barX2, barY2, 0xFF05080A);
        g.fill(barX1 + 1, barY1 + 1, barX2 - 1, barY2 - 1, BORDER);
        g.fill(barX1 + 2, barY1 + 2, barX2 - 2, barY2 - 2, 0xFF0B151B);
        int innerHeight = barY2 - barY1 - 4;
        int fill = (int)(innerHeight * Math.min((long)energy, (long)maxEnergy) / Math.max(1L, (long)maxEnergy));
        if (fill > 0) {
            g.fill(barX1 + 2, barY2 - 2 - fill, barX2 - 2, barY2 - 2, CYAN);
            g.fill(barX1 + 2, barY2 - 2 - fill, barX2 - 2, Math.min(barY2 - 2, barY2 - 1 - fill), CYAN_BRIGHT);
        }
    }

    private void drawCardSlot(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, 0xFF05080A);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, CARD_BORDER);
        g.fill(x1 + 2, y1 + 2, x2 - 2, y2 - 2, CARD_SLOT);
        g.fill(x1 + 3, y1 + 2, x2 - 3, y1 + 3, CYAN_DARK);
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

        // Energy: visual bar + numeric value + percentage.
        panel(g, x + 8, y + 22, x + 54, y + 68);
        g.text(font, Component.literal("ENERGY"), x + 11, y + 27, MUTED);
        int energy = menu.data().get(0);
        int maxEnergy = Math.max(1, menu.data().get(1));
        drawEnergyBar(g, x, y, energy, maxEnergy);
        g.text(font, Component.literal(compact(energy)), x + 25, y + 40, CYAN);
        g.text(font, Component.literal(((long)energy * 100L / maxEnergy) + "%"), x + 25, y + 54, CYAN);

        // Cards. The slot itself is now lighter so a dark graphite card remains readable.
        panel(g, x + 58, y + 22, x + 148, y + 68);
        g.text(font, Component.literal("SHAPE"), x + 62, y + 25, CYAN_DARK);
        g.text(font, Component.literal("QUARRY"), x + 101, y + 25, CYAN_DARK);
        drawCardSlot(g, x + 63, y + 34, x + 87, y + 60);
        drawCardSlot(g, x + 101, y + 34, x + 125, y + 60);

        // Operation / progress
        panel(g, x + 152, y + 22, x + 246, y + 68);
        int status = menu.data().get(11);
        int cursor = menu.data().get(9);
        int volume = Math.max(1, menu.data().get(10));
        int permille = (int)(1000L * Math.min(cursor, volume) / volume);
        int pw = (int)(82L * Math.min(cursor, volume) / volume);
        g.text(font, statusText(status), x + 158, y + 50, CYAN);
        g.fill(x + 158, y + 61, x + 240, y + 65, 0xFF05080A);
        g.fill(x + 158, y + 61, x + 158 + pw, y + 65, CYAN);
        g.text(font, Component.literal((permille / 10) + "." + (permille % 10) + "%"), x + 211, y + 50, MUTED);

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
            int sx = x + 46 + col * 18, sy = y + 147 + row * 18;
            g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
            g.fill(sx + 1, sy + 1, sx + 17, sy + 17, PANEL);
        }
        for (int col = 0; col < 9; col++) {
            int sx = x + 46 + col * 18, sy = y + 205;
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

# --- Quarry filter player inventory ------------------------------------------
(java / 'QuarryFilterMenu.java').write_text(r'''package mcjty.rftoolsbuilder;

import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;

public class QuarryFilterMenu extends AbstractContainerMenu {
    public static final int REMOVE_BASE = 100;
    public static final int EXPAND_BASE = 200;
    private final Inventory inventory;
    private final int cardSlot;

    public QuarryFilterMenu(int containerId, Inventory inventory, FriendlyByteBuf extraData) {
        this(containerId, inventory, extraData.readVarInt());
    }

    public QuarryFilterMenu(int containerId, Inventory inventory, int cardSlot) {
        super(RFToolsBuilder.QUARRY_FILTER_MENU.get(), containerId);
        this.inventory = inventory;
        this.cardSlot = cardSlot;

        // Exact alignment with the backgrounds drawn by QuarryFilterScreen.
        int x = 47;
        int y = 217;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9, x + col * 18, y + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(inventory, col, x + col * 18, 275));
        }
    }

    public int cardSlot() { return cardSlot; }

    public ItemStack cardStack() {
        if (cardSlot < 0 || cardSlot >= inventory.getContainerSize()) return ItemStack.EMPTY;
        return inventory.getItem(cardSlot);
    }

    @Override
    public void clicked(int slotId, int button, ContainerInput input, Player player) {
        if (slotId >= 0 && slotId < slots.size()) {
            ItemStack source = slots.get(slotId).getItem();
            if (!source.isEmpty() && !(source.getItem() instanceof QuarryCardItem)) {
                if (!player.level().isClientSide()) {
                    if (input == ContainerInput.QUICK_MOVE) QuarryCardItem.addTagsFromItem(cardStack(), source);
                    else QuarryCardItem.addFilterItem(cardStack(), source, player.registryAccess());
                    broadcastChanges();
                }
                return;
            }
        }
        super.clicked(slotId, button, input, player);
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        ItemStack card = cardStack();
        if (!(card.getItem() instanceof QuarryCardItem)) return false;

        if (id >= 0 && id <= 3) {
            QuarryCardItem.toggle(card, id);
            broadcastChanges();
            return true;
        }
        if (id == 4) {
            QuarryCardItem.clearFilter(card);
            broadcastChanges();
            return true;
        }
        if (id >= REMOVE_BASE && id < REMOVE_BASE + QuarryCardItem.MAX_FILTER_ENTRIES) {
            QuarryCardItem.removeEntry(card, id - REMOVE_BASE, player.registryAccess());
            broadcastChanges();
            return true;
        }
        if (id >= EXPAND_BASE && id < EXPAND_BASE + QuarryCardItem.MAX_FILTER_ENTRIES) {
            QuarryCardItem.expandEntryToTags(card, id - EXPAND_BASE, player.registryAccess());
            broadcastChanges();
            return true;
        }
        return false;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        if (index < 0 || index >= slots.size()) return ItemStack.EMPTY;
        ItemStack source = slots.get(index).getItem();
        if (source.isEmpty() || source.getItem() instanceof QuarryCardItem) return ItemStack.EMPTY;
        if (!player.level().isClientSide()) {
            QuarryCardItem.addTagsFromItem(cardStack(), source);
            broadcastChanges();
        }
        return source.copy();
    }

    @Override
    public boolean stillValid(Player player) {
        return cardStack().getItem() instanceof QuarryCardItem;
    }
}
''', encoding='utf-8')

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
    private static final int VISIBLE_ROWS = 5;

    private int selected = -1;
    private int scroll = 0;
    private Button modeButton, damageButton, nbtButton, modButton;
    private Button removeButton, expandButton, upButton, downButton;
    private EditBox tagBox;

    public QuarryFilterScreen(QuarryFilterMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 256, 304);
        this.inventoryLabelY = 204;
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
                .bounds(leftPos + 228, topPos + 82, 20, 18).build());
        downButton = addRenderableWidget(Button.builder(Component.literal("▼"), b -> {
            int max = Math.max(0, QuarryCardItem.entryCount(card()) - VISIBLE_ROWS);
            if (scroll < max) scroll++;
        }).bounds(leftPos + 228, topPos + 144, 20, 18).build());

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
        int lx = (int) event.x() - leftPos;
        int ly = (int) event.y() - topPos;
        if (lx >= 9 && lx < 224 && ly >= 82 && ly < 162) {
            int row = (ly - 82) / 16;
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

    private void drawInventorySlot(GuiGraphicsExtractor g, int sx, int sy) {
        g.fill(sx, sy, sx + 18, sy + 18, 0xFF05080A);
        g.fill(sx + 1, sy + 1, sx + 17, sy + 17, 0xFF1A232C);
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
        panel(g, x + 42, y + 202, x + 214, y + 298);

        int count = QuarryCardItem.entryCount(card());
        g.text(font, Component.literal("FILTER LIST  " + count + "/18"), x + 10, y + 71, CYAN_DARK);
        for (int row = 0; row < VISIBLE_ROWS; row++) {
            int idx = scroll + row;
            int ry = y + 82 + row * 16;
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

        // Inventory grid: backgrounds and actual Slot coordinates now match exactly.
        g.text(font, Component.literal("INVENTORY"), x + 47, y + 204, CYAN_DARK);
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++) {
            drawInventorySlot(g, x + 46 + col * 18, y + 216 + row * 18);
        }
        for (int col = 0; col < 9; col++) drawInventorySlot(g, x + 46 + col * 18, y + 274);
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

# --- Card sprites: widen visible silhouette and raise graphite contrast -------
# The final 3.0.3 images are PNG RGBA. Decode them using only the stdlib so the
# build remains deterministic and has no Pillow dependency.
def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

def decode_rgba(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError(path)
    pos = 8; idat = bytearray(); width = height = None
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+ln]
        pos += 12 + ln
        if typ == b'IHDR':
            width, height, bit, color, comp, filt, inter = struct.unpack('>IIBBBBB', chunk)
            if bit != 8 or color != 6 or inter != 0: raise ValueError('Unsupported PNG format')
        elif typ == b'IDAT': idat.extend(chunk)
        elif typ == b'IEND': break
    raw = zlib.decompress(bytes(idat)); stride = width * 4; prev = bytearray(stride); rows = []
    p = 0
    for _ in range(height):
        ft = raw[p]; p += 1
        scan = bytearray(raw[p:p+stride]); p += stride
        out = bytearray(stride)
        for i, val in enumerate(scan):
            a = out[i-4] if i >= 4 else 0
            b = prev[i]
            c = prev[i-4] if i >= 4 else 0
            if ft == 0: v = val
            elif ft == 1: v = (val + a) & 255
            elif ft == 2: v = (val + b) & 255
            elif ft == 3: v = (val + ((a + b) >> 1)) & 255
            elif ft == 4: v = (val + paeth(a,b,c)) & 255
            else: raise ValueError('Bad PNG filter')
            out[i] = v
        prev = out
        rows.append([tuple(out[i:i+4]) for i in range(0, stride, 4)])
    return rows

def write_rgba(path, px):
    h = len(px); w = len(px[0])
    raw = b''.join(b'\x00' + bytes(sum(row, ())) for row in px)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w,h,8,6,0,0,0)) + chunk(b'IDAT', zlib.compress(raw,9)) + chunk(b'IEND', b'')
    path.write_bytes(data)

def brighten(pixel):
    r,g,b,a = pixel
    if a == 0: return pixel
    mx = max(r,g,b)
    if mx < 48: r,g,b = max(r,34), max(g,41), max(b,48)
    elif mx < 82: r,g,b = min(255,r+18), min(255,g+18), min(255,b+18)
    return (r,g,b,a)

def widen_card(path, accent):
    src = decode_rgba(path)
    coords = [(x,y) for y in range(16) for x in range(16) if src[y][x][3] > 24]
    if not coords: return
    x0=min(x for x,y in coords); x1=max(x for x,y in coords)
    y0=min(y for x,y in coords); y1=max(y for x,y in coords)
    T=(0,0,0,0); plate=(34,42,50,255); plate2=(43,52,61,255); edge=(113,127,138,255)
    out=[[T for _ in range(16)] for _ in range(16)]
    for y in range(1,15):
        for x in range(1,15):
            if (x,y) in ((1,1),(14,1),(1,14),(14,14)): continue
            out[y][x] = plate2 if y in (2,13) else plate
    for x in range(2,14): out[1][x]=edge; out[14][x]=edge
    for y in range(2,14): out[y][1]=edge; out[y][14]=edge
    for x in range(3,13): out[2][x]=accent

    # Stretch the approved source artwork horizontally into a 12px inner face.
    sw=max(1,x1-x0+1)
    for y in range(max(1,y0), min(14,y1)+1):
        for tx in range(2,14):
            sx = x0 + round((tx-2) * (sw-1) / 11)
            pix = brighten(src[y][max(0,min(15,sx))])
            if pix[3] > 20: out[y][tx] = pix

    # Reassert a readable graphite-metal perimeter over dark source shadows.
    for x in range(2,14):
        if out[1][x][3] == 0 or max(out[1][x][:3]) < 85: out[1][x]=edge
        if out[14][x][3] == 0 or max(out[14][x][:3]) < 85: out[14][x]=edge
    for y in range(2,14):
        if out[y][1][3] == 0 or max(out[y][1][:3]) < 85: out[y][1]=edge
        if out[y][14][3] == 0 or max(out[y][14][:3]) < 85: out[y][14]=edge
    write_rgba(path,out)

textures = res / 'assets/rftoolsbuilder/textures/item'
card_accents = {
    'shapecarditem.png': (255,137,15,255),
    'shapecardquarryitem.png': (255,137,15,255),
    'shapecardcquarryitem.png': (225,231,235,255),
    'shapecardfortuneitem.png': (255,174,20,255),
    'shapecardcfortuneitem.png': (255,174,20,255),
    'shapecardsilkitem.png': (23,211,239,255),
    'shapecardcsilkitem.png': (23,211,239,255),
}
for name, accent in card_accents.items(): widen_card(textures / name, accent)

# Version bump.
build = root / 'build.gradle'
bs = build.read_text(encoding='utf-8')
bs, n = re.subn(r"(?m)^version\s*=\s*['\"]3\.0\.3['\"]", "version = '3.0.4'", bs, count=1)
if n != 1: raise SystemExit('3.0.3 version not found')
build.write_text(bs, encoding='utf-8')

print('Quantum Tools 3.0.4: energy bar, wider cards, card contrast, quarry inventory alignment')

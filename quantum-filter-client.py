from pathlib import Path

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'

(java / 'FilterTagPayload.java').write_text(r"""package mcjty.rftoolsbuilder;

import io.netty.buffer.ByteBuf;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.network.handling.IPayloadContext;

public record FilterTagPayload(int cardSlot, String tag) implements CustomPacketPayload {
    public static final Type<FilterTagPayload> TYPE = new Type<>(Identifier.fromNamespaceAndPath(RFToolsBuilder.MOD_ID, "filter_tag"));
    public static final StreamCodec<ByteBuf, FilterTagPayload> STREAM_CODEC = StreamCodec.composite(
            ByteBufCodecs.VAR_INT, FilterTagPayload::cardSlot,
            ByteBufCodecs.STRING_UTF8, FilterTagPayload::tag,
            FilterTagPayload::new);

    @Override
    public Type<? extends CustomPacketPayload> type() { return TYPE; }

    public static void handle(FilterTagPayload payload, IPayloadContext context) {
        if (!(context.player() instanceof ServerPlayer player)) return;
        if (payload.cardSlot < 0 || payload.cardSlot >= player.getInventory().getContainerSize()) return;
        ItemStack card = player.getInventory().getItem(payload.cardSlot);
        if (!(card.getItem() instanceof QuarryCardItem)) return;
        QuarryCardItem.addFilterTag(card, payload.tag);
        player.containerMenu.broadcastChanges();
    }
}
""", encoding='utf-8')

(client / 'QuarryFilterScreen.java').write_text(r"""package mcjty.rftoolsbuilder.client;

import mcjty.rftoolsbuilder.FilterTagPayload;
import mcjty.rftoolsbuilder.QuarryCardItem;
import mcjty.rftoolsbuilder.QuarryFilterMenu;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.client.network.ClientPacketDistributor;

public class QuarryFilterScreen extends AbstractContainerScreen<QuarryFilterMenu> {
    private static final int BG = 0xFF090D11;
    private static final int PANEL = 0xFF121A21;
    private static final int BORDER = 0xFF33414B;
    private static final int CYAN = 0xFF18DDF3;
    private static final int CYAN_DARK = 0xFF087A88;
    private static final int TEXT = 0xFFE8F1F4;
    private static final int MUTED = 0xFF75858F;
    private static final int SELECTED = 0xFF274653;

    private int selected = -1;
    private int page = 0;
    private Button modeButton, damageButton, nbtButton, modButton, removeButton, expandButton, prevButton, nextButton;
    private EditBox tagBox;

    public QuarryFilterScreen(QuarryFilterMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 188, 218);
        this.inventoryLabelY = 120;
    }

    @Override
    protected void init() {
        super.init();
        modeButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(0)).bounds(leftPos + 8, topPos + 87, 52, 16).build());
        damageButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(1)).bounds(leftPos + 62, topPos + 87, 34, 16).build());
        nbtButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(2)).bounds(leftPos + 98, topPos + 87, 34, 16).build());
        modButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(3)).bounds(leftPos + 134, topPos + 87, 36, 16).build());

        removeButton = addRenderableWidget(Button.builder(Component.literal("Remove"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.REMOVE_BASE + selected);
        }).bounds(leftPos + 8, topPos + 105, 48, 16).build());
        expandButton = addRenderableWidget(Button.builder(Component.literal("Expand"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.EXPAND_BASE + selected);
        }).bounds(leftPos + 58, topPos + 105, 48, 16).build());
        addRenderableWidget(Button.builder(Component.literal("Clear"), b -> { selected = -1; send(4); }).bounds(leftPos + 108, topPos + 105, 38, 16).build());

        prevButton = addRenderableWidget(Button.builder(Component.literal("<"), b -> { if (page > 0) page--; }).bounds(leftPos + 148, topPos + 105, 10, 16).build());
        nextButton = addRenderableWidget(Button.builder(Component.literal(">"), b -> { if ((page + 1) * 8 < QuarryCardItem.entryCount(card())) page++; }).bounds(leftPos + 160, topPos + 105, 10, 16).build());

        tagBox = new EditBox(font, leftPos + 8, topPos + 68, 120, 16, Component.literal("Tag"));
        tagBox.setMaxLength(80);
        tagBox.setHint(Component.literal("c:ores"));
        addRenderableWidget(tagBox);
        addRenderableWidget(Button.builder(Component.literal("+ Tag"), b -> {
            String value = tagBox.getValue().trim();
            if (!value.isEmpty()) {
                ClientPacketDistributor.sendToServer(new FilterTagPayload(menu.cardSlot(), value));
                tagBox.setValue("");
                selected = -1;
            }
        }).bounds(leftPos + 132, topPos + 68, 38, 16).build());
        syncButtons();
    }

    private void send(int id) {
        if (minecraft != null && minecraft.gameMode != null) minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
    }

    private ItemStack card() { return menu.cardStack(); }

    private void syncButtons() {
        ItemStack card = card();
        if (modeButton != null) modeButton.setMessage(Component.literal(QuarryCardItem.blacklist(card) ? "BLACK" : "WHITE"));
        if (damageButton != null) damageButton.setMessage(Component.literal(QuarryCardItem.damageMode(card) ? "DMG✓" : "DMG"));
        if (nbtButton != null) nbtButton.setMessage(Component.literal(QuarryCardItem.nbtMode(card) ? "DATA✓" : "DATA"));
        if (modButton != null) modButton.setMessage(Component.literal(QuarryCardItem.modMode(card) ? "MOD✓" : "MOD"));
        int count = QuarryCardItem.entryCount(card);
        if (selected >= count) selected = -1;
        int maxPage = Math.max(0, (count - 1) / 8);
        if (page > maxPage) page = maxPage;
        if (removeButton != null) removeButton.active = selected >= 0;
        if (expandButton != null) expandButton.active = selected >= QuarryCardItem.tagCount(card);
        if (prevButton != null) prevButton.active = page > 0;
        if (nextButton != null) nextButton.active = page < maxPage;
    }

    @Override
    protected void containerTick() { super.containerTick(); syncButtons(); }

    @Override
    public boolean mouseClicked(double mouseX, double mouseY, int button) {
        int relX = (int) mouseX - leftPos;
        int relY = (int) mouseY - topPos;
        if (relY >= 27 && relY < 63 && relX >= 8 && relX < 178) {
            int col = (relX - 8) / 85;
            int row = (relY - 27) / 18;
            if (col >= 0 && col < 2 && row >= 0 && row < 2) {
                int idx = page * 8 + col * 2 + row;
                if (idx < QuarryCardItem.entryCount(card())) { selected = idx; return true; }
            }
        }
        return super.mouseClicked(mouseX, mouseY, button);
    }

    private String entryLabel(int combined) {
        ItemStack card = card();
        int tags = QuarryCardItem.tagCount(card);
        if (combined < tags) return "#" + QuarryCardItem.getTag(card, combined);
        if (minecraft == null || minecraft.level == null) return "";
        ItemStack item = QuarryCardItem.getFilterItem(card, combined - tags, minecraft.level.registryAccess());
        return item.isEmpty() ? "" : item.getHoverName().getString();
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        int x = leftPos, y = topPos;
        g.fill(x, y, x + imageWidth, y + imageHeight, BG);
        g.fill(x + 2, y + 2, x + imageWidth - 2, y + imageHeight - 2, PANEL);
        g.fill(x + 8, y + 3, x + 56, y + 5, CYAN_DARK);
        g.fill(x + imageWidth - 56, y + 3, x + imageWidth - 8, y + 5, CYAN_DARK);
        g.centeredText(font, Component.literal("QUARRY FILTER"), x + imageWidth / 2, y + 8, TEXT);
        g.text(font, Component.literal("Whitelist / Blacklist • Item • Tag • Mod • Data"), x + 8, y + 17, MUTED);

        int count = QuarryCardItem.entryCount(card());
        int start = page * 8;
        for (int local = 0; local < 4; local++) {
            int combined = start + local;
            int col = local / 2, row = local % 2;
            int rx = x + 8 + col * 85, ry = y + 27 + row * 18;
            g.fill(rx, ry, rx + 81, ry + 16, combined == selected ? SELECTED : 0xFF0B1116);
            g.fill(rx, ry, rx + 1, ry + 16, combined == selected ? CYAN : BORDER);
            if (combined < count) {
                String label = entryLabel(combined);
                if (label.length() > 13) label = label.substring(0, 12) + "…";
                g.text(font, Component.literal(label), rx + 4, ry + 4, TEXT);
            } else g.text(font, Component.literal("empty"), rx + 4, ry + 4, MUTED);
        }
        if (count > start + 4) g.text(font, Component.literal("Page " + (page + 1) + " • " + count + "/18 entries"), x + 8, y + 61, MUTED);
        else g.text(font, Component.literal(count + "/18 entries"), x + 8, y + 61, MUTED);

        g.text(font, Component.literal("Click item = add exact  •  Shift-click = add tags"), x + 8, y + 124, MUTED);
        g.text(font, Component.literal("INVENTORY"), x + 13, y + 120, CYAN_DARK);
    }

    @Override
    protected void extractLabels(GuiGraphicsExtractor g, int mouseX, int mouseY) { }
}
""", encoding='utf-8')

p = client / 'RFToolsBuilderClient.java'
s = p.read_text(encoding='utf-8')
s = s.replace('event.register(RFToolsBuilder.BUILDER_MENU.get(), BuilderScreen::new);', 'event.register(RFToolsBuilder.BUILDER_MENU.get(), BuilderScreen::new);\n            event.register(RFToolsBuilder.QUARRY_FILTER_MENU.get(), QuarryFilterScreen::new);')
p.write_text(s, encoding='utf-8')

p = java / 'RFToolsBuilder.java'
s = p.read_text(encoding='utf-8')
s = s.replace('import net.neoforged.neoforge.registries.DeferredRegister;', 'import net.neoforged.neoforge.registries.DeferredRegister;\nimport net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;')
s = s.replace('public static final DeferredHolder<MenuType<?>, MenuType<BuilderMenu>> BUILDER_MENU =\n            MENUS.register("builder", () -> IMenuTypeExtension.create(BuilderMenu::new));', 'public static final DeferredHolder<MenuType<?>, MenuType<BuilderMenu>> BUILDER_MENU =\n            MENUS.register("builder", () -> IMenuTypeExtension.create(BuilderMenu::new));\n\n    public static final DeferredHolder<MenuType<?>, MenuType<QuarryFilterMenu>> QUARRY_FILTER_MENU =\n            MENUS.register("quarry_filter", () -> IMenuTypeExtension.create(QuarryFilterMenu::new));')
s = s.replace('modBus.addListener(this::registerCapabilities);', 'modBus.addListener(this::registerCapabilities);\n        modBus.addListener(this::registerPayloads);')
s = s.replace('\n    private void registerCapabilities(RegisterCapabilitiesEvent event) {', '\n    private void registerPayloads(RegisterPayloadHandlersEvent event) {\n        event.registrar("1").playToServer(FilterTagPayload.TYPE, FilterTagPayload.STREAM_CODEC, FilterTagPayload::handle);\n    }\n\n    private void registerCapabilities(RegisterCapabilitiesEvent event) {')
p.write_text(s, encoding='utf-8')
print('Quantum filter client/network applied')

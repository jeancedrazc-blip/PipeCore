from pathlib import Path
import re, base64

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'
res = root / 'src/main/resources'

# -----------------------------------------------------------------------------
# 1) Large-area scanning: 256 positions/tick made 512xYx512 appear frozen.
#    4096 keeps CPU cost bounded while making filtered quarries usable.
# -----------------------------------------------------------------------------
p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r'private static final int SCAN_BUDGET\s*=\s*256\s*;', 'private static final int SCAN_BUDGET = 4096;', s, count=1)
if n != 1:
    raise SystemExit('SCAN_BUDGET constant not found')
p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 2) Quarry filter menu: roomy inventory placement and stable ContainerInput API.
# -----------------------------------------------------------------------------
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

        int x = 47;
        int y = 211;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9, x + col * 18, y + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) {
            addSlot(new Slot(inventory, col, x + col * 18, y + 58));
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
                    if (input == ContainerInput.QUICK_MOVE) {
                        QuarryCardItem.addTagsFromItem(cardStack(), source);
                    } else {
                        QuarryCardItem.addFilterItem(cardStack(), source, player.registryAccess());
                    }
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

# -----------------------------------------------------------------------------
# 3) Quarry filter screen: no paging/overlap. All 18 entries visible at once.
# -----------------------------------------------------------------------------
(client / 'QuarryFilterScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;

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
    private static final int BG = 0xFF080C10;
    private static final int PANEL = 0xFF111820;
    private static final int PANEL_2 = 0xFF18222B;
    private static final int BORDER = 0xFF33434E;
    private static final int CYAN = 0xFF18DDF3;
    private static final int CYAN_DARK = 0xFF087A88;
    private static final int TEXT = 0xFFE8F1F4;
    private static final int MUTED = 0xFF74838D;

    private int selected = -1;
    private final Button[] entryButtons = new Button[18];
    private Button modeButton;
    private Button damageButton;
    private Button nbtButton;
    private Button modButton;
    private Button removeButton;
    private Button expandButton;
    private EditBox tagBox;

    public QuarryFilterScreen(QuarryFilterMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, 256, 292);
        this.inventoryLabelY = 198;
        this.titleLabelY = 7;
    }

    @Override
    protected void init() {
        super.init();

        modeButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(0))
                .bounds(leftPos + 8, topPos + 24, 68, 18).build());
        modButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(3))
                .bounds(leftPos + 78, topPos + 24, 54, 18).build());
        nbtButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(2))
                .bounds(leftPos + 134, topPos + 24, 54, 18).build());
        damageButton = addRenderableWidget(Button.builder(Component.empty(), b -> send(1))
                .bounds(leftPos + 190, topPos + 24, 58, 18).build());

        tagBox = new EditBox(font, leftPos + 8, topPos + 47, 180, 16, Component.literal("Tag"));
        tagBox.setMaxLength(80);
        tagBox.setHint(Component.literal("c:ores"));
        addRenderableWidget(tagBox);
        addRenderableWidget(Button.builder(Component.literal("+ TAG"), b -> addTag())
                .bounds(leftPos + 190, topPos + 47, 58, 16).build());

        for (int i = 0; i < entryButtons.length; i++) {
            final int idx = i;
            int col = i % 3;
            int row = i / 3;
            entryButtons[i] = addRenderableWidget(Button.builder(Component.empty(), b -> selected = idx)
                    .bounds(leftPos + 8 + col * 81, topPos + 69 + row * 17, 78, 16).build());
        }

        removeButton = addRenderableWidget(Button.builder(Component.literal("REMOVE"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.REMOVE_BASE + selected);
        }).bounds(leftPos + 8, topPos + 174, 64, 18).build());

        expandButton = addRenderableWidget(Button.builder(Component.literal("EXPAND"), b -> {
            if (selected >= 0) send(QuarryFilterMenu.EXPAND_BASE + selected);
        }).bounds(leftPos + 74, topPos + 174, 64, 18).build());

        addRenderableWidget(Button.builder(Component.literal("CLEAR"), b -> {
            selected = -1;
            send(4);
        }).bounds(leftPos + 184, topPos + 174, 64, 18).build());

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
        if (minecraft != null && minecraft.gameMode != null) {
            minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
        }
    }

    private ItemStack card() { return menu.cardStack(); }

    private String entryLabel(int combined) {
        ItemStack card = card();
        int tags = QuarryCardItem.tagCount(card);
        if (combined < tags) return "#" + QuarryCardItem.getTag(card, combined);
        if (minecraft == null || minecraft.level == null) return "";
        ItemStack item = QuarryCardItem.getFilterItem(card, combined - tags, minecraft.level.registryAccess());
        return item.isEmpty() ? "" : item.getHoverName().getString();
    }

    private void syncButtons() {
        ItemStack card = card();
        int count = QuarryCardItem.entryCount(card);
        int tags = QuarryCardItem.tagCount(card);
        if (selected >= count) selected = -1;

        if (modeButton != null) modeButton.setMessage(Component.literal(QuarryCardItem.blacklist(card) ? "BLACKLIST" : "WHITELIST"));
        if (modButton != null) modButton.setMessage(Component.literal(QuarryCardItem.modMode(card) ? "MOD: ON" : "MOD: OFF"));
        if (nbtButton != null) nbtButton.setMessage(Component.literal(QuarryCardItem.nbtMode(card) ? "DATA: ON" : "DATA: OFF"));
        if (damageButton != null) damageButton.setMessage(Component.literal(QuarryCardItem.damageMode(card) ? "DMG: ON" : "DMG: OFF"));

        for (int i = 0; i < entryButtons.length; i++) {
            Button b = entryButtons[i];
            if (b == null) continue;
            boolean present = i < count;
            b.active = present;
            String label = present ? entryLabel(i) : "—";
            if (label.length() > 12) label = label.substring(0, 11) + "…";
            b.setMessage(Component.literal((i == selected ? "> " : "") + label));
        }

        if (removeButton != null) removeButton.active = selected >= 0;
        if (expandButton != null) expandButton.active = selected >= tags && selected < count;
    }

    @Override
    protected void containerTick() {
        super.containerTick();
        syncButtons();
    }

    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, 0xFF05080B);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, BORDER);
        g.fill(x1 + 2, y1 + 2, x2 - 2, y2 - 2, PANEL);
        g.fill(x1 + 4, y1 + 2, Math.min(x2 - 4, x1 + 28), y1 + 3, CYAN_DARK);
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        int x = leftPos;
        int y = topPos;

        g.fill(x, y, x + imageWidth, y + imageHeight, BG);
        g.fill(x + 2, y + 2, x + imageWidth - 2, y + imageHeight - 2, PANEL_2);
        g.fill(x + 4, y + 4, x + imageWidth - 4, y + imageHeight - 4, BG);

        g.fill(x + 8, y + 3, x + 64, y + 5, CYAN_DARK);
        g.fill(x + imageWidth - 64, y + 3, x + imageWidth - 8, y + 5, CYAN_DARK);
        g.centeredText(font, Component.literal("QUARRY CARD FILTER"), x + imageWidth / 2, y + 8, TEXT);

        panel(g, x + 6, y + 20, x + 250, y + 66);
        panel(g, x + 6, y + 65, x + 250, y + 166);
        panel(g, x + 6, y + 170, x + 250, y + 196);
        panel(g, x + 42, y + 202, x + 214, y + 286);

        int count = QuarryCardItem.entryCount(card());
        g.text(font, Component.literal("FILTER ENTRIES  " + count + "/18"), x + 10, y + 66, CYAN_DARK);
        g.text(font, Component.literal("Clique no item = bloco exato  •  Shift-clique = tags"), x + 9, y + 198, MUTED);
        g.text(font, Component.literal("INVENTORY"), x + 47, y + 199, CYAN_DARK);
    }

    @Override
    protected void extractLabels(GuiGraphicsExtractor g, int mouseX, int mouseY) { }
}
''', encoding='utf-8')

# -----------------------------------------------------------------------------
# 4) Builder UI: make progress perceptible for huge 512 areas.
# -----------------------------------------------------------------------------
p = client / 'BuilderScreen.java'
s = p.read_text(encoding='utf-8')
needle = 'g.text(font, Component.literal(compact(Math.min(cursor, volume)) + " / " + compact(volume)), x + 150, y + 70, MUTED);'
if needle in s:
    repl = '''int permille = (int)(1000L * Math.min(cursor, volume) / volume);
        String percent = (permille / 10) + "." + (permille % 10) + "%";
        g.text(font, Component.literal(percent + "  •  " + compact(Math.min(cursor, volume)) + "/" + compact(volume)), x + 150, y + 70, MUTED);'''
    s = s.replace(needle, repl, 1)
# Stronger, visibly different header/panel identity.
s = s.replace('g.fill(x + imageWidth / 2 - 34, y + 18, x + imageWidth / 2 + 34, y + 19, CYAN_DARK);',
              'g.fill(x + 48, y + 18, x + imageWidth - 48, y + 20, CYAN_DARK);')
p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 5) Approved cards: direct 16x16 reductions of the seven approved concept cards.
# -----------------------------------------------------------------------------
CARD_B64 = {
'shapecarditem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACF0lEQVR42n2STUtUURjHf+fcF+fe27VxULQZGR0hAyEpiqKoNha0qlWbNq37BC78BG1aiB+iTfs+QFSUREamgZnlNDjgS6bOy305T4sJmwuNz+6cw//H//lxFF1jF8oyGBgaLUOaGpSl0ECSCsYYvFwfge9QXV9Xx5luwPz9Jjnb8PTjRfrDHCYFTEIct2m2YwLXMH9riWtP/mV0N6Be28Hd3aF0+JY3i8uUWy95XHmBu73E6pdNbrrvWFw6ouf4o9My3G9LTiNgS8FHrlcQ19ECluQdZCDfL5m1uw/lgsNqzQaTcLmcMB5CM4V7U4bVOnzaAifO5LOAyNj4VszsbXj/A16vgQCBA3emYWYCFhZPALTTlAFPWPkGLQMz01DbgYIPK3UYsuC0D7tRD4nKgBhoNeHVOnyuwrkSfPgJyxsQRyCSbaCzGjuPkYBvw+EBbG5B3IY+t9NKZfNZQGwMlgZXgWhIgdR0gFECngXKUr0BtiT8jhSDAYyGIAKuhjSBiQJYGhrxSQAN+7HFszU4E8L5IuQDuDLe0f38KyRG9/5IlckpUbYjf2XIiIfcHUM8i+M7PwwzFjJ9/OFJMQc1/CAAyyGKE4wotALPgbh1RDO1aR/sqv+uMHdjg7NDDqeGimhtE/ouxQEXz7Ww+3wGS2NcGjnq7SBvRcxd3aOxVydp/OJhscqDwncelapsbe9TUTVmL7QzgD+sYNWy2TdeBwAAAABJRU5ErkJggg==',
'shapecardquarryitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACKklEQVR42n2Tv2tTURiGn/Pj5iapsWmaitS2VKtIoVZRsBTUsaiLOAiddNVBXRykLroJ+ifo4qS7iCAOQkERbFELlYptWonUVNIaNObc3Hs+J7FR47e/D9/7nO8oNo3J90v3VkvTRbhmgtIKozTgSQQCY+hIG8rLy+pXxm4GnBpJuDBeZ+r5AURZPOCanpQWfFwnii3nD65w+c7vjN4M6EiqfFioMibTzL6Zx3+a4frIE8bMM17PlSjU35LfKNF2Mtv3ytaugmQNAmmBUApZJdYoQVkJjZJC1srmTMsGO7ozxAT4lOHSsQa3z3hc2EmxsIUwBCeGahTQFhBFHoUnjoXH8wr3vUn52gZXj8bETQVKYa1qDxBJAEi8YmEtzd2XKWZmYWLwB8UuDYn8VbsF4MVjFEgC/UXPzSMRpx9kWfwCk/scoDBK2kvs2zUsYWePbMsZuX8CGekJBNIy3Kvl8JCS0TxSzGXaSxSESDRThxLuvTPMrRlsGDO/GjCA0LAhtUT/zwFkdMKNF5ZHH1NgBas0xwccS980J3sdHX9UaHWAB2DdgTECKPrCmHwGJvd4pj9rvPgWQMspWyUoPEhCEnkQEO95ugQP30NOe2LTukHLo4Y9u8VKgxQN0CFWg6BwcQIIPklwzhHXa//+TOf2lylVAl7VhzCNKkppAg3GapQOCHJ5XGWRSr2dA++4MlpjUK1SqUVMFFc4u7PExeEVpF5BfS1za3y9pcJP69XsvO1U5TIAAAAASUVORK5CYII=',
'shapecardcquarryitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACTklEQVR42n2TzUtUYRTGf/eOdz6vzjW9w0xOY+pYmGCaThrpokVGFhGUiyDaBEX/QRDRtj8g2xkEQyHtW7SZQggCJREKCVc2Y5IzUzijzsz9OC0qv2h64D1wFs9zfpzDq7BHXqNNbEXlUAAsWxBAwcV1HVSPhusIXp+HQm5F+etp2BsQbfHweHyD6c9dfKsYaKpCqeKCW0O1NxGPn8OhErO5Xc++gHioSCFXZlJf4MFyAlVc7o9l0VyHR5korqryMLXKLHWkRzpFN9slGkDg94sbiphBBMUjgLTpyF7PPoJwow/bqrH2M8jNW5M0NoWZfp7G5/cS9juYEZPlpS+AveNR9waIgOO4qGIxN/8Rs9Xk3ZvXTJw/h4hghMOguNQlQAFVVXBRWfq0yLNymfiRBMd7TjAz85K5D/mDMw90IngUFewqx3p6uX5tkrt3bhOLRYnFExitEVLDw/UJHAcq29vE2uKMX7hI+kUacWyeTE2haRoBv498vlifwHUtQJi4dIXM2wz5tRygcGqgHz2kIyKMjo5QV5FEUsx4h3h8AQEk2GTIxOWr0tt3cueMXd3dUpdA/hSnWsXf2MTgwCDr+TylchnEAWCjtPW/JbogNg1+Px3tnWSzWYqFPGdSKZpNE38wxOjZkfpLLG3aKKqHgM/LerGIbTs0KLBWKJI4msSqbpP/vn7w8rsa6zckqW/x6msvpqGxVSyg+byUSiWsWg29uQWrssGP1dy/f6PUqtxI1rDcFdLzwthIH0NDpxGBxcUFMu/nuddf4enqrucXOv/s3BD+14EAAAAASUVORK5CYII=',
'shapecardfortuneitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACLklEQVR42n2TPWhTURiGn/Nz83NbTdLUNj81tgUtVLqIg9W1kyIFaxW0m4vg5iCugp2KuAji5iKC7qJTNwcpokODIJSkhLZpaWt/0uQmN/dz0JZETD84wzmc9zkPLxxFy4QTGfGaEDYNxA9AKYwBBfhNAaUxWlPdLqvDjG0FWKuYm9xmfjnFwmqaE9GASkPTqDew1DH4CFDYLh9ldCtgILZPZctjJlXErRUorqwzOfCNuStfiPlrlDZ2mEn9oONEe7Lips7JcBwBK+BIIoqcPolYqwS09IaR1kybQTTi0B8Ps/RLMzHm8/SWEIS6KHlhjDE8vBGn5jh0BAB49QYg/Fw31Cs+32d9Xt1VqGaTjwsVKjX/eMDhabFseDYfZvGrx0SuRjIZJb/skXD1MQClUAABOBHNm5seD95ZPuXh6sgBqVMuT+70dC4xmR2S9OCI2FBIXt9GpkcRcCSTNHI2g4CWHveYEhXCZlVz/1KdYhne5y3gsychHl2zTF0I2DqwnQ0SmUFJZgYlYpWAkunxLhnNuTI7hUhhWDYeI/3d7Qa23UChFPwp2rBY8lndFhaXYPflEm8/QzVQ0M5oMUjnJJ0bkr832tbFXiTmHO1bHv3nMykTxVTXiHTHaAZCWAc4uslmTWGURhpVKnu76r8lZmMN7o2VcGIpunv70NYh7LqEIlHiEcvJeJxY9gwdOwjE5/qQh9or8CLfx/nsDtOXD9jdB2vg+QeP8ZxmpSXzG++/1c06s3iMAAAAAElFTkSuQmCC',
'shapecardcfortuneitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACRElEQVR42nWTvU9TURjGf+fc2957C4UChSpt1SISQUlkIH5EJWp0cDA1kU3i4KD/giOTRhM1ITHGwT/A6Kabg0wOOiCYqDH4EYWEjwKB0vb2frwOxNgm3mc5OcPzy3Oe9z2KBjkdWakGkLTBAAIBrSDw6uhYHBGIx2KUFn+ovx6zERAK3L20wmxpF6/ne0ladTZdRegFWEaIwqcWqkYLuvHSm6ogZZ/LmRUyeonSRo3rg595eG6GhLvCwmqZmwe+NQGacC3pnHhYZGrz/CprIE6XU8MxoYZmOzDp1HUWyv98TQlsy6S7zaYaM7l9NeTBRICyW1jzDC6MdnBqIMZCmWh15fok339IlFLSk1Ty7AYSPDLkWEELIIcLlpwfbZXIDhRgGBoRWN4yeDsLXz4FXBvTgGKzLMSR6BJFBCQEDKaKPsqDo080LcpnKO+Q7zR59W67CdA0Rq2gVNGMj/gEVbj/XgHCrRcQTwAVhTIsJHD/nyAIBUdXefkBHs+ZTBYdNMKJixN07R1hyU1xZuxkdImp3XskWxgQQGbu9YrM5WTyLFI4OCK2bQsghuVI5BNA2OlIMz29SOYrzC7C+nqJmlsHFIFbjU7QnslLttAvOySkr3XnLBaLsq9vv8QdR4aGh6MTuPUQH4NEIoHhtLKsDLJJn6XVNXrSaeJWglSyLXqVc/m0XBnc4OncHlrbk6jKJqZpUKlWCAIwbAcvDNn4/T3iN4Yhp3t8gtxPpj52c6S/xvjxLTw/geuF3Hm+zVjB4k2D5w/LLOJp2ftGpQAAAABJRU5ErkJggg==',
'shapecardsilkitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACKElEQVR42n2TwUtUcRDHP/N7L9fd1VIzUzdW1LDMgjKhkAK7FZ08FVHdjI516BZElLfo0Cn6Bzp06F4EFdIhEcLYJLFDbiW5sru93X3v7b59Ox22Yg3Xuc0Xvh++M8wIDdXRm9SCW0WNEiEgDBUjIICi1FRAhIqzIX89diOgFAjjAyEzExnuvTtCaySKWIZCKYBaBQnLxGJRVlIb/zymERDWhEQ0T3tZuDKcZnXdQYs/mJ2c59rBFG7BxclnGy1IY9Pe3a9+rYV228PK/SQT1PW+NvDLkCMC1RC0KlsmUITunS14XkAmspv+m7fpvHSdtWKMXEsX1v7DEG/blMD83ymCsQyUC2Tm32NNX2TkzQfM+EnCpQUkkWwOEDEIBjEWBBWCuRdszN5luSR0njhVT+m62yQAVEMwf+TJszA4CpencKfO1VeWXmkOMCIoBin7MHgIjp6Gl08h+x3v4R04cx7sCE2ro29A9yQGNb43qdx4oPSPKKCMHlMeP1deryqPnmmjx94KFJZdeHIfvGJdGBoDuwOWU5BO0xSgKhjLxhIDbh569hEdOoDnFyGbgVwWPi02B9RUEVEgrAvr3/DyWah4YEchOQxfPm5ziT0JrUoMCTyo5InEd1GrhiCCXa1QibQinofjZJs8k28xPbZGrmRY1AliYQ7/l4MVjSOi7PB9pLsXJ5VtMkJNiNseM8dDbr39zNJXB71wldrQCOr6kFqga+7VphF+A4wL3/XI65y6AAAAAElFTkSuQmCC',
'shapecardcsilkitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACOElEQVR42nWST0gUURzHP29mdmdnNXMz0y0ttRCEDpGUlIeiPJj9OUkeguhS0K0O3Tt3DboEQYeCDlEQHoM6Bl5q02WRItGS1vaP4844szPzXocx2aXd3+HB9wff7/t+v+8JGmZv36Dy/BA/VHSlBVGkQEF8KHTDIAxC3EpR/OMYjQKRFFgpwZPL67zI9bNUOoBlGqAkXl2iqQAhJG6luMvRGgXqUudQ1xZOGe4MFxH1KqVymZujSzwc/4IZ2NhVu5GCaATd2WHleT5oCXq9FVadeN/TCaaCX462Q4laR1BKkbaSWEmD1RJkpy5hmml+zL8GdBInz6J1deN/eNc6ghACpRSBjHHNCzFv32Py7Uf00TGC3AJ+boG2kzk4pDLZI6pv8KgCLa7+zLRKfCqqgbsPYmykVCOn2YFmIAApBCBh5gZMnCeYu0jHiQkwkmClmy5t6kATgkgIqNVgchqOn4ZH9wHJ92eP0TMZ6Ogm2iq3dsBOB1IpcLdIreVJX5iBPRlmB3oY6+sl6zvtHUgVx4uiAK23n8HZW7iOjV8PyC3l+ZovxNHaCew+p65DyqK6XMAuLKJ8H9uu/Udu+Q+EkiRTKTbnX7HxcwXqASx/ZuLqFez3Do67TeBtt3EgQ1wvQk9YpDQdo5CLi7LSrG/8YWhohMrmJivfllsLbPswst/l3OHfPM8fY1/GxK1UMRIJFvMFZKgwOzrbRwilQhBxfTiiXFrjTSGBGj9FOHUNogDWV+l8+bRJ4C/HkPEDAmtumgAAAABJRU5ErkJggg=='
}
tex = res / 'assets/rftoolsbuilder/textures/item'
for name, encoded in CARD_B64.items():
    (tex / name).write_bytes(base64.b64decode(encoded))

# Version bump after quantumtools-assets.py sets 3.0.0.
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s = re.sub(r"(?m)^version\s*=\s*['\"]3\.0\.0['\"]", "version = '3.0.1'", s, count=1)
p.write_text(s, encoding='utf-8')

print('Quantum Tools 3.0.1 fixes applied')

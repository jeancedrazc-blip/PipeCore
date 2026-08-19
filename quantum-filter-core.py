from pathlib import Path

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'

(java / 'QuarryCardItem.java').write_text(r"""package mcjty.rftoolsbuilder;

import net.minecraft.ChatFormatting;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.item.component.TooltipDisplay;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class QuarryCardItem extends Item {
    public static final int MAX_FILTER_ENTRIES = 18;
    private static final String P = "QuantumFilter";
    private static final String BLACK = P + "Blacklist";
    private static final String DAMAGE = P + "Damage";
    private static final String NBT = P + "Nbt";
    private static final String MOD = P + "Mod";
    private static final String ITEM_COUNT = P + "ItemCount";
    private static final String TAG_COUNT = P + "TagCount";
    private static final String ITEM_PREFIX = P + "Item";
    private static final String TAG_PREFIX = P + "Tag";

    private final QuarryMode mode;

    public QuarryCardItem(Properties properties, QuarryMode mode) {
        super(properties.stacksTo(1));
        this.mode = mode;
    }

    public QuarryMode mode() { return mode; }

    @Override
    public InteractionResult use(Level level, Player player, InteractionHand hand) {
        if (!level.isClientSide() && player instanceof ServerPlayer serverPlayer) {
            int cardSlot = hand == InteractionHand.MAIN_HAND
                    ? player.getInventory().getSelectedSlot()
                    : Inventory.SLOT_OFFHAND;
            serverPlayer.openMenu(
                    new SimpleMenuProvider(
                            (containerId, inventory, p) -> new QuarryFilterMenu(containerId, inventory, cardSlot),
                            Component.translatable("gui.rftoolsbuilder.filter.title")),
                    data -> data.writeVarInt(cardSlot));
        }
        return InteractionResult.SUCCESS;
    }

    private static CompoundTag root(ItemStack stack) {
        CustomData data = stack.get(DataComponents.CUSTOM_DATA);
        return data == null ? new CompoundTag() : data.copyTag();
    }

    private static void saveRoot(ItemStack stack, CompoundTag root) {
        stack.set(DataComponents.CUSTOM_DATA, CustomData.of(root));
    }

    public static boolean blacklist(ItemStack stack) { return root(stack).getBooleanOr(BLACK, false); }
    public static boolean damageMode(ItemStack stack) { return root(stack).getBooleanOr(DAMAGE, false); }
    public static boolean nbtMode(ItemStack stack) { return root(stack).getBooleanOr(NBT, false); }
    public static boolean modMode(ItemStack stack) { return root(stack).getBooleanOr(MOD, false); }
    public static int itemCount(ItemStack stack) { return Math.max(0, Math.min(MAX_FILTER_ENTRIES, root(stack).getIntOr(ITEM_COUNT, 0))); }
    public static int tagCount(ItemStack stack) { return Math.max(0, Math.min(MAX_FILTER_ENTRIES, root(stack).getIntOr(TAG_COUNT, 0))); }
    public static int entryCount(ItemStack stack) { return Math.min(MAX_FILTER_ENTRIES, itemCount(stack) + tagCount(stack)); }

    public static void toggle(ItemStack stack, int setting) {
        CompoundTag r = root(stack);
        String key = switch (setting) {
            case 0 -> BLACK;
            case 1 -> DAMAGE;
            case 2 -> NBT;
            case 3 -> MOD;
            default -> null;
        };
        if (key == null) return;
        r.putBoolean(key, !r.getBooleanOr(key, false));
        saveRoot(stack, r);
    }

    public static String getTag(ItemStack stack, int index) {
        CompoundTag r = root(stack);
        int count = Math.max(0, Math.min(MAX_FILTER_ENTRIES, r.getIntOr(TAG_COUNT, 0)));
        if (index < 0 || index >= count) return "";
        return r.getString(TAG_PREFIX + index).orElse("");
    }

    public static ItemStack getFilterItem(ItemStack stack, int index, HolderLookup.Provider registries) {
        CompoundTag r = root(stack);
        int count = Math.max(0, Math.min(MAX_FILTER_ENTRIES, r.getIntOr(ITEM_COUNT, 0)));
        if (index < 0 || index >= count) return ItemStack.EMPTY;
        CompoundTag tag = r.getCompound(ITEM_PREFIX + index).orElse(null);
        if (tag == null) return ItemStack.EMPTY;
        return ItemStack.parseOptional(registries, tag);
    }

    public static List<String> getTags(ItemStack stack) {
        List<String> result = new ArrayList<>();
        for (int i = 0; i < tagCount(stack); i++) {
            String value = getTag(stack, i);
            if (!value.isBlank()) result.add(value);
        }
        return result;
    }

    public static boolean addFilterItem(ItemStack card, ItemStack source, HolderLookup.Provider registries) {
        if (source.isEmpty() || source.getItem() instanceof QuarryCardItem) return false;
        if (entryCount(card) >= MAX_FILTER_ENTRIES) return false;
        int count = itemCount(card);
        ItemStack normalized = source.copyWithCount(1);
        for (int i = 0; i < count; i++) {
            if (ItemStack.isSameItemSameComponents(getFilterItem(card, i, registries), normalized)) return false;
        }
        CompoundTag r = root(card);
        r.put(ITEM_PREFIX + count, normalized.saveOptional(registries));
        r.putInt(ITEM_COUNT, count + 1);
        saveRoot(card, r);
        return true;
    }

    public static boolean addFilterTag(ItemStack card, String raw) {
        String value = raw == null ? "" : raw.trim().toLowerCase();
        if (value.startsWith("#")) value = value.substring(1);
        if (value.isBlank() || !value.contains(":")) return false;
        Identifier id;
        try { id = Identifier.parse(value); }
        catch (Exception e) { return false; }
        value = id.toString();
        if (entryCount(card) >= MAX_FILTER_ENTRIES) return false;
        int count = tagCount(card);
        for (int i = 0; i < count; i++) if (value.equals(getTag(card, i))) return false;
        CompoundTag r = root(card);
        r.putString(TAG_PREFIX + count, value);
        r.putInt(TAG_COUNT, count + 1);
        saveRoot(card, r);
        return true;
    }

    public static int addTagsFromItem(ItemStack card, ItemStack source) {
        if (source.isEmpty()) return 0;
        int[] added = {0};
        source.getItemHolder().tags().forEach(tag -> {
            if (entryCount(card) < MAX_FILTER_ENTRIES && addFilterTag(card, tag.location().toString())) added[0]++;
        });
        return added[0];
    }

    public static void removeEntry(ItemStack card, int combinedIndex, HolderLookup.Provider registries) {
        int tags = tagCount(card);
        if (combinedIndex < 0 || combinedIndex >= entryCount(card)) return;
        CompoundTag r = root(card);
        if (combinedIndex < tags) {
            for (int i = combinedIndex; i < tags - 1; i++) {
                r.putString(TAG_PREFIX + i, r.getString(TAG_PREFIX + (i + 1)).orElse(""));
            }
            r.remove(TAG_PREFIX + (tags - 1));
            r.putInt(TAG_COUNT, tags - 1);
        } else {
            int index = combinedIndex - tags;
            int items = itemCount(card);
            for (int i = index; i < items - 1; i++) {
                CompoundTag next = r.getCompound(ITEM_PREFIX + (i + 1)).orElse(null);
                if (next != null) r.put(ITEM_PREFIX + i, next.copy());
                else r.remove(ITEM_PREFIX + i);
            }
            r.remove(ITEM_PREFIX + (items - 1));
            r.putInt(ITEM_COUNT, items - 1);
        }
        saveRoot(card, r);
    }

    public static void expandEntryToTags(ItemStack card, int combinedIndex, HolderLookup.Provider registries) {
        int itemIndex = combinedIndex - tagCount(card);
        if (itemIndex < 0 || itemIndex >= itemCount(card)) return;
        ItemStack source = getFilterItem(card, itemIndex, registries);
        if (source.isEmpty()) return;
        removeEntry(card, combinedIndex, registries);
        addTagsFromItem(card, source);
    }

    public static void clearFilter(ItemStack card) {
        CompoundTag r = root(card);
        int items = Math.max(0, r.getIntOr(ITEM_COUNT, 0));
        int tags = Math.max(0, r.getIntOr(TAG_COUNT, 0));
        for (int i = 0; i < items; i++) r.remove(ITEM_PREFIX + i);
        for (int i = 0; i < tags; i++) r.remove(TAG_PREFIX + i);
        r.putInt(ITEM_COUNT, 0);
        r.putInt(TAG_COUNT, 0);
        saveRoot(card, r);
    }

    public static boolean allowsBlock(ItemStack card, BlockState state, HolderLookup.Provider registries) {
        int items = itemCount(card);
        int tags = tagCount(card);
        if (items + tags == 0) return true;
        boolean match = false;

        ItemStack target = new ItemStack(state.getBlock().asItem());
        for (int i = 0; i < tags && !match; i++) {
            try {
                Identifier id = Identifier.parse(getTag(card, i));
                if (state.is(TagKey.create(Registries.BLOCK, id))) match = true;
                if (!match && !target.isEmpty() && target.is(TagKey.create(Registries.ITEM, id))) match = true;
            } catch (Exception ignored) { }
        }

        if (!match && !target.isEmpty()) {
            Identifier targetId = BuiltInRegistries.ITEM.getKey(target.getItem());
            for (int i = 0; i < items && !match; i++) {
                ItemStack filter = getFilterItem(card, i, registries);
                if (filter.isEmpty()) continue;
                if (modMode(card)) {
                    Identifier filterId = BuiltInRegistries.ITEM.getKey(filter.getItem());
                    match = filterId.getNamespace().equals(targetId.getNamespace());
                } else {
                    if (filter.getItem() != target.getItem()) continue;
                    if (damageMode(card) && filter.getDamageValue() != target.getDamageValue()) continue;
                    if (nbtMode(card) && !ItemStack.isSameItemSameComponents(filter, target)) continue;
                    match = true;
                }
            }
        }
        return blacklist(card) ? !match : match;
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, TooltipDisplay display,
                                Consumer<Component> builder, TooltipFlag flag) {
        super.appendHoverText(stack, context, display, builder, flag);
        if (mode.isFortune()) builder.accept(Component.translatable("tooltip.rftoolsbuilder.fortune_iii").withStyle(ChatFormatting.GOLD));
        else if (mode.isSilk()) builder.accept(Component.translatable("tooltip.rftoolsbuilder.silk_touch").withStyle(ChatFormatting.AQUA));
        builder.accept(Component.translatable(mode.isClear() ? "tooltip.rftoolsbuilder.clear_mode" : "tooltip.rftoolsbuilder.replace_mode").withStyle(ChatFormatting.GRAY));
        builder.accept(Component.translatable("tooltip.rftoolsbuilder.filter_summary", blacklist(stack) ? "Blacklist" : "Whitelist", entryCount(stack)).withStyle(ChatFormatting.DARK_AQUA));
        builder.accept(Component.translatable("tooltip.rftoolsbuilder.filter_open").withStyle(ChatFormatting.DARK_GRAY));
    }
}
""", encoding='utf-8')

(java / 'QuarryFilterMenu.java').write_text(r"""package mcjty.rftoolsbuilder;

import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ClickType;
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
        int x = 13, y = 132;
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++)
            addSlot(new Slot(inventory, col + row * 9 + 9, x + col * 18, y + row * 18));
        for (int col = 0; col < 9; col++) addSlot(new Slot(inventory, col, x + col * 18, y + 58));
    }

    public int cardSlot() { return cardSlot; }
    public ItemStack cardStack() {
        if (cardSlot < 0 || cardSlot >= inventory.getContainerSize()) return ItemStack.EMPTY;
        return inventory.getItem(cardSlot);
    }

    @Override
    public void clicked(int slotId, int button, ClickType clickType, Player player) {
        if (slotId >= 0 && slotId < slots.size()) {
            ItemStack source = slots.get(slotId).getItem();
            if (!source.isEmpty() && !(source.getItem() instanceof QuarryCardItem)) {
                if (!player.level().isClientSide()) {
                    if (clickType == ClickType.QUICK_MOVE) QuarryCardItem.addTagsFromItem(cardStack(), source);
                    else QuarryCardItem.addFilterItem(cardStack(), source, player.registryAccess());
                    broadcastChanges();
                }
                return;
            }
        }
        super.clicked(slotId, button, clickType, player);
    }

    @Override
    public boolean clickMenuButton(Player player, int id) {
        ItemStack card = cardStack();
        if (!(card.getItem() instanceof QuarryCardItem)) return false;
        if (id >= 0 && id <= 3) { QuarryCardItem.toggle(card, id); broadcastChanges(); return true; }
        if (id == 4) { QuarryCardItem.clearFilter(card); broadcastChanges(); return true; }
        if (id >= REMOVE_BASE && id < REMOVE_BASE + QuarryCardItem.MAX_FILTER_ENTRIES) {
            QuarryCardItem.removeEntry(card, id - REMOVE_BASE, player.registryAccess()); broadcastChanges(); return true;
        }
        if (id >= EXPAND_BASE && id < EXPAND_BASE + QuarryCardItem.MAX_FILTER_ENTRIES) {
            QuarryCardItem.expandEntryToTags(card, id - EXPAND_BASE, player.registryAccess()); broadcastChanges(); return true;
        }
        return false;
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        if (index < 0 || index >= slots.size()) return ItemStack.EMPTY;
        ItemStack source = slots.get(index).getItem();
        if (source.isEmpty() || source.getItem() instanceof QuarryCardItem) return ItemStack.EMPTY;
        if (!player.level().isClientSide()) { QuarryCardItem.addTagsFromItem(cardStack(), source); broadcastChanges(); }
        return source.copy();
    }

    @Override
    public boolean stillValid(Player player) { return cardStack().getItem() instanceof QuarryCardItem; }
}
""", encoding='utf-8')

p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')
s = s.replace('builder.work((ServerLevel) level, card.mode());', 'builder.work((ServerLevel) level, card.mode(), quarryStack);')
s = s.replace('private void work(ServerLevel level, QuarryMode mode) {', 'private void work(ServerLevel level, QuarryMode mode, ItemStack quarryCard) {')
needle = '''            if (!isMineableTarget(level, target, state)) {\n                cursor++;\n                continue;\n            }\n'''
repl = needle + '''            if (!QuarryCardItem.allowsBlock(quarryCard, state, level.registryAccess())) {\n                cursor++;\n                continue;\n            }\n'''
if needle not in s: raise SystemExit('Mining insertion point not found')
s = s.replace(needle, repl, 1)
p.write_text(s, encoding='utf-8')
print('Quantum filter core applied')

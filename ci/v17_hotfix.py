from pathlib import Path
import binascii
import json
import re
import struct
import sys
import zlib


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")
props_path = root / "gradle.properties"
props = props_path.read_text(encoding="utf-8")
if "mod_version=1.3.13" not in props:
    raise SystemExit("Expected mod_version=1.3.13 before V17 hotfix")


# ---------------------------------------------------------------------------
# Item/tag routing and Void rules.
# ---------------------------------------------------------------------------
entity_path = root / "src/main/java/com/pipecore/block/PipeBlockEntity.java"
entity = entity_path.read_text(encoding="utf-8")

entity = entity.replace(
    "import net.minecraft.core.registries.BuiltInRegistries;\n",
    "import net.minecraft.core.registries.BuiltInRegistries;\n"
    "import net.minecraft.core.registries.Registries;\n",
    1,
)
entity = entity.replace(
    "import net.minecraft.server.level.ServerPlayer;\n",
    "import net.minecraft.server.level.ServerPlayer;\n"
    "import net.minecraft.tags.TagKey;\n",
    1,
)

old_fields = '''    private final String[] voidFilterItemIds = new String[6];
    private final int[] priorities = new int[6];
    public static final int NORMAL_FILTER_SLOTS = 9;
    private final String[][] normalFilterItemIds = new String[6][NORMAL_FILTER_SLOTS];
    private final boolean[] filterBlacklist = new boolean[6];
'''
new_fields = '''    private final String[] voidFilterItemIds = new String[6];
    private final String[] voidFilterTagIds = new String[6];
    private final int[] priorities = new int[6];
    public static final int NORMAL_FILTER_SLOTS = 9;
    private final String[][] normalFilterItemIds = new String[6][NORMAL_FILTER_SLOTS];
    private final String[][] normalFilterTagIds = new String[6][NORMAL_FILTER_SLOTS];
    private final boolean[] filterBlacklist = new boolean[6];
'''
if old_fields not in entity:
    raise SystemExit("V17 field anchor not found")
entity = entity.replace(old_fields, new_fields, 1)

old_ctor = '''            allowFilterItemIds[i] = "";
            voidFilterItemIds[i] = "";
            for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
                normalFilterItemIds[i][slot] = "";
            }
'''
new_ctor = '''            allowFilterItemIds[i] = "";
            voidFilterItemIds[i] = "";
            voidFilterTagIds[i] = "";
            for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
                normalFilterItemIds[i][slot] = "";
                normalFilterTagIds[i][slot] = "";
            }
'''
if old_ctor not in entity:
    raise SystemExit("V17 constructor anchor not found")
entity = entity.replace(old_ctor, new_ctor, 1)

old_accessors = '''    public boolean voidFilterConfigured(Direction direction) { return !voidFilterItemIds[direction.ordinal()].isEmpty(); }
    public boolean filterBlacklist(Direction direction) { return filterBlacklist[direction.ordinal()]; }
'''
new_accessors = '''    public boolean voidFilterConfigured(Direction direction) { return !voidFilterItemIds[direction.ordinal()].isEmpty(); }
    public boolean filterBlacklist(Direction direction) { return filterBlacklist[direction.ordinal()]; }
    public int normalFilterTagSelection(Direction direction, int slot) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return 0;
        int face = direction.ordinal();
        return tagSelection(normalFilterItemIds[face][slot], normalFilterTagIds[face][slot]);
    }
    public int voidFilterTagSelection(Direction direction) {
        int face = direction.ordinal();
        return tagSelection(voidFilterItemIds[face], voidFilterTagIds[face]);
    }
'''
if old_accessors not in entity:
    raise SystemExit("V17 accessor anchor not found")
entity = entity.replace(old_accessors, new_accessors, 1)

items_pattern = re.compile(
    r"    private int transferItems\(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate\) \{.*?\n    \}\n\n    private boolean passesAllowFilter.*?\n    private int transferFluids",
    re.S,
)
items_replacement = r'''    private int transferItems(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate) {
        ResourceHandler<ItemResource> source = level.getCapability(Capabilities.Item.BLOCK, sourcePos, sourceFace.getOpposite());
        if (source == null) return 0;
        int remaining = rate;
        int total = 0;
        int faceIndex = sourceFace.ordinal();
        boolean hasVoidRule = voidFilterCards[faceIndex] && !voidFilterItemIds[faceIndex].isEmpty();

        // Void has its own budget so matching items are deleted without preventing all
        // other items from continuing through the pipe in the same transfer cycle.
        if (hasVoidRule) {
            total += voidMatchingItems(source, voidFilterItemIds[faceIndex], voidFilterTagIds[faceIndex], rate);
        }

        List<ResourceHandler<ItemResource>> targets = new ArrayList<>();
        for (PipeBlockEntity targetPipe : network) {
            for (Direction targetSide : Direction.values()) {
                if (targetPipe.getFaceMode(targetSide) != FaceMode.NORMAL) continue;
                BlockPos targetPos = targetPipe.worldPosition.relative(targetSide);
                if (targetPos.equals(sourcePos) || !targetPipe.isExternalEndpoint(level, targetPos)) continue;
                ResourceHandler<ItemResource> target = level.getCapability(Capabilities.Item.BLOCK, targetPos, targetSide.getOpposite());
                if (target == null || target == source || targets.contains(target)) continue;
                targets.add(target);
            }
        }

        DistributionMode distribution = distributionMode(sourceFace);
        if (distribution == DistributionMode.FURTHEST) Collections.reverse(targets);
        else if (distribution == DistributionMode.RANDOM) Collections.shuffle(targets);
        else if (distribution == DistributionMode.ROUND_ROBIN && !targets.isEmpty()) {
            int start = Math.floorMod(roundRobinCursor[faceIndex], targets.size());
            Collections.rotate(targets, -start);
        }

        boolean movedRoundRobin = false;
        for (ResourceHandler<ItemResource> target : targets) {
            if (remaining <= 0) break;
            try (Transaction tx = Transaction.open(null)) {
                int moved = ResourceHandlerUtil.move(source, target, resource ->
                        (!hasVoidRule || !matchesRule(resource, voidFilterItemIds[faceIndex], voidFilterTagIds[faceIndex]))
                                && passesAllowFilter(faceIndex, resource), remaining, tx);
                if (moved > 0) {
                    tx.commit();
                    remaining -= moved;
                    total += moved;
                    if (distribution == DistributionMode.ROUND_ROBIN) {
                        movedRoundRobin = true;
                        break;
                    }
                }
            }
        }

        if (distribution == DistributionMode.ROUND_ROBIN && movedRoundRobin && !targets.isEmpty()) {
            roundRobinCursor[faceIndex] = Math.floorMod(roundRobinCursor[faceIndex] + 1, targets.size());
        }
        return total;
    }

    private boolean passesAllowFilter(int faceIndex, ItemResource resource) {
        if (!filterCards[faceIndex]) return true;
        boolean configured = false;
        boolean matches = false;
        for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
            String itemId = normalFilterItemIds[faceIndex][slot];
            if (itemId.isEmpty()) continue;
            configured = true;
            if (matchesRule(resource, itemId, normalFilterTagIds[faceIndex][slot])) {
                matches = true;
                break;
            }
        }
        if (!configured) return true;
        return filterBlacklist[faceIndex] ? !matches : matches;
    }

    private static boolean matchesRule(ItemResource resource, String itemId, String tagId) {
        if (itemId.isEmpty() || resource.isEmpty()) return false;
        if (!tagId.isEmpty()) {
            try {
                TagKey<Item> tag = TagKey.create(Registries.ITEM, Identifier.parse(tagId));
                return resource.getItem().builtInRegistryHolder().is(tag);
            } catch (Exception ignored) {
                return false;
            }
        }
        return BuiltInRegistries.ITEM.getKey(resource.getItem()).toString().equals(itemId);
    }

    private static int voidMatchingItems(ResourceHandler<ItemResource> source, String itemId, String tagId, int maxAmount) {
        int voided = 0;
        int size = source.size();
        for (int index = 0; index < size && voided < maxAmount; index++) {
            ItemResource resource = source.getResource(index);
            if (!matchesRule(resource, itemId, tagId)) continue;
            int amount = Math.min(maxAmount - voided, source.getAmountAsInt(index));
            if (amount <= 0) continue;
            try (Transaction tx = Transaction.open(null)) {
                int extracted = source.extract(index, resource, amount, tx);
                if (extracted > 0) {
                    tx.commit();
                    voided += extracted;
                }
            }
        }
        return voided;
    }

    private int transferFluids'''
entity, count = items_pattern.subn(items_replacement, entity, count=1)
if count != 1:
    raise SystemExit("V17 transfer/filter method block not found")

normal_helpers_pattern = re.compile(
    r"    public ItemStack normalFilterStack\(Direction face, int slot\) \{.*?\n    \}\n\n    public ItemStack voidFilterCardStack",
    re.S,
)
normal_helpers_replacement = r'''    public ItemStack normalFilterStack(Direction face, int slot) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return ItemStack.EMPTY;
        String itemId = normalFilterItemIds[face.ordinal()][slot];
        return stackFromItemId(itemId);
    }

    public void setNormalFilterStack(Direction face, int slot, ItemStack stack) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return;
        int i = face.ordinal();
        String value = stack.isEmpty() ? "" : BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
        if (normalFilterItemIds[i][slot].equals(value) && normalFilterTagIds[i][slot].isEmpty()) return;
        normalFilterItemIds[i][slot] = value;
        normalFilterTagIds[i][slot] = "";
        markDirtyAndSync();
    }

    public void cycleNormalFilterTag(Direction face, int slot, Player player) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return;
        int i = face.ordinal();
        if (!filterCards[i] || normalFilterItemIds[i][slot].isEmpty()) return;
        normalFilterTagIds[i][slot] = nextTag(normalFilterItemIds[i][slot], normalFilterTagIds[i][slot]);
        announceRule(player, "message.pipecore.filter_rule", normalFilterTagIds[i][slot]);
        markDirtyAndSync();
    }

    public ItemStack voidFilterStack(Direction face) {
        return stackFromItemId(voidFilterItemIds[face.ordinal()]);
    }

    public void setVoidFilterStack(Direction face, ItemStack stack) {
        int i = face.ordinal();
        String value = stack.isEmpty() ? "" : BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
        if (voidFilterItemIds[i].equals(value) && voidFilterTagIds[i].isEmpty()) return;
        voidFilterItemIds[i] = value;
        voidFilterTagIds[i] = "";
        markDirtyAndSync();
    }

    public void cycleVoidFilterTag(Direction face, Player player) {
        int i = face.ordinal();
        if (!voidFilterCards[i] || voidFilterItemIds[i].isEmpty()) return;
        voidFilterTagIds[i] = nextTag(voidFilterItemIds[i], voidFilterTagIds[i]);
        announceRule(player, "message.pipecore.void_rule", voidFilterTagIds[i]);
        markDirtyAndSync();
    }

    private static ItemStack stackFromItemId(String itemId) {
        if (itemId.isEmpty()) return ItemStack.EMPTY;
        try {
            Item item = BuiltInRegistries.ITEM.getOptional(Identifier.parse(itemId)).orElse(null);
            return item == null ? ItemStack.EMPTY : new ItemStack(item);
        } catch (Exception ignored) {
            return ItemStack.EMPTY;
        }
    }

    private static List<String> tagsForItem(String itemId) {
        ItemStack stack = stackFromItemId(itemId);
        if (stack.isEmpty()) return List.of();
        return stack.getItem().builtInRegistryHolder().tags()
                .map(tag -> tag.location().toString())
                .sorted()
                .toList();
    }

    private static String nextTag(String itemId, String currentTag) {
        List<String> tags = tagsForItem(itemId);
        if (tags.isEmpty()) return "";
        if (currentTag.isEmpty()) return tags.getFirst();
        int current = tags.indexOf(currentTag);
        if (current < 0) return tags.getFirst();
        return current + 1 < tags.size() ? tags.get(current + 1) : "";
    }

    private static int tagSelection(String itemId, String tagId) {
        if (itemId.isEmpty() || tagId.isEmpty()) return 0;
        int index = tagsForItem(itemId).indexOf(tagId);
        return index < 0 ? 0 : index + 1;
    }

    private static void announceRule(Player player, String translationKey, String tagId) {
        Component value = tagId.isEmpty()
                ? Component.translatable("ui.pipecore.exact_item")
                : Component.literal("#" + tagId);
        if (player instanceof ServerPlayer serverPlayer) {
            serverPlayer.sendSystemMessage(Component.translatable(translationKey, value));
        }
    }

    public ItemStack voidFilterCardStack'''
entity, count = normal_helpers_pattern.subn(normal_helpers_replacement, entity, count=1)
if count != 1:
    raise SystemExit("V17 filter helper block not found")

old_void_button = '''        if (buttonId == PipeMenu.BUTTON_VOID_FILTER && kind() == PipeKind.ITEM && voidFilterCards[i]) {
            voidFilterItemIds[i] = itemIdFromHeld(player);
            markDirtyAndSync();
            return true;
        }
'''
if old_void_button not in entity:
    raise SystemExit("V17 legacy Void button block not found")
entity = entity.replace(old_void_button, "", 1)

item_from_held_pattern = re.compile(
    r"\n    private static String itemIdFromHeld\(Player player\) \{.*?\n    \}\n",
    re.S,
)
entity, count = item_from_held_pattern.subn("\n", entity, count=1)
if count != 1:
    raise SystemExit("V17 legacy held-item helper not found")

old_save_void = '            if (!voidFilterItemIds[i].isEmpty()) output.putString("void_filter_" + i, voidFilterItemIds[i]);\n'
new_save_void = old_save_void + '            if (!voidFilterTagIds[i].isEmpty()) output.putString("void_filter_tag_" + i, voidFilterTagIds[i]);\n'
if old_save_void not in entity:
    raise SystemExit("V17 Void save anchor not found")
entity = entity.replace(old_save_void, new_save_void, 1)

old_save_normal = '''                if (!normalFilterItemIds[i][slot].isEmpty()) {
                    output.putString("normal_filter_" + i + "_" + slot, normalFilterItemIds[i][slot]);
                }
'''
new_save_normal = '''                if (!normalFilterItemIds[i][slot].isEmpty()) {
                    output.putString("normal_filter_" + i + "_" + slot, normalFilterItemIds[i][slot]);
                }
                if (!normalFilterTagIds[i][slot].isEmpty()) {
                    output.putString("normal_filter_tag_" + i + "_" + slot, normalFilterTagIds[i][slot]);
                }
'''
if old_save_normal not in entity:
    raise SystemExit("V17 normal filter save anchor not found")
entity = entity.replace(old_save_normal, new_save_normal, 1)

old_load_void = '            voidFilterItemIds[i] = input.getStringOr("void_filter_" + i, "");\n'
new_load_void = old_load_void + '            voidFilterTagIds[i] = input.getStringOr("void_filter_tag_" + i, "");\n'
if old_load_void not in entity:
    raise SystemExit("V17 Void load anchor not found")
entity = entity.replace(old_load_void, new_load_void, 1)

old_load_normal = '                normalFilterItemIds[i][slot] = input.getStringOr("normal_filter_" + i + "_" + slot, "");\n'
new_load_normal = old_load_normal + '                normalFilterTagIds[i][slot] = input.getStringOr("normal_filter_tag_" + i + "_" + slot, "");\n'
if old_load_normal not in entity:
    raise SystemExit("V17 normal filter load anchor not found")
entity = entity.replace(old_load_normal, new_load_normal, 1)
entity_path.write_text(entity, encoding="utf-8")


# ---------------------------------------------------------------------------
# Conditional, compact menu. Filter and Void panels only become active when
# their card is installed. Right-click cycles exact item -> each tag -> exact.
# ---------------------------------------------------------------------------
menu_path = root / "src/main/java/com/pipecore/menu/PipeMenu.java"
menu_path.write_text(r'''package com.pipecore.menu;

import com.pipecore.PipeCore;
import com.pipecore.PipeKind;
import com.pipecore.block.PipeBlockEntity;
import com.pipecore.block.PipeBlockEntity.DistributionMode;
import java.util.function.BooleanSupplier;
import net.minecraft.core.Direction;
import net.minecraft.world.Container;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerData;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;

public final class PipeMenu extends AbstractContainerMenu {
    public static final int BUTTON_DISTRIBUTION = 100;
    public static final int BUTTON_FILTER_MODE = 101;
    public static final int FILTER_SLOT_COUNT = PipeBlockEntity.NORMAL_FILTER_SLOTS;
    private static final int CARD_SLOT_COUNT = 3;
    private static final int FILTER_SLOT_START = CARD_SLOT_COUNT;
    private static final int VOID_SLOT_START = FILTER_SLOT_START + FILTER_SLOT_COUNT;
    private static final int PLAYER_SLOT_START = VOID_SLOT_START + 1;
    private static final int DATA_NORMAL_TAG_START = 6;
    private static final int DATA_VOID_TAG = DATA_NORMAL_TAG_START + FILTER_SLOT_COUNT;
    private static final int DATA_COUNT = DATA_VOID_TAG + 1;

    private final PipeBlockEntity pipe;
    private final Direction outputFace;
    private final SimpleContainer cards;
    private final SimpleContainer normalFilters;
    private final SimpleContainer voidFilter;
    private final ContainerData data;

    public PipeMenu(int containerId, Inventory inventory) {
        this(containerId, inventory, null, Direction.DOWN,
                new SimpleContainer(CARD_SLOT_COUNT), new SimpleContainer(FILTER_SLOT_COUNT),
                new SimpleContainer(1), new SimpleContainerData(DATA_COUNT));
    }

    public PipeMenu(int containerId, Inventory inventory, PipeBlockEntity pipe, Direction outputFace) {
        this(containerId, inventory, pipe, outputFace,
                createServerCards(pipe, outputFace), createServerFilters(pipe, outputFace),
                createServerVoidFilter(pipe, outputFace), createServerData(pipe, outputFace));
    }

    private PipeMenu(int containerId, Inventory inventory, PipeBlockEntity pipe, Direction outputFace,
            SimpleContainer cards, SimpleContainer normalFilters, SimpleContainer voidFilter, ContainerData data) {
        super(PipeCore.PIPE_MENU.get(), containerId);
        this.pipe = pipe;
        this.outputFace = outputFace;
        this.cards = cards;
        this.normalFilters = normalFilters;
        this.voidFilter = voidFilter;
        this.data = data;
        checkContainerDataCount(data, DATA_COUNT);
        addDataSlots(data);

        addSlot(new CardSlot(cards, 0, 38, 29) {
            @Override public boolean mayPlace(ItemStack stack) { return PipeBlockEntity.isTierCard(stack.getItem()); }
        });
        addSlot(new CardSlot(cards, 1, 99, 29) {
            @Override public boolean mayPlace(ItemStack stack) {
                return pipeKind() == PipeKind.ITEM && stack.getItem() == PipeCore.FILTER_CARD.get();
            }
        });
        addSlot(new CardSlot(cards, 2, 160, 29) {
            @Override public boolean mayPlace(ItemStack stack) {
                return pipeKind() == PipeKind.ITEM && stack.getItem() == PipeCore.VOID_FILTER_CARD.get();
            }
        });

        for (int col = 0; col < FILTER_SLOT_COUNT; col++) {
            addSlot(new ConditionalGhostSlot(normalFilters, col, 18 + col * 18, 113,
                    () -> pipeKind() == PipeKind.ITEM && hasFilterCard()));
        }
        addSlot(new ConditionalGhostSlot(voidFilter, 0, 180, 147,
                () -> pipeKind() == PipeKind.ITEM && hasVoidFilterCard()));

        int invY = 187;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9, 18 + col * 18, invY + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) addSlot(new Slot(inventory, col, 18 + col * 18, 245));
    }

    private static SimpleContainer createServerCards(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(CARD_SLOT_COUNT);
        container.setItem(0, pipe.tierCardStack(face));
        container.setItem(1, pipe.filterCardStack(face));
        container.setItem(2, pipe.voidFilterCardStack(face));
        return container;
    }

    private static SimpleContainer createServerFilters(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(FILTER_SLOT_COUNT);
        for (int slot = 0; slot < FILTER_SLOT_COUNT; slot++) container.setItem(slot, pipe.normalFilterStack(face, slot));
        return container;
    }

    private static SimpleContainer createServerVoidFilter(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(1);
        container.setItem(0, pipe.voidFilterStack(face));
        return container;
    }

    private static ContainerData createServerData(PipeBlockEntity pipe, Direction face) {
        return new ContainerData() {
            @Override public int get(int index) {
                if (index >= DATA_NORMAL_TAG_START && index < DATA_VOID_TAG) {
                    return pipe.normalFilterTagSelection(face, index - DATA_NORMAL_TAG_START);
                }
                if (index == DATA_VOID_TAG) return pipe.voidFilterTagSelection(face);
                return switch (index) {
                    case 0 -> face.ordinal();
                    case 1 -> pipe.distributionMode(face).ordinal();
                    case 2 -> pipe.allowFilterConfigured(face) ? 1 : 0;
                    case 3 -> pipe.voidFilterConfigured(face) ? 1 : 0;
                    case 4 -> pipe.kind().ordinal();
                    case 5 -> pipe.filterBlacklist(face) ? 1 : 0;
                    default -> 0;
                };
            }
            @Override public void set(int index, int value) { }
            @Override public int getCount() { return DATA_COUNT; }
        };
    }

    private void syncCardsToPipe() {
        if (pipe != null) pipe.applyCardSlots(outputFace, cards.getItem(0), cards.getItem(1), cards.getItem(2));
    }

    private void syncFiltersToPipe() {
        if (pipe == null) return;
        for (int slot = 0; slot < FILTER_SLOT_COUNT; slot++) pipe.setNormalFilterStack(outputFace, slot, normalFilters.getItem(slot));
    }

    private void syncVoidToPipe() {
        if (pipe != null) pipe.setVoidFilterStack(outputFace, voidFilter.getItem(0));
    }

    @Override public void slotsChanged(Container container) {
        super.slotsChanged(container);
        if (container == cards) syncCardsToPipe();
        if (container == normalFilters) syncFiltersToPipe();
        if (container == voidFilter) syncVoidToPipe();
    }

    public Direction outputFace() {
        Direction[] values = Direction.values();
        return values[Math.floorMod(data.get(0), values.length)];
    }
    public DistributionMode distributionMode() { return DistributionMode.byId(data.get(1)); }
    public boolean allowFilterConfigured() { return data.get(2) != 0; }
    public boolean voidFilterConfigured() { return data.get(3) != 0; }
    public boolean filterBlacklist() { return data.get(5) != 0; }
    public boolean normalFilterUsesTag(int slot) {
        return slot >= 0 && slot < FILTER_SLOT_COUNT && data.get(DATA_NORMAL_TAG_START + slot) > 0;
    }
    public boolean voidFilterUsesTag() { return data.get(DATA_VOID_TAG) > 0; }
    public PipeKind pipeKind() {
        PipeKind[] values = PipeKind.values();
        return values[Math.floorMod(data.get(4), values.length)];
    }
    public boolean hasFilterCard() { return !cards.getItem(1).isEmpty(); }
    public boolean hasVoidFilterCard() { return !cards.getItem(2).isEmpty(); }

    @Override public boolean clickMenuButton(Player player, int buttonId) {
        return pipe != null && pipe.handleOutputButton(player, outputFace, buttonId);
    }

    @Override
    public void clicked(int slotId, int button, ContainerInput clickType, Player player) {
        if (slotId >= FILTER_SLOT_START && slotId < VOID_SLOT_START) {
            if (!hasFilterCard()) return;
            int filterSlot = slotId - FILTER_SLOT_START;
            configureGhost(normalFilters, filterSlot, getCarried(), button, clickType);
            syncFiltersToPipe();
            if (button == 1 && pipe != null && !normalFilters.getItem(filterSlot).isEmpty()) {
                pipe.cycleNormalFilterTag(outputFace, filterSlot, player);
            }
            return;
        }
        if (slotId == VOID_SLOT_START) {
            if (!hasVoidFilterCard()) return;
            configureGhost(voidFilter, 0, getCarried(), button, clickType);
            syncVoidToPipe();
            if (button == 1 && pipe != null && !voidFilter.getItem(0).isEmpty()) {
                pipe.cycleVoidFilterTag(outputFace, player);
            }
            return;
        }
        super.clicked(slotId, button, clickType, player);
    }

    private static void configureGhost(SimpleContainer container, int slot, ItemStack carried,
            int button, ContainerInput clickType) {
        if (clickType != ContainerInput.PICKUP && clickType != ContainerInput.QUICK_MOVE) return;
        if (!carried.isEmpty()) {
            ItemStack ghost = carried.copy();
            ghost.setCount(1);
            container.setItem(slot, ghost);
            container.setChanged();
        } else if (button == 0) {
            container.setItem(slot, ItemStack.EMPTY);
            container.setChanged();
        }
    }

    @Override
    public ItemStack quickMoveStack(Player player, int index) {
        Slot slot = slots.get(index);
        if (!slot.hasItem()) return ItemStack.EMPTY;
        ItemStack source = slot.getItem();
        ItemStack copy = source.copy();
        if (index < CARD_SLOT_COUNT) {
            if (!moveItemStackTo(source, PLAYER_SLOT_START, PLAYER_SLOT_START + 36, true)) return ItemStack.EMPTY;
        } else if (index < PLAYER_SLOT_START) return ItemStack.EMPTY;
        else if (PipeBlockEntity.isTierCard(source.getItem())) {
            if (!moveItemStackTo(source, 0, 1, false)) return ItemStack.EMPTY;
        } else if (pipeKind() == PipeKind.ITEM && source.getItem() == PipeCore.FILTER_CARD.get()) {
            if (!moveItemStackTo(source, 1, 2, false)) return ItemStack.EMPTY;
        } else if (pipeKind() == PipeKind.ITEM && source.getItem() == PipeCore.VOID_FILTER_CARD.get()) {
            if (!moveItemStackTo(source, 2, 3, false)) return ItemStack.EMPTY;
        } else return ItemStack.EMPTY;
        if (source.isEmpty()) slot.setByPlayer(ItemStack.EMPTY); else slot.setChanged();
        return copy;
    }

    @Override public void removed(Player player) {
        syncCardsToPipe();
        syncFiltersToPipe();
        syncVoidToPipe();
        super.removed(player);
    }

    @Override public boolean stillValid(Player player) {
        return pipe == null || (!pipe.isRemoved() && player.distanceToSqr(
                pipe.getBlockPos().getX() + 0.5, pipe.getBlockPos().getY() + 0.5,
                pipe.getBlockPos().getZ() + 0.5) <= 64.0);
    }

    private static class CardSlot extends Slot {
        CardSlot(Container container, int slot, int x, int y) { super(container, slot, x, y); }
        @Override public int getMaxStackSize() { return 1; }
    }

    private static final class ConditionalGhostSlot extends Slot {
        private final BooleanSupplier active;
        ConditionalGhostSlot(Container container, int slot, int x, int y, BooleanSupplier active) {
            super(container, slot, x, y);
            this.active = active;
        }
        @Override public boolean mayPlace(ItemStack stack) { return false; }
        @Override public boolean mayPickup(Player player) { return false; }
        @Override public boolean isActive() { return active.getAsBoolean(); }
        @Override public int getMaxStackSize() { return 1; }
    }
}
''', encoding="utf-8")


# ---------------------------------------------------------------------------
# Reorganized UI and conditional panels.
# ---------------------------------------------------------------------------
screen_path = root / "src/main/java/com/pipecore/client/PipeScreen.java"
screen_path.write_text(r'''package com.pipecore.client;

import com.pipecore.PipeKind;
import com.pipecore.menu.PipeMenu;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.player.Inventory;

public final class PipeScreen extends AbstractContainerScreen<PipeMenu> {
    private static final int W = 214;
    private static final int H = 268;
    private static final int GRAPHITE = 0xFF151A20;
    private static final int PANEL = 0xFF20272F;
    private static final int PANEL_DARK = 0xFF10151A;
    private static final int BORDER = 0xFF353E47;
    private static final int TEXT = 0xFFE8EDF1;
    private static final int MUTED = 0xFFA3ADB6;
    private static final int TAG = 0xFF5DE7FF;
    private Button distributionButton;
    private Button filterModeButton;

    public PipeScreen(PipeMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, W, H);
        this.titleLabelX = 8;
        this.titleLabelY = 7;
        this.inventoryLabelX = 18;
        this.inventoryLabelY = 175;
    }

    @Override protected void init() {
        super.init();
        distributionButton = addRenderableWidget(Button.builder(distributionLabel(), b -> request(PipeMenu.BUTTON_DISTRIBUTION))
                .bounds(leftPos + 9, topPos + 55, 196, 18).build());
        filterModeButton = addRenderableWidget(Button.builder(filterModeLabel(), b -> request(PipeMenu.BUTTON_FILTER_MODE))
                .bounds(leftPos + 11, topPos + 81, 192, 18).build());
        updateControls();
    }

    private void request(int id) {
        if (minecraft != null && minecraft.gameMode != null) minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
    }

    @Override protected void containerTick() {
        super.containerTick();
        updateControls();
    }

    private void updateControls() {
        boolean itemPipe = menu.pipeKind() == PipeKind.ITEM;
        distributionButton.visible = itemPipe;
        distributionButton.active = itemPipe;
        distributionButton.setMessage(distributionLabel());
        filterModeButton.visible = itemPipe && menu.hasFilterCard();
        filterModeButton.active = filterModeButton.visible;
        filterModeButton.setMessage(filterModeLabel());
    }

    private Component distributionLabel() {
        if (menu.pipeKind() != PipeKind.ITEM) return Component.translatable("ui.pipecore.distribution_na");
        String key = switch (menu.distributionMode()) {
            case NEAREST -> "distribution.pipecore.nearest";
            case FURTHEST -> "distribution.pipecore.furthest";
            case ROUND_ROBIN -> "distribution.pipecore.round_robin";
            case RANDOM -> "distribution.pipecore.random";
        };
        return Component.translatable("ui.pipecore.distribution", Component.translatable(key));
    }

    private Component filterModeLabel() {
        return Component.translatable(menu.filterBlacklist()
                ? "ui.pipecore.filter_blacklist"
                : "ui.pipecore.filter_whitelist");
    }

    private int accent() {
        return switch (menu.pipeKind()) {
            case ITEM -> 0xFFFF9638;
            case FLUID -> 0xFF32DDF7;
            case ENERGY -> 0xFFFFE53B;
            case CHEMICAL -> 0xFF55E77A;
        };
    }

    @Override public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {
        super.extractBackground(g, mouseX, mouseY, partialTick);
        int x = leftPos, y = topPos, a = accent();
        g.fill(x, y, x + W, y + H, 0xF20A0D10);
        g.fill(x + 2, y + 2, x + W - 2, y + H - 2, GRAPHITE);
        g.fill(x + 5, y + 5, x + W - 5, y + 7, a);

        g.fill(x + 7, y + 20, x + W - 7, y + 51, PANEL);
        g.fill(x + 7, y + 20, x + W - 7, y + 21, BORDER);
        drawSlot(g, x + 37, y + 28, a);
        drawSlot(g, x + 98, y + 28, a);
        drawSlot(g, x + 159, y + 28, a);

        if (menu.hasFilterCard()) {
            g.fill(x + 7, y + 77, x + W - 7, y + 134, PANEL);
            g.fill(x + 7, y + 77, x + W - 7, y + 79, a);
            for (int col = 0; col < PipeMenu.FILTER_SLOT_COUNT; col++) {
                int slotX = x + 17 + col * 18;
                drawSlot(g, slotX, y + 112, a);
                if (menu.normalFilterUsesTag(col)) drawTagBadge(g, slotX + 12, y + 112);
            }
        }

        if (menu.hasVoidFilterCard()) {
            g.fill(x + 7, y + 139, x + W - 7, y + 170, PANEL);
            g.fill(x + 7, y + 139, x + W - 7, y + 141, 0xFFFF4D78);
            drawSlot(g, x + 179, y + 146, 0xFFFF4D78);
            if (menu.voidFilterUsesTag()) drawTagBadge(g, x + 191, y + 146);
        }

        g.fill(x + 7, y + 173, x + W - 7, y + 174, BORDER);
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++)
            drawInventorySlot(g, x + 17 + col * 18, y + 186 + row * 18);
        for (int col = 0; col < 9; col++) drawInventorySlot(g, x + 17 + col * 18, y + 244);
    }

    private void drawTagBadge(GuiGraphicsExtractor g, int x, int y) {
        g.fill(x, y, x + 8, y + 8, PANEL_DARK);
        g.text(font, Component.literal("#"), x + 1, y, TAG, false);
    }

    private static void drawSlot(GuiGraphicsExtractor g, int x, int y, int accent) {
        g.fill(x, y, x + 20, y + 20, BORDER);
        g.fill(x + 1, y + 1, x + 19, y + 19, 0xFF0D1115);
        g.fill(x + 1, y + 1, x + 19, y + 3, accent);
    }

    private static void drawInventorySlot(GuiGraphicsExtractor g, int x, int y) {
        g.fill(x, y, x + 20, y + 20, BORDER);
        g.fill(x + 1, y + 1, x + 19, y + 19, 0xFF0D1115);
    }

    @Override protected void extractLabels(GuiGraphicsExtractor g, int mouseX, int mouseY) {
        String face = menu.outputFace().getName().toUpperCase();
        g.text(font, Component.literal("PIPE CORE  ·  OUTPUT " + face), 8, 8, TEXT, false);
        g.text(font, Component.translatable("ui.pipecore.tier"), 34, 20, MUTED, false);
        g.text(font, Component.translatable("ui.pipecore.filter_card"), 87, 20, MUTED, false);
        g.text(font, Component.translatable("ui.pipecore.void_card"), 152, 20, MUTED, false);
        if (menu.hasFilterCard()) {
            g.text(font, Component.translatable("ui.pipecore.filter_rule_help"), 11, 102, MUTED, false);
        }
        if (menu.hasVoidFilterCard()) {
            g.text(font, Component.translatable("ui.pipecore.void_rule_title"), 11, 145, TEXT, false);
            g.text(font, Component.translatable("ui.pipecore.void_rule_help"), 11, 157, MUTED, false);
        }
        g.text(font, Component.translatable("container.inventory"), inventoryLabelX, inventoryLabelY, MUTED, false);
    }
}
''', encoding="utf-8")


# ---------------------------------------------------------------------------
# Language strings.
# ---------------------------------------------------------------------------
lang_dir = root / "src/main/resources/assets/pipecore/lang"
translations = {
    "pt_br.json": {
        "ui.pipecore.filter_rule_help": "Item ou tag • botão direito alterna",
        "ui.pipecore.void_rule_title": "VOID SELETIVO",
        "ui.pipecore.void_rule_help": "Apaga a regra • restante passa",
        "ui.pipecore.exact_item": "item exato",
        "message.pipecore.filter_rule": "Filtro configurado para %s",
        "message.pipecore.void_rule": "Void configurado para %s",
    },
    "en_us.json": {
        "ui.pipecore.filter_rule_help": "Item or tag • right-click cycles",
        "ui.pipecore.void_rule_title": "SELECTIVE VOID",
        "ui.pipecore.void_rule_help": "Deletes the rule • the rest passes",
        "ui.pipecore.exact_item": "exact item",
        "message.pipecore.filter_rule": "Filter set to %s",
        "message.pipecore.void_rule": "Void set to %s",
    },
}
for filename, additions in translations.items():
    path = lang_dir / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Pixel-perfect textures: thicker black outline next to the colored core and
# electric amber energy palette. The center strip geometry/colors stay intact
# for item/fluid/chemical pipes.
# ---------------------------------------------------------------------------
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_rgba_png(path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise SystemExit(f"Invalid PNG: {path}")
    pos = len(PNG_SIGNATURE)
    width = height = None
    compressed = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (bit_depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise SystemExit(f"Unsupported PNG format: {path}")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    stride = width * 4
    rows = []
    offset = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        scan = raw[offset + 1:offset + 1 + stride]
        offset += stride + 1
        recon = bytearray(stride)
        for i, value in enumerate(scan):
            left = recon[i - 4] if i >= 4 else 0
            up = previous[i]
            up_left = previous[i - 4] if i >= 4 else 0
            predictor = {
                0: 0,
                1: left,
                2: up,
                3: (left + up) // 2,
                4: paeth(left, up, up_left),
            }.get(filter_type)
            if predictor is None:
                raise SystemExit(f"Unsupported PNG filter {filter_type}: {path}")
            recon[i] = (value + predictor) & 0xFF
        rows.append([tuple(recon[x:x + 4]) for x in range(0, stride, 4)])
        previous = recon
    return width, height, rows


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def write_rgba_png(path, width, height, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for pixel in row:
            raw.extend(pixel)
    out = bytearray(PNG_SIGNATURE)
    out.extend(png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    out.extend(png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
    out.extend(png_chunk(b"IEND", b""))
    path.write_bytes(out)


textures = root / "src/main/resources/assets/pipecore/textures/block"
vertical_names = [
    f"{kind}_pipe{suffix}.png"
    for kind in ("item", "fluid", "energy", "chemical")
    for suffix in ("_vertical", "_output_vertical")
]
for filename in vertical_names:
    path = textures / filename
    width, height, rows = read_rgba_png(path)
    for y in range(2, height - 2):
        rows[y][5] = (24, 26, 29, 255)
        rows[y][10] = (24, 26, 29, 255)
    write_rgba_png(path, width, height, rows)

energy_palette = {
    (81, 42, 113, 255): (92, 71, 0, 255),
    (104, 55, 146, 255): (118, 88, 0, 255),
    (140, 73, 188, 255): (195, 145, 0, 255),
    (155, 81, 217, 255): (214, 164, 0, 255),
    (170, 89, 214, 255): (233, 183, 22, 255),
    (179, 94, 250, 255): (246, 199, 24, 255),
    (206, 108, 255, 255): (255, 230, 55, 255),
    (239, 126, 255, 255): (255, 248, 135, 255),
}
for filename in ("energy_pipe.png", "energy_pipe_vertical.png", "energy_pipe_output.png", "energy_pipe_output_vertical.png"):
    path = textures / filename
    width, height, rows = read_rgba_png(path)
    rows = [[energy_palette.get(pixel, pixel) for pixel in row] for row in rows]
    write_rgba_png(path, width, height, rows)


props_path.write_text(props.replace("mod_version=1.3.13", "mod_version=1.3.14", 1), encoding="utf-8")
print("Applied Pipe Core V17: conditional UI, item/tag filters, selective Void, thicker outlines, amber energy, version 1.3.14")

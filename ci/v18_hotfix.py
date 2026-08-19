from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")
props_path = root / "gradle.properties"
props = props_path.read_text(encoding="utf-8")
if "mod_version=1.3.14" not in props:
    raise SystemExit("Expected mod_version=1.3.14 before V18 hotfix")

# ---------------------------------------------------------------------------
# Pipe Core 1.3.15 / V18
# - 100 normal filter rules per item-pipe face
# - 16 Void rules per item-pipe face
# - whitelist/blacklist is stored per rule (blacklist always wins)
# - if any whitelist exists, unmatched items are rejected; with only blacklists,
#   unmatched items are accepted. Void follows the same model: W = delete,
#   B = protect/exclude from deletion.
# - paged compact UI: 10 normal rules/page, 8 Void rules/page
# ---------------------------------------------------------------------------

entity_path = root / "src/main/java/com/pipecore/block/PipeBlockEntity.java"
entity = entity_path.read_text(encoding="utf-8")

old_fields = '''    private final String[] voidFilterItemIds = new String[6];
    private final String[] voidFilterTagIds = new String[6];
    private final int[] priorities = new int[6];
    public static final int NORMAL_FILTER_SLOTS = 9;
    private final String[][] normalFilterItemIds = new String[6][NORMAL_FILTER_SLOTS];
    private final String[][] normalFilterTagIds = new String[6][NORMAL_FILTER_SLOTS];
    private final boolean[] filterBlacklist = new boolean[6];
'''
new_fields = '''    public static final int NORMAL_FILTER_SLOTS = 100;
    public static final int VOID_FILTER_SLOTS = 16;
    private final String[][] voidFilterItemIds = new String[6][VOID_FILTER_SLOTS];
    private final String[][] voidFilterTagIds = new String[6][VOID_FILTER_SLOTS];
    private final boolean[][] voidFilterBlacklist = new boolean[6][VOID_FILTER_SLOTS];
    private final int[] priorities = new int[6];
    private final String[][] normalFilterItemIds = new String[6][NORMAL_FILTER_SLOTS];
    private final String[][] normalFilterTagIds = new String[6][NORMAL_FILTER_SLOTS];
    private final boolean[][] normalFilterBlacklist = new boolean[6][NORMAL_FILTER_SLOTS];
    // Kept only to read old V16/V17 worlds. V18 filtering never uses this global mode.
    private final boolean[] filterBlacklist = new boolean[6];
'''
if old_fields not in entity:
    raise SystemExit("V18 field anchor not found")
entity = entity.replace(old_fields, new_fields, 1)

old_ctor = '''            allowFilterItemIds[i] = "";
            voidFilterItemIds[i] = "";
            voidFilterTagIds[i] = "";
            for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
                normalFilterItemIds[i][slot] = "";
                normalFilterTagIds[i][slot] = "";
            }
'''
new_ctor = '''            allowFilterItemIds[i] = "";
            for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
                normalFilterItemIds[i][slot] = "";
                normalFilterTagIds[i][slot] = "";
                normalFilterBlacklist[i][slot] = false;
            }
            for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {
                voidFilterItemIds[i][slot] = "";
                voidFilterTagIds[i][slot] = "";
                voidFilterBlacklist[i][slot] = false;
            }
'''
if old_ctor not in entity:
    raise SystemExit("V18 constructor anchor not found")
entity = entity.replace(old_ctor, new_ctor, 1)

old_accessors = '''    public boolean voidFilterConfigured(Direction direction) { return !voidFilterItemIds[direction.ordinal()].isEmpty(); }
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
new_accessors = '''    public boolean voidFilterConfigured(Direction direction) {
        int face = direction.ordinal();
        for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {
            if (!voidFilterItemIds[face][slot].isEmpty()) return true;
        }
        return false;
    }
    public boolean filterBlacklist(Direction direction) { return filterBlacklist[direction.ordinal()]; }
'''
if old_accessors not in entity:
    raise SystemExit("V18 accessor anchor not found")
entity = entity.replace(old_accessors, new_accessors, 1)

items_pattern = re.compile(
    r"    private int transferItems\(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate\) \{.*?\n    private int transferFluids",
    re.S,
)
items_replacement = r'''    private int transferItems(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate) {
        ResourceHandler<ItemResource> source = level.getCapability(Capabilities.Item.BLOCK, sourcePos, sourceFace.getOpposite());
        if (source == null) return 0;
        int remaining = rate;
        int total = 0;
        int faceIndex = sourceFace.ordinal();
        boolean hasVoidRules = voidFilterCards[faceIndex] && voidFilterConfigured(sourceFace);

        // Void has its own budget. Items selected by the per-entry W/B rules are
        // deleted first; protected/unmatched items remain available for transport.
        if (hasVoidRules) {
            total += voidMatchingItems(source, faceIndex, rate);
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
                        (!hasVoidRules || !shouldVoid(faceIndex, resource))
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
        boolean hasWhitelist = false;
        boolean matchedWhitelist = false;

        for (int slot = 0; slot < NORMAL_FILTER_SLOTS; slot++) {
            String itemId = normalFilterItemIds[faceIndex][slot];
            if (itemId.isEmpty()) continue;
            configured = true;
            boolean match = matchesRule(resource, itemId, normalFilterTagIds[faceIndex][slot]);
            if (normalFilterBlacklist[faceIndex][slot]) {
                if (match) return false; // blacklist always wins
            } else {
                hasWhitelist = true;
                if (match) matchedWhitelist = true;
            }
        }

        if (!configured) return true;
        return !hasWhitelist || matchedWhitelist;
    }

    private boolean shouldVoid(int faceIndex, ItemResource resource) {
        if (!voidFilterCards[faceIndex]) return false;
        boolean configured = false;
        boolean hasWhitelist = false;
        boolean matchedWhitelist = false;

        for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {
            String itemId = voidFilterItemIds[faceIndex][slot];
            if (itemId.isEmpty()) continue;
            configured = true;
            boolean match = matchesRule(resource, itemId, voidFilterTagIds[faceIndex][slot]);
            if (voidFilterBlacklist[faceIndex][slot]) {
                if (match) return false; // protected from Void
            } else {
                hasWhitelist = true;
                if (match) matchedWhitelist = true;
            }
        }

        if (!configured) return false;
        return !hasWhitelist || matchedWhitelist;
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

    private int voidMatchingItems(ResourceHandler<ItemResource> source, int faceIndex, int maxAmount) {
        int voided = 0;
        int size = source.size();
        for (int index = 0; index < size && voided < maxAmount; index++) {
            ItemResource resource = source.getResource(index);
            if (!shouldVoid(faceIndex, resource)) continue;
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
    raise SystemExit("V18 transfer/filter block not found")

helpers_pattern = re.compile(
    r"    public ItemStack normalFilterStack\(Direction face, int slot\) \{.*?\n    public ItemStack voidFilterCardStack",
    re.S,
)
helpers_replacement = r'''    public ItemStack normalFilterStack(Direction face, int slot) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return ItemStack.EMPTY;
        return stackFromItemId(normalFilterItemIds[face.ordinal()][slot]);
    }

    public void setNormalFilterStack(Direction face, int slot, ItemStack stack) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return;
        int i = face.ordinal();
        String value = stack.isEmpty() ? "" : BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
        boolean clearing = value.isEmpty();
        if (normalFilterItemIds[i][slot].equals(value) && normalFilterTagIds[i][slot].isEmpty()) {
            if (clearing && normalFilterBlacklist[i][slot]) {
                normalFilterBlacklist[i][slot] = false;
                markDirtyAndSync();
            }
            return;
        }
        normalFilterItemIds[i][slot] = value;
        normalFilterTagIds[i][slot] = "";
        if (clearing) normalFilterBlacklist[i][slot] = false;
        markDirtyAndSync();
    }

    public boolean normalFilterBlacklist(Direction face, int slot) {
        return slot >= 0 && slot < NORMAL_FILTER_SLOTS && normalFilterBlacklist[face.ordinal()][slot];
    }

    public void toggleNormalFilterRule(Direction face, int slot) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return;
        int i = face.ordinal();
        if (!filterCards[i] || normalFilterItemIds[i][slot].isEmpty()) return;
        normalFilterBlacklist[i][slot] = !normalFilterBlacklist[i][slot];
        markDirtyAndSync();
    }

    public int normalFilterTagSelection(Direction face, int slot) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return 0;
        int i = face.ordinal();
        return tagSelection(normalFilterItemIds[i][slot], normalFilterTagIds[i][slot]);
    }

    public void cycleNormalFilterTag(Direction face, int slot, Player player) {
        if (slot < 0 || slot >= NORMAL_FILTER_SLOTS) return;
        int i = face.ordinal();
        if (!filterCards[i] || normalFilterItemIds[i][slot].isEmpty()) return;
        normalFilterTagIds[i][slot] = nextTag(normalFilterItemIds[i][slot], normalFilterTagIds[i][slot]);
        announceRule(player, "message.pipecore.filter_rule", normalFilterTagIds[i][slot]);
        markDirtyAndSync();
    }

    public ItemStack voidFilterStack(Direction face, int slot) {
        if (slot < 0 || slot >= VOID_FILTER_SLOTS) return ItemStack.EMPTY;
        return stackFromItemId(voidFilterItemIds[face.ordinal()][slot]);
    }

    public void setVoidFilterStack(Direction face, int slot, ItemStack stack) {
        if (slot < 0 || slot >= VOID_FILTER_SLOTS) return;
        int i = face.ordinal();
        String value = stack.isEmpty() ? "" : BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
        boolean clearing = value.isEmpty();
        if (voidFilterItemIds[i][slot].equals(value) && voidFilterTagIds[i][slot].isEmpty()) {
            if (clearing && voidFilterBlacklist[i][slot]) {
                voidFilterBlacklist[i][slot] = false;
                markDirtyAndSync();
            }
            return;
        }
        voidFilterItemIds[i][slot] = value;
        voidFilterTagIds[i][slot] = "";
        if (clearing) voidFilterBlacklist[i][slot] = false;
        markDirtyAndSync();
    }

    public boolean voidFilterBlacklist(Direction face, int slot) {
        return slot >= 0 && slot < VOID_FILTER_SLOTS && voidFilterBlacklist[face.ordinal()][slot];
    }

    public void toggleVoidFilterRule(Direction face, int slot) {
        if (slot < 0 || slot >= VOID_FILTER_SLOTS) return;
        int i = face.ordinal();
        if (!voidFilterCards[i] || voidFilterItemIds[i][slot].isEmpty()) return;
        voidFilterBlacklist[i][slot] = !voidFilterBlacklist[i][slot];
        markDirtyAndSync();
    }

    public int voidFilterTagSelection(Direction face, int slot) {
        if (slot < 0 || slot >= VOID_FILTER_SLOTS) return 0;
        int i = face.ordinal();
        return tagSelection(voidFilterItemIds[i][slot], voidFilterTagIds[i][slot]);
    }

    public void cycleVoidFilterTag(Direction face, int slot, Player player) {
        if (slot < 0 || slot >= VOID_FILTER_SLOTS) return;
        int i = face.ordinal();
        if (!voidFilterCards[i] || voidFilterItemIds[i][slot].isEmpty()) return;
        voidFilterTagIds[i][slot] = nextTag(voidFilterItemIds[i][slot], voidFilterTagIds[i][slot]);
        announceRule(player, "message.pipecore.void_rule", voidFilterTagIds[i][slot]);
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
entity, count = helpers_pattern.subn(helpers_replacement, entity, count=1)
if count != 1:
    raise SystemExit("V18 filter helper block not found")

# If older code clears the single Void rule when the card is removed, expand that
# clear to all 16 rules. The V18 helper/constructor replacements above are excluded.
entity = entity.replace(
    '            voidFilterItemIds[i] = "";\n',
    '            for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {\n'
    '                voidFilterItemIds[i][slot] = "";\n'
    '                voidFilterTagIds[i][slot] = "";\n'
    '                voidFilterBlacklist[i][slot] = false;\n'
    '            }\n'
)

old_save_void = '''            if (!voidFilterItemIds[i].isEmpty()) output.putString("void_filter_" + i, voidFilterItemIds[i]);
            if (!voidFilterTagIds[i].isEmpty()) output.putString("void_filter_tag_" + i, voidFilterTagIds[i]);
'''
new_save_void = '''            for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {
                if (!voidFilterItemIds[i][slot].isEmpty()) {
                    output.putString("void_filter_" + i + "_" + slot, voidFilterItemIds[i][slot]);
                }
                if (!voidFilterTagIds[i][slot].isEmpty()) {
                    output.putString("void_filter_tag_" + i + "_" + slot, voidFilterTagIds[i][slot]);
                }
                if (voidFilterBlacklist[i][slot]) {
                    output.putBoolean("void_filter_black_" + i + "_" + slot, true);
                }
            }
'''
if old_save_void not in entity:
    raise SystemExit("V18 Void save anchor not found")
entity = entity.replace(old_save_void, new_save_void, 1)

normal_save_pattern = re.compile(
    r'''(            for \(int slot = 0; slot < NORMAL_FILTER_SLOTS; slot\+\+\) \{\n                if \(!normalFilterItemIds\[i\]\[slot\]\.isEmpty\(\)\) \{\n                    output\.putString\("normal_filter_" \+ i \+ "_" \+ slot, normalFilterItemIds\[i\]\[slot\]\);\n                \}\n                if \(!normalFilterTagIds\[i\]\[slot\]\.isEmpty\(\)\) \{\n                    output\.putString\("normal_filter_tag_" \+ i \+ "_" \+ slot, normalFilterTagIds\[i\]\[slot\]\);\n                \}\n)(            \})'''
)
entity, count = normal_save_pattern.subn(
    r'''\1                if (normalFilterBlacklist[i][slot]) {
                    output.putBoolean("normal_filter_black_" + i + "_" + slot, true);
                }
\2''',
    entity,
    count=1,
)
if count != 1:
    raise SystemExit("V18 normal save loop not found")

old_load_void = '''            voidFilterItemIds[i] = input.getStringOr("void_filter_" + i, "");
            voidFilterTagIds[i] = input.getStringOr("void_filter_tag_" + i, "");
'''
new_load_void = '''            String legacyVoidItem = input.getStringOr("void_filter_" + i, "");
            String legacyVoidTag = input.getStringOr("void_filter_tag_" + i, "");
            for (int slot = 0; slot < VOID_FILTER_SLOTS; slot++) {
                voidFilterItemIds[i][slot] = input.getStringOr(
                        "void_filter_" + i + "_" + slot, slot == 0 ? legacyVoidItem : "");
                voidFilterTagIds[i][slot] = input.getStringOr(
                        "void_filter_tag_" + i + "_" + slot, slot == 0 ? legacyVoidTag : "");
                voidFilterBlacklist[i][slot] = input.getBooleanOr(
                        "void_filter_black_" + i + "_" + slot, false);
            }
'''
if old_load_void not in entity:
    raise SystemExit("V18 Void load anchor not found")
entity = entity.replace(old_load_void, new_load_void, 1)

old_load_normal = '''                normalFilterItemIds[i][slot] = input.getStringOr("normal_filter_" + i + "_" + slot, "");
                normalFilterTagIds[i][slot] = input.getStringOr("normal_filter_tag_" + i + "_" + slot, "");
'''
new_load_normal = old_load_normal + '''                normalFilterBlacklist[i][slot] = input.getBooleanOr("normal_filter_black_" + i + "_" + slot, false);
'''
if old_load_normal not in entity:
    raise SystemExit("V18 normal load anchor not found")
entity = entity.replace(old_load_normal, new_load_normal, 1)

# No 1D Void filter accesses may survive V18.
leftovers = [line for line in entity.splitlines()
             if re.search(r'voidFilter(?:Item|Tag)Ids\[[^\]]+\](?!\[)', line)]
if leftovers:
    raise SystemExit("V18 left 1D Void accesses:\n" + "\n".join(leftovers))

entity_path.write_text(entity, encoding="utf-8")

# ---------------------------------------------------------------------------
# Paged menu: 10 visible normal rules out of 100, 8 visible Void rules out of 16.
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
    // Legacy constant kept because PipeBlockEntity from older build stages references it.
    public static final int BUTTON_FILTER_MODE = 101;
    public static final int BUTTON_NORMAL_PREV = 110;
    public static final int BUTTON_NORMAL_NEXT = 111;
    public static final int BUTTON_VOID_PREV = 112;
    public static final int BUTTON_VOID_NEXT = 113;
    public static final int BUTTON_NORMAL_RULE_BASE = 200;
    public static final int BUTTON_VOID_RULE_BASE = 220;

    public static final int NORMAL_FILTER_CAPACITY = PipeBlockEntity.NORMAL_FILTER_SLOTS;
    public static final int VOID_FILTER_CAPACITY = PipeBlockEntity.VOID_FILTER_SLOTS;
    public static final int NORMAL_VISIBLE_SLOTS = 10;
    public static final int VOID_VISIBLE_SLOTS = 8;
    public static final int NORMAL_PAGE_COUNT = (NORMAL_FILTER_CAPACITY + NORMAL_VISIBLE_SLOTS - 1) / NORMAL_VISIBLE_SLOTS;
    public static final int VOID_PAGE_COUNT = (VOID_FILTER_CAPACITY + VOID_VISIBLE_SLOTS - 1) / VOID_VISIBLE_SLOTS;

    private static final int CARD_SLOT_COUNT = 3;
    private static final int FILTER_SLOT_START = CARD_SLOT_COUNT;
    private static final int VOID_SLOT_START = FILTER_SLOT_START + NORMAL_VISIBLE_SLOTS;
    private static final int PLAYER_SLOT_START = VOID_SLOT_START + VOID_VISIBLE_SLOTS;

    private static final int DATA_NORMAL_TAG_START = 6;
    private static final int DATA_NORMAL_BLACK_START = DATA_NORMAL_TAG_START + NORMAL_FILTER_CAPACITY;
    private static final int DATA_VOID_TAG_START = DATA_NORMAL_BLACK_START + NORMAL_FILTER_CAPACITY;
    private static final int DATA_VOID_BLACK_START = DATA_VOID_TAG_START + VOID_FILTER_CAPACITY;
    private static final int DATA_COUNT = DATA_VOID_BLACK_START + VOID_FILTER_CAPACITY;

    private final PipeBlockEntity pipe;
    private final Direction outputFace;
    private final SimpleContainer cards;
    private final SimpleContainer normalFilters;
    private final SimpleContainer voidFilters;
    private final ContainerData data;
    private int normalPage;
    private int voidPage;
    private boolean refreshingPage;

    public PipeMenu(int containerId, Inventory inventory) {
        this(containerId, inventory, null, Direction.DOWN,
                new SimpleContainer(CARD_SLOT_COUNT),
                new SimpleContainer(NORMAL_VISIBLE_SLOTS),
                new SimpleContainer(VOID_VISIBLE_SLOTS),
                new SimpleContainerData(DATA_COUNT));
    }

    public PipeMenu(int containerId, Inventory inventory, PipeBlockEntity pipe, Direction outputFace) {
        this(containerId, inventory, pipe, outputFace,
                createServerCards(pipe, outputFace),
                createServerFilters(pipe, outputFace),
                createServerVoidFilters(pipe, outputFace),
                createServerData(pipe, outputFace));
    }

    private PipeMenu(int containerId, Inventory inventory, PipeBlockEntity pipe, Direction outputFace,
            SimpleContainer cards, SimpleContainer normalFilters, SimpleContainer voidFilters, ContainerData data) {
        super(PipeCore.PIPE_MENU.get(), containerId);
        this.pipe = pipe;
        this.outputFace = outputFace;
        this.cards = cards;
        this.normalFilters = normalFilters;
        this.voidFilters = voidFilters;
        this.data = data;
        this.normalPage = 0;
        this.voidPage = 0;
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

        for (int local = 0; local < NORMAL_VISIBLE_SLOTS; local++) {
            int col = local % 5;
            int row = local / 5;
            addSlot(new ConditionalGhostSlot(normalFilters, local, 14 + col * 38, 102 + row * 23,
                    () -> pipeKind() == PipeKind.ITEM && hasFilterCard()));
        }
        for (int local = 0; local < VOID_VISIBLE_SLOTS; local++) {
            int col = local % 4;
            int row = local / 4;
            addSlot(new ConditionalGhostSlot(voidFilters, local, 26 + col * 45, 177 + row * 23,
                    () -> pipeKind() == PipeKind.ITEM && hasVoidFilterCard()));
        }

        int invY = 239;
        for (int row = 0; row < 3; row++) {
            for (int col = 0; col < 9; col++) {
                addSlot(new Slot(inventory, col + row * 9 + 9, 18 + col * 18, invY + row * 18));
            }
        }
        for (int col = 0; col < 9; col++) addSlot(new Slot(inventory, col, 18 + col * 18, 297));
    }

    private static SimpleContainer createServerCards(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(CARD_SLOT_COUNT);
        container.setItem(0, pipe.tierCardStack(face));
        container.setItem(1, pipe.filterCardStack(face));
        container.setItem(2, pipe.voidFilterCardStack(face));
        return container;
    }

    private static SimpleContainer createServerFilters(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(NORMAL_VISIBLE_SLOTS);
        for (int local = 0; local < NORMAL_VISIBLE_SLOTS; local++) {
            container.setItem(local, pipe.normalFilterStack(face, local));
        }
        return container;
    }

    private static SimpleContainer createServerVoidFilters(PipeBlockEntity pipe, Direction face) {
        SimpleContainer container = new SimpleContainer(VOID_VISIBLE_SLOTS);
        for (int local = 0; local < VOID_VISIBLE_SLOTS; local++) {
            container.setItem(local, pipe.voidFilterStack(face, local));
        }
        return container;
    }

    private static ContainerData createServerData(PipeBlockEntity pipe, Direction face) {
        return new ContainerData() {
            @Override public int get(int index) {
                if (index >= DATA_NORMAL_TAG_START && index < DATA_NORMAL_BLACK_START) {
                    return pipe.normalFilterTagSelection(face, index - DATA_NORMAL_TAG_START);
                }
                if (index >= DATA_NORMAL_BLACK_START && index < DATA_VOID_TAG_START) {
                    return pipe.normalFilterBlacklist(face, index - DATA_NORMAL_BLACK_START) ? 1 : 0;
                }
                if (index >= DATA_VOID_TAG_START && index < DATA_VOID_BLACK_START) {
                    return pipe.voidFilterTagSelection(face, index - DATA_VOID_TAG_START);
                }
                if (index >= DATA_VOID_BLACK_START && index < DATA_COUNT) {
                    return pipe.voidFilterBlacklist(face, index - DATA_VOID_BLACK_START) ? 1 : 0;
                }
                return switch (index) {
                    case 0 -> face.ordinal();
                    case 1 -> pipe.distributionMode(face).ordinal();
                    case 2 -> pipe.allowFilterConfigured(face) ? 1 : 0;
                    case 3 -> pipe.voidFilterConfigured(face) ? 1 : 0;
                    case 4 -> pipe.kind().ordinal();
                    case 5 -> pipe.filterBlacklist(face) ? 1 : 0; // legacy only
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

    private int normalIndex(int local) { return normalPage * NORMAL_VISIBLE_SLOTS + local; }
    private int voidIndex(int local) { return voidPage * VOID_VISIBLE_SLOTS + local; }

    private void syncFiltersToPipe() {
        if (pipe == null || refreshingPage) return;
        for (int local = 0; local < NORMAL_VISIBLE_SLOTS; local++) {
            int index = normalIndex(local);
            if (index < NORMAL_FILTER_CAPACITY) pipe.setNormalFilterStack(outputFace, index, normalFilters.getItem(local));
        }
    }

    private void syncVoidToPipe() {
        if (pipe == null || refreshingPage) return;
        for (int local = 0; local < VOID_VISIBLE_SLOTS; local++) {
            int index = voidIndex(local);
            if (index < VOID_FILTER_CAPACITY) pipe.setVoidFilterStack(outputFace, index, voidFilters.getItem(local));
        }
    }

    private void refreshNormalPage() {
        if (pipe == null) return;
        refreshingPage = true;
        try {
            for (int local = 0; local < NORMAL_VISIBLE_SLOTS; local++) {
                int index = normalIndex(local);
                normalFilters.setItem(local, index < NORMAL_FILTER_CAPACITY
                        ? pipe.normalFilterStack(outputFace, index) : ItemStack.EMPTY);
            }
        } finally {
            refreshingPage = false;
        }
        broadcastChanges();
    }

    private void refreshVoidPage() {
        if (pipe == null) return;
        refreshingPage = true;
        try {
            for (int local = 0; local < VOID_VISIBLE_SLOTS; local++) {
                int index = voidIndex(local);
                voidFilters.setItem(local, index < VOID_FILTER_CAPACITY
                        ? pipe.voidFilterStack(outputFace, index) : ItemStack.EMPTY);
            }
        } finally {
            refreshingPage = false;
        }
        broadcastChanges();
    }

    @Override public void slotsChanged(Container container) {
        super.slotsChanged(container);
        if (refreshingPage) return;
        if (container == cards) syncCardsToPipe();
        if (container == normalFilters) syncFiltersToPipe();
        if (container == voidFilters) syncVoidToPipe();
    }

    public Direction outputFace() {
        Direction[] values = Direction.values();
        return values[Math.floorMod(data.get(0), values.length)];
    }
    public DistributionMode distributionMode() { return DistributionMode.byId(data.get(1)); }
    public PipeKind pipeKind() {
        PipeKind[] values = PipeKind.values();
        return values[Math.floorMod(data.get(4), values.length)];
    }
    public boolean hasFilterCard() { return !cards.getItem(1).isEmpty(); }
    public boolean hasVoidFilterCard() { return !cards.getItem(2).isEmpty(); }
    public int normalPage() { return normalPage; }
    public int voidPage() { return voidPage; }

    public ItemStack normalVisibleStack(int local) {
        return local >= 0 && local < NORMAL_VISIBLE_SLOTS ? normalFilters.getItem(local) : ItemStack.EMPTY;
    }
    public ItemStack voidVisibleStack(int local) {
        return local >= 0 && local < VOID_VISIBLE_SLOTS ? voidFilters.getItem(local) : ItemStack.EMPTY;
    }
    public boolean normalFilterUsesTag(int local) {
        int index = normalIndex(local);
        return index >= 0 && index < NORMAL_FILTER_CAPACITY && data.get(DATA_NORMAL_TAG_START + index) > 0;
    }
    public boolean normalRuleBlacklist(int local) {
        int index = normalIndex(local);
        return index >= 0 && index < NORMAL_FILTER_CAPACITY && data.get(DATA_NORMAL_BLACK_START + index) != 0;
    }
    public boolean voidFilterUsesTag(int local) {
        int index = voidIndex(local);
        return index >= 0 && index < VOID_FILTER_CAPACITY && data.get(DATA_VOID_TAG_START + index) > 0;
    }
    public boolean voidRuleBlacklist(int local) {
        int index = voidIndex(local);
        return index >= 0 && index < VOID_FILTER_CAPACITY && data.get(DATA_VOID_BLACK_START + index) != 0;
    }

    public boolean changeNormalPageClient(int delta) {
        int next = Math.max(0, Math.min(NORMAL_PAGE_COUNT - 1, normalPage + delta));
        if (next == normalPage) return false;
        normalPage = next;
        return true;
    }
    public boolean changeVoidPageClient(int delta) {
        int next = Math.max(0, Math.min(VOID_PAGE_COUNT - 1, voidPage + delta));
        if (next == voidPage) return false;
        voidPage = next;
        return true;
    }

    private boolean changeNormalPageServer(int delta) {
        int next = Math.max(0, Math.min(NORMAL_PAGE_COUNT - 1, normalPage + delta));
        if (next == normalPage) return false;
        syncFiltersToPipe();
        normalPage = next;
        refreshNormalPage();
        return true;
    }
    private boolean changeVoidPageServer(int delta) {
        int next = Math.max(0, Math.min(VOID_PAGE_COUNT - 1, voidPage + delta));
        if (next == voidPage) return false;
        syncVoidToPipe();
        voidPage = next;
        refreshVoidPage();
        return true;
    }

    @Override public boolean clickMenuButton(Player player, int buttonId) {
        if (pipe == null) return false;
        if (buttonId == BUTTON_NORMAL_PREV) return changeNormalPageServer(-1);
        if (buttonId == BUTTON_NORMAL_NEXT) return changeNormalPageServer(1);
        if (buttonId == BUTTON_VOID_PREV) return changeVoidPageServer(-1);
        if (buttonId == BUTTON_VOID_NEXT) return changeVoidPageServer(1);
        if (buttonId >= BUTTON_NORMAL_RULE_BASE && buttonId < BUTTON_NORMAL_RULE_BASE + NORMAL_VISIBLE_SLOTS) {
            int local = buttonId - BUTTON_NORMAL_RULE_BASE;
            int index = normalIndex(local);
            if (hasFilterCard() && index < NORMAL_FILTER_CAPACITY) {
                pipe.toggleNormalFilterRule(outputFace, index);
                broadcastChanges();
                return true;
            }
            return false;
        }
        if (buttonId >= BUTTON_VOID_RULE_BASE && buttonId < BUTTON_VOID_RULE_BASE + VOID_VISIBLE_SLOTS) {
            int local = buttonId - BUTTON_VOID_RULE_BASE;
            int index = voidIndex(local);
            if (hasVoidFilterCard() && index < VOID_FILTER_CAPACITY) {
                pipe.toggleVoidFilterRule(outputFace, index);
                broadcastChanges();
                return true;
            }
            return false;
        }
        return pipe.handleOutputButton(player, outputFace, buttonId);
    }

    @Override
    public void clicked(int slotId, int button, ContainerInput clickType, Player player) {
        if (slotId >= FILTER_SLOT_START && slotId < VOID_SLOT_START) {
            if (!hasFilterCard()) return;
            int local = slotId - FILTER_SLOT_START;
            configureGhost(normalFilters, local, getCarried(), button, clickType);
            syncFiltersToPipe();
            int index = normalIndex(local);
            if (button == 1 && pipe != null && !normalFilters.getItem(local).isEmpty() && index < NORMAL_FILTER_CAPACITY) {
                pipe.cycleNormalFilterTag(outputFace, index, player);
            }
            return;
        }
        if (slotId >= VOID_SLOT_START && slotId < PLAYER_SLOT_START) {
            if (!hasVoidFilterCard()) return;
            int local = slotId - VOID_SLOT_START;
            configureGhost(voidFilters, local, getCarried(), button, clickType);
            syncVoidToPipe();
            int index = voidIndex(local);
            if (button == 1 && pipe != null && !voidFilters.getItem(local).isEmpty() && index < VOID_FILTER_CAPACITY) {
                pipe.cycleVoidFilterTag(outputFace, index, player);
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
        if (index < 0 || index >= slots.size()) return ItemStack.EMPTY;
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
# UI: compact paged filter editors with individual W/B toggles.
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
    private static final int H = 320;
    private static final int GRAPHITE = 0xFF151A20;
    private static final int PANEL = 0xFF20272F;
    private static final int PANEL_DARK = 0xFF10151A;
    private static final int BORDER = 0xFF353E47;
    private static final int TEXT = 0xFFE8EDF1;
    private static final int MUTED = 0xFFA3ADB6;
    private static final int TAG = 0xFF5DE7FF;
    private static final int WHITE_RULE = 0xFF58E9B0;
    private static final int BLACK_RULE = 0xFFFF647C;

    private Button distributionButton;
    private Button normalPrevButton;
    private Button normalNextButton;
    private Button voidPrevButton;
    private Button voidNextButton;
    private final Button[] normalRuleButtons = new Button[PipeMenu.NORMAL_VISIBLE_SLOTS];
    private final Button[] voidRuleButtons = new Button[PipeMenu.VOID_VISIBLE_SLOTS];

    public PipeScreen(PipeMenu menu, Inventory inventory, Component title) {
        super(menu, inventory, title, W, H);
        this.titleLabelX = 8;
        this.titleLabelY = 7;
        this.inventoryLabelX = 18;
        this.inventoryLabelY = 227;
    }

    @Override protected void init() {
        super.init();
        distributionButton = addRenderableWidget(Button.builder(distributionLabel(), b -> request(PipeMenu.BUTTON_DISTRIBUTION))
                .bounds(leftPos + 9, topPos + 55, 196, 18).build());

        normalPrevButton = addRenderableWidget(Button.builder(Component.literal("<"), b -> changeNormalPage(-1))
                .bounds(leftPos + 157, topPos + 81, 20, 16).build());
        normalNextButton = addRenderableWidget(Button.builder(Component.literal(">"), b -> changeNormalPage(1))
                .bounds(leftPos + 183, topPos + 81, 20, 16).build());

        for (int local = 0; local < normalRuleButtons.length; local++) {
            final int index = local;
            int col = local % 5;
            int row = local / 5;
            int bx = leftPos + 34 + col * 38;
            int by = topPos + 101 + row * 23;
            normalRuleButtons[local] = addRenderableWidget(Button.builder(Component.literal("W"),
                    b -> request(PipeMenu.BUTTON_NORMAL_RULE_BASE + index)).bounds(bx, by, 17, 20).build());
        }

        voidPrevButton = addRenderableWidget(Button.builder(Component.literal("<"), b -> changeVoidPage(-1))
                .bounds(leftPos + 157, topPos + 156, 20, 16).build());
        voidNextButton = addRenderableWidget(Button.builder(Component.literal(">"), b -> changeVoidPage(1))
                .bounds(leftPos + 183, topPos + 156, 20, 16).build());

        for (int local = 0; local < voidRuleButtons.length; local++) {
            final int index = local;
            int col = local % 4;
            int row = local / 4;
            int bx = leftPos + 46 + col * 45;
            int by = topPos + 176 + row * 23;
            voidRuleButtons[local] = addRenderableWidget(Button.builder(Component.literal("W"),
                    b -> request(PipeMenu.BUTTON_VOID_RULE_BASE + index)).bounds(bx, by, 17, 20).build());
        }
        updateControls();
    }

    private void request(int id) {
        if (minecraft != null && minecraft.gameMode != null) minecraft.gameMode.handleInventoryButtonClick(menu.containerId, id);
    }

    private void changeNormalPage(int delta) {
        if (!menu.changeNormalPageClient(delta)) return;
        request(delta < 0 ? PipeMenu.BUTTON_NORMAL_PREV : PipeMenu.BUTTON_NORMAL_NEXT);
        updateControls();
    }

    private void changeVoidPage(int delta) {
        if (!menu.changeVoidPageClient(delta)) return;
        request(delta < 0 ? PipeMenu.BUTTON_VOID_PREV : PipeMenu.BUTTON_VOID_NEXT);
        updateControls();
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

        boolean normal = itemPipe && menu.hasFilterCard();
        normalPrevButton.visible = normal;
        normalNextButton.visible = normal;
        normalPrevButton.active = normal && menu.normalPage() > 0;
        normalNextButton.active = normal && menu.normalPage() + 1 < PipeMenu.NORMAL_PAGE_COUNT;
        for (int local = 0; local < normalRuleButtons.length; local++) {
            Button button = normalRuleButtons[local];
            button.visible = normal;
            button.active = normal && !menu.normalVisibleStack(local).isEmpty();
            button.setMessage(Component.literal(menu.normalRuleBlacklist(local) ? "B" : "W"));
        }

        boolean voidFilter = itemPipe && menu.hasVoidFilterCard();
        voidPrevButton.visible = voidFilter;
        voidNextButton.visible = voidFilter;
        voidPrevButton.active = voidFilter && menu.voidPage() > 0;
        voidNextButton.active = voidFilter && menu.voidPage() + 1 < PipeMenu.VOID_PAGE_COUNT;
        for (int local = 0; local < voidRuleButtons.length; local++) {
            Button button = voidRuleButtons[local];
            button.visible = voidFilter;
            button.active = voidFilter && !menu.voidVisibleStack(local).isEmpty();
            button.setMessage(Component.literal(menu.voidRuleBlacklist(local) ? "B" : "W"));
        }
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
            g.fill(x + 7, y + 77, x + W - 7, y + 147, PANEL);
            g.fill(x + 7, y + 77, x + W - 7, y + 79, a);
            for (int local = 0; local < PipeMenu.NORMAL_VISIBLE_SLOTS; local++) {
                int col = local % 5;
                int row = local / 5;
                int slotX = x + 13 + col * 38;
                int slotY = y + 101 + row * 23;
                drawSlot(g, slotX, slotY, a);
                if (menu.normalFilterUsesTag(local)) drawTagBadge(g, slotX + 12, slotY);
                drawRuleRail(g, slotX + 20, slotY, menu.normalRuleBlacklist(local));
            }
        }

        if (menu.hasVoidFilterCard()) {
            g.fill(x + 7, y + 152, x + W - 7, y + 222, PANEL);
            g.fill(x + 7, y + 152, x + W - 7, y + 154, 0xFFFF4D78);
            for (int local = 0; local < PipeMenu.VOID_VISIBLE_SLOTS; local++) {
                int col = local % 4;
                int row = local / 4;
                int slotX = x + 25 + col * 45;
                int slotY = y + 176 + row * 23;
                drawSlot(g, slotX, slotY, 0xFFFF4D78);
                if (menu.voidFilterUsesTag(local)) drawTagBadge(g, slotX + 12, slotY);
                drawRuleRail(g, slotX + 20, slotY, menu.voidRuleBlacklist(local));
            }
        }

        g.fill(x + 7, y + 225, x + W - 7, y + 226, BORDER);
        for (int row = 0; row < 3; row++) for (int col = 0; col < 9; col++)
            drawInventorySlot(g, x + 17 + col * 18, y + 238 + row * 18);
        for (int col = 0; col < 9; col++) drawInventorySlot(g, x + 17 + col * 18, y + 296);
    }

    private void drawRuleRail(GuiGraphicsExtractor g, int x, int y, boolean blacklist) {
        int c = blacklist ? BLACK_RULE : WHITE_RULE;
        g.fill(x, y, x + 18, y + 20, PANEL_DARK);
        g.fill(x, y, x + 2, y + 20, c);
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
            g.text(font, Component.literal("FILTER  " + (menu.normalPage() + 1) + "/" + PipeMenu.NORMAL_PAGE_COUNT), 11, 83, TEXT, false);
            g.text(font, Component.translatable("ui.pipecore.filter_rule_help_v18"), 11, 137, MUTED, false);
        }
        if (menu.hasVoidFilterCard()) {
            g.text(font, Component.literal("VOID  " + (menu.voidPage() + 1) + "/" + PipeMenu.VOID_PAGE_COUNT), 11, 158, TEXT, false);
            g.text(font, Component.translatable("ui.pipecore.void_rule_help_v18"), 11, 212, MUTED, false);
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
        "ui.pipecore.filter_rule_help_v18": "W permite • B bloqueia • dir.=tag",
        "ui.pipecore.void_rule_help_v18": "W apaga • B protege • dir.=tag",
        "ui.pipecore.filter_whitelist": "Whitelist",
        "ui.pipecore.filter_blacklist": "Blacklist",
    },
    "en_us.json": {
        "ui.pipecore.filter_rule_help_v18": "W allows • B blocks • right=tag",
        "ui.pipecore.void_rule_help_v18": "W voids • B protects • right=tag",
        "ui.pipecore.filter_whitelist": "Whitelist",
        "ui.pipecore.filter_blacklist": "Blacklist",
    },
}
for filename, additions in translations.items():
    path = lang_dir / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

props_path.write_text(props.replace("mod_version=1.3.14", "mod_version=1.3.15", 1), encoding="utf-8")
print("Applied Pipe Core V18: 100 normal + 16 Void per-entry W/B filter rules, paged UI, version 1.3.15")

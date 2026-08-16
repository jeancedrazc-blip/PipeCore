from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]).resolve()
java_root = root / 'src/main/java'
res_root = root / 'src/main/resources'

# Strip the MDK example mod and replace it with the isolated project.
shutil.rmtree(java_root, ignore_errors=True)
java_root.mkdir(parents=True, exist_ok=True)

pkg = java_root / 'com/jeancedraz/fluidbucketcrafting'
mixin_pkg = pkg / 'mixin'
pkg.mkdir(parents=True, exist_ok=True)
mixin_pkg.mkdir(parents=True, exist_ok=True)

(root / 'gradle.properties').write_text('''# Gradle\norg.gradle.jvmargs=-Xmx2G\norg.gradle.daemon=false\norg.gradle.parallel=true\norg.gradle.caching=true\n\n# Environment\nminecraft_version=26.1.2\nminecraft_version_range=[26.1.2]\nneo_version=26.1.2.95\n\n# Mod\nmod_id=fluidbucketcrafting\nmod_name=Fluid Bucket Crafting\nmod_license=MIT\nmod_version=1.0.0\nmod_group_id=com.jeancedraz.fluidbucketcrafting\n''', encoding='utf-8')

(pkg / 'FluidBucketCrafting.java').write_text(r'''package com.jeancedraz.fluidbucketcrafting;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Block;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.capabilities.RegisterCapabilitiesEvent;
import net.neoforged.neoforge.common.NeoForge;

import java.util.ArrayList;
import java.util.List;

@Mod(FluidBucketCrafting.MOD_ID)
public final class FluidBucketCrafting {
    public static final String MOD_ID = "fluidbucketcrafting";

    public FluidBucketCrafting(IEventBus modBus) {
        modBus.addListener(this::registerCapabilities);
        NeoForge.EVENT_BUS.register(new FluidCraftingEvents());
    }

    private void registerCapabilities(RegisterCapabilitiesEvent event) {
        List<Block> blocks = new ArrayList<>();
        BuiltInRegistries.BLOCK.forEach(block -> {
            if (!event.isBlockRegistered(Capabilities.Fluid.BLOCK, block)) {
                blocks.add(block);
            }
        });

        if (!blocks.isEmpty()) {
            event.registerBlock(
                    Capabilities.Fluid.BLOCK,
                    (level, pos, state, blockEntity, side) -> CraftingTableSupport.isSupported(state.getBlock())
                            ? CraftingTableFluidHandler.get(level, pos)
                            : null,
                    blocks.toArray(Block[]::new)
            );
        }
    }
}
''', encoding='utf-8')

(pkg / 'CraftingTableSupport.java').write_text(r'''package com.jeancedraz.fluidbucketcrafting;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.CraftingTableBlock;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class CraftingTableSupport {
    private static final Set<Block> DISCOVERED = ConcurrentHashMap.newKeySet();

    private CraftingTableSupport() {}

    public static boolean isSupported(Block block) {
        if (block instanceof CraftingTableBlock || DISCOVERED.contains(block)) {
            return true;
        }
        var id = BuiltInRegistries.BLOCK.getKey(block);
        if (id == null) {
            return false;
        }
        String path = id.getPath();
        return path.contains("crafting_table") || path.contains("craftingtable") || path.contains("workbench");
    }

    public static boolean discover(Block block) {
        return DISCOVERED.add(block);
    }
}
''', encoding='utf-8')

(pkg / 'CraftingTableFluidHandler.java').write_text(r'''package com.jeancedraz.fluidbucketcrafting;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.neoforge.fluids.FluidType;
import net.neoforged.neoforge.transfer.ResourceHandler;
import net.neoforged.neoforge.transfer.TransferPreconditions;
import net.neoforged.neoforge.transfer.fluid.FluidResource;
import net.neoforged.neoforge.transfer.transaction.SnapshotJournal;
import net.neoforged.neoforge.transfer.transaction.TransactionContext;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.WeakHashMap;

public final class CraftingTableFluidHandler extends SnapshotJournal<CraftingTableFluidHandler.State>
        implements ResourceHandler<FluidResource> {

    public static final int CAPACITY = FluidType.BUCKET_VOLUME;

    private static final Map<Level, Map<Long, CraftingTableFluidHandler>> HANDLERS = new WeakHashMap<>();

    public static CraftingTableFluidHandler get(Level level, BlockPos pos) {
        synchronized (HANDLERS) {
            return HANDLERS
                    .computeIfAbsent(level, ignored -> new HashMap<>())
                    .computeIfAbsent(pos.asLong(), ignored -> new CraftingTableFluidHandler(level, pos.immutable()));
        }
    }

    public record State(FluidResource resource, int amount) {}

    private final Level level;
    private final BlockPos pos;
    private FluidResource resource = FluidResource.EMPTY;
    private int amount;

    private CraftingTableFluidHandler(Level level, BlockPos pos) {
        this.level = level;
        this.pos = pos;
    }

    @Override
    public int size() {
        return 1;
    }

    @Override
    public FluidResource getResource(int index) {
        Objects.checkIndex(index, 1);
        return amount <= 0 ? FluidResource.EMPTY : resource;
    }

    @Override
    public long getAmountAsLong(int index) {
        Objects.checkIndex(index, 1);
        return amount;
    }

    @Override
    public long getCapacityAsLong(int index, FluidResource resource) {
        Objects.checkIndex(index, 1);
        return isAllowed(resource) ? CAPACITY : 0;
    }

    @Override
    public boolean isValid(int index, FluidResource resource) {
        Objects.checkIndex(index, 1);
        TransferPreconditions.checkNonEmpty(resource);
        return isAllowed(resource);
    }

    private static boolean isAllowed(FluidResource resource) {
        Fluid fluid = resource.getFluid();
        return fluid == Fluids.WATER || fluid == Fluids.LAVA;
    }

    @Override
    public int insert(int index, FluidResource incoming, int requested, TransactionContext transaction) {
        Objects.checkIndex(index, 1);
        TransferPreconditions.checkNonEmptyNonNegative(incoming, requested);
        if (!isAllowed(incoming) || requested == 0) {
            return 0;
        }
        if (amount > 0 && !resource.equals(incoming)) {
            return 0;
        }

        int inserted = Math.min(requested, CAPACITY - amount);
        if (inserted > 0) {
            updateSnapshots(transaction);
            resource = incoming;
            amount += inserted;
        }
        return inserted;
    }

    @Override
    public int extract(int index, FluidResource requestedResource, int requested, TransactionContext transaction) {
        Objects.checkIndex(index, 1);
        TransferPreconditions.checkNonEmptyNonNegative(requestedResource, requested);
        if (amount <= 0 || requested == 0 || !resource.equals(requestedResource)) {
            return 0;
        }

        int extracted = Math.min(requested, amount);
        if (extracted > 0) {
            updateSnapshots(transaction);
            amount -= extracted;
            if (amount == 0) {
                resource = FluidResource.EMPTY;
            }
        }
        return extracted;
    }

    public boolean has(Fluid fluid, int requested) {
        return amount >= requested && !resource.isEmpty() && resource.getFluid() == fluid;
    }

    public boolean consumeDirect(Fluid fluid, int requested) {
        if (!has(fluid, requested)) {
            return false;
        }
        amount -= requested;
        if (amount == 0) {
            resource = FluidResource.EMPTY;
        }
        return true;
    }

    public Level level() {
        return level;
    }

    public BlockPos pos() {
        return pos;
    }

    @Override
    protected State createSnapshot() {
        return new State(resource, amount);
    }

    @Override
    protected void revertToSnapshot(State snapshot) {
        resource = snapshot.resource();
        amount = snapshot.amount();
    }
}
''', encoding='utf-8')

(pkg / 'FluidCraftingEvents.java').write_text(r'''package com.jeancedraz.fluidbucketcrafting;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.CraftingMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
import net.neoforged.neoforge.event.tick.PlayerTickEvent;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class FluidCraftingEvents {
    private record ActiveCraft(BlockPos pos, Fluid fluid, Item result) {}

    private static final Map<UUID, BlockPos> LAST_CLICKED_BLOCK = new ConcurrentHashMap<>();
    private static final Map<UUID, BlockPos> OPEN_TABLE = new ConcurrentHashMap<>();
    private static final Map<UUID, ActiveCraft> ACTIVE_CRAFT = new ConcurrentHashMap<>();

    @SubscribeEvent
    public void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        if (!event.getEntity().level().isClientSide()) {
            LAST_CLICKED_BLOCK.put(event.getEntity().getUUID(), event.getPos().immutable());
        }
    }

    @SubscribeEvent
    public void onPlayerTick(PlayerTickEvent.Post event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        if (!(player.containerMenu instanceof CraftingMenu menu)) {
            OPEN_TABLE.remove(player.getUUID());
            ACTIVE_CRAFT.remove(player.getUUID());
            return;
        }

        BlockPos pos = OPEN_TABLE.get(player.getUUID());
        if (pos == null) {
            pos = LAST_CLICKED_BLOCK.get(player.getUUID());
            if (pos == null) {
                return;
            }
            OPEN_TABLE.put(player.getUUID(), pos);
        }

        if (!player.level().isLoaded(pos)) {
            ACTIVE_CRAFT.remove(player.getUUID());
            return;
        }

        var block = player.level().getBlockState(pos).getBlock();
        if (CraftingTableSupport.discover(block)) {
            player.level().invalidateCapabilities(pos);
        }

        updateResult(player, menu, pos);
    }

    private static void updateResult(ServerPlayer player, CraftingMenu menu, BlockPos pos) {
        int bucketSlot = findSingleIngredientBucket(menu);
        Slot resultSlot = menu.getSlot(0);
        ActiveCraft old = ACTIVE_CRAFT.get(player.getUUID());

        if (bucketSlot < 0) {
            clearOurResult(player, menu, resultSlot, old);
            return;
        }

        CraftingTableFluidHandler handler = CraftingTableFluidHandler.get(player.level(), pos);
        Fluid fluid;
        Item result;
        if (handler.has(Fluids.WATER, CraftingTableFluidHandler.CAPACITY)) {
            fluid = Fluids.WATER;
            result = Items.WATER_BUCKET;
        } else if (handler.has(Fluids.LAVA, CraftingTableFluidHandler.CAPACITY)) {
            fluid = Fluids.LAVA;
            result = Items.LAVA_BUCKET;
        } else {
            clearOurResult(player, menu, resultSlot, old);
            return;
        }

        ItemStack current = resultSlot.getItem();
        if (!current.isEmpty() && current.getItem() != result && old == null) {
            return;
        }

        resultSlot.set(new ItemStack(result));
        ACTIVE_CRAFT.put(player.getUUID(), new ActiveCraft(pos, fluid, result));
        menu.broadcastChanges();
    }

    private static int findSingleIngredientBucket(AbstractContainerMenu menu) {
        if (menu.slots.size() < 10) {
            return -1;
        }
        int found = -1;
        for (int i = 1; i <= 9; i++) {
            ItemStack stack = menu.getSlot(i).getItem();
            if (stack.isEmpty()) {
                continue;
            }
            if (!stack.is(Items.BUCKET) || found != -1) {
                return -1;
            }
            found = i;
        }
        return found;
    }

    private static void clearOurResult(ServerPlayer player, CraftingMenu menu, Slot resultSlot, ActiveCraft old) {
        if (old != null && resultSlot.getItem().getItem() == old.result()) {
            resultSlot.set(ItemStack.EMPTY);
            menu.broadcastChanges();
        }
        ACTIVE_CRAFT.remove(player.getUUID());
    }

    public static boolean handleSpecialTake(Player player, ItemStack taken) {
        if (!(player instanceof ServerPlayer serverPlayer) || !(player.containerMenu instanceof CraftingMenu menu)) {
            return false;
        }

        ActiveCraft craft = ACTIVE_CRAFT.get(player.getUUID());
        if (craft == null || taken.getItem() != craft.result()) {
            return false;
        }

        int bucketSlotIndex = findSingleIngredientBucket(menu);
        if (bucketSlotIndex < 0) {
            ACTIVE_CRAFT.remove(player.getUUID());
            return false;
        }

        CraftingTableFluidHandler handler = CraftingTableFluidHandler.get(serverPlayer.level(), craft.pos());
        if (!handler.consumeDirect(craft.fluid(), CraftingTableFluidHandler.CAPACITY)) {
            ACTIVE_CRAFT.remove(player.getUUID());
            return false;
        }

        Slot bucketSlot = menu.getSlot(bucketSlotIndex);
        ItemStack bucketStack = bucketSlot.getItem();
        bucketStack.shrink(1);
        bucketSlot.setChanged();

        menu.getSlot(0).set(ItemStack.EMPTY);
        ACTIVE_CRAFT.remove(player.getUUID());
        taken.onCraftedBy(player, 1);
        menu.broadcastChanges();
        return true;
    }
}
''', encoding='utf-8')

(mixin_pkg / 'ResultSlotMixin.java').write_text(r'''package com.jeancedraz.fluidbucketcrafting.mixin;

import com.jeancedraz.fluidbucketcrafting.FluidCraftingEvents;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ResultSlot;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ResultSlot.class)
public abstract class ResultSlotMixin {
    @Inject(method = "onTake", at = @At("HEAD"), cancellable = true)
    private void fluidbucketcrafting$consumeFluid(Player player, ItemStack stack, CallbackInfo ci) {
        if (FluidCraftingEvents.handleSpecialTake(player, stack)) {
            ci.cancel();
        }
    }
}
''', encoding='utf-8')

# Replace resources from the template.
for child in list(res_root.iterdir()):
    if child.name == 'META-INF':
        continue
    if child.is_dir():
        shutil.rmtree(child)
    else:
        child.unlink()

meta = res_root / 'META-INF'
meta.mkdir(parents=True, exist_ok=True)
(meta / 'neoforge.mods.toml').write_text('''modLoader="javafml"\nloaderVersion="[3,)"\nlicense="MIT"\n\n[[mods]]\nmodId="fluidbucketcrafting"\nversion="1.0.0"\ndisplayName="Fluid Bucket Crafting"\nauthors="Jan"\ndescription=''' + "'''" + '''\nAllows standard crafting tables to receive real water/lava through NeoForge fluid transfer and craft filled buckets from an empty bucket.\n''' + "'''" + '''\n\n[[mixins]]\nconfig="fluidbucketcrafting.mixins.json"\n\n[[dependencies.fluidbucketcrafting]]\nmodId="minecraft"\ntype="required"\nversionRange="[26.1.2]"\nordering="NONE"\nside="BOTH"\n\n[[dependencies.fluidbucketcrafting]]\nmodId="neoforge"\ntype="required"\nversionRange="[26.1.2.95,)"\nordering="NONE"\nside="BOTH"\n''', encoding='utf-8')

(res_root / 'fluidbucketcrafting.mixins.json').write_text('''{\n  "required": true,\n  "minVersion": "0.8",\n  "package": "com.jeancedraz.fluidbucketcrafting.mixin",\n  "mixins": [\n    "ResultSlotMixin"\n  ],\n  "injectors": {\n    "defaultRequire": 1\n  }\n}\n''', encoding='utf-8')

assets = res_root / 'assets/fluidbucketcrafting/lang'
assets.mkdir(parents=True, exist_ok=True)
(assets / 'en_us.json').write_text('{"modmenu.descriptionTranslation.fluidbucketcrafting":"Craft buckets using real fluid input."}\n', encoding='utf-8')
(assets / 'pt_br.json').write_text('{"modmenu.descriptionTranslation.fluidbucketcrafting":"Crie baldes usando fluido real como entrada."}\n', encoding='utf-8')

(root / 'README.md').write_text('''# Fluid Bucket Crafting\n\nMinecraft 26.1.2 / NeoForge 26.1.2.95\n\n- Adds a 1000 mB fluid capability to vanilla crafting tables and compatible modded crafting tables.\n- Only water and lava are accepted.\n- 1000 mB water + empty bucket -> water bucket.\n- 1000 mB lava + empty bucket -> lava bucket.\n- Fluid can be inserted/extracted by NeoForge-compatible pipes and fluid handlers.\n- Modded tables using the standard CraftingMenu are auto-discovered when opened.\n''', encoding='utf-8')

print('Generated Fluid Bucket Crafting project at', root)

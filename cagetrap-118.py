from pathlib import Path
import re

root = Path('CageTrapProjectV4')
java = root / 'src/main/java/com/jeancedraz/cagetrap'
client = java / 'client'

# Version 1.1.8
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.7['\"]", "version = '1.1.8'", s, count=1)
if n != 1:
    raise SystemExit('1.1.7 version not found')
p.write_text(s, encoding='utf-8')

# Register client render hooks directly on the mod event bus. RegisterItemDecorationsEvent
# is an IModBusEvent, so this avoids relying on subscriber discovery for the badge.
(client / 'CageTrapClient.java').write_text(r'''package com.jeancedraz.cagetrap.client;

import com.jeancedraz.cagetrap.CageTrap;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;
import net.neoforged.neoforge.client.event.RegisterItemDecorationsEvent;

@Mod(value = CageTrap.MOD_ID, dist = Dist.CLIENT)
public final class CageTrapClient {
    public CageTrapClient(IEventBus modBus, ModContainer container) {
        modBus.addListener(CageTrapClient::registerRenderers);
        modBus.addListener(CageTrapClient::registerItemDecorations);
    }

    private static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
        event.registerBlockEntityRenderer(CageTrap.CAGE_TRAP_BLOCK_ENTITY.get(), CageTrapBlockEntityRenderer::new);
    }

    private static void registerItemDecorations(RegisterItemDecorationsEvent event) {
        event.register(CageTrap.CAGE_TRAP_ITEM.get(), new CageTrapItemDecorator());
    }
}
''', encoding='utf-8')

# Smaller, less intrusive mob portrait badge. It remains in the upper-right corner,
# but is reduced from ~9x9 to 7x7 pixels.
(client / 'CageTrapItemDecorator.java').write_text(r'''package com.jeancedraz.cagetrap.client;

import com.jeancedraz.cagetrap.CageTrapItem;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.Vec3;
import net.neoforged.neoforge.client.IItemDecorator;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public final class CageTrapItemDecorator implements IItemDecorator {
    private static final Map<Integer, LivingEntity> CACHE = new HashMap<>();

    @Override
    public boolean render(GuiGraphicsExtractor graphics, Font font, ItemStack stack, int xOffset, int yOffset) {
        CompoundTag captured = CageTrapItem.getCapturedEntity(stack);
        if (captured == null || captured.isEmpty()) return false;

        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft.level == null) return false;

        int key = captured.hashCode();
        LivingEntity living = CACHE.get(key);
        if (living == null || living.level() != minecraft.level) {
            try {
                Entity entity = EntityType.loadEntityRecursive(
                        captured.copy(), minecraft.level, EntitySpawnReason.LOAD,
                        loaded -> {
                            loaded.setUUID(UUID.randomUUID());
                            loaded.absSnapTo(0.0D, 0.0D, 0.0D, 180.0F, 0.0F);
                            loaded.setDeltaMovement(Vec3.ZERO);
                            return loaded;
                        });
                if (!(entity instanceof LivingEntity loadedLiving)) return false;
                living = loadedLiving;
                CACHE.put(key, living);
            } catch (RuntimeException ignored) {
                return false;
            }
        }

        living.tickCount = 0;
        living.setDeltaMovement(Vec3.ZERO);
        living.setYRot(180.0F);
        living.setXRot(0.0F);
        living.setYHeadRot(180.0F);
        living.yHeadRotO = 180.0F;

        // Compact 7x7 portrait in the upper-right corner of the 16x16 item.
        int x0 = xOffset + 9;
        int y0 = yOffset;
        int x1 = xOffset + 16;
        int y1 = yOffset + 7;
        graphics.fill(x0 - 1, y0, x1, y1 + 1, 0xB8000000);
        graphics.fill(x0, y0 + 1, x1 - 1, y1, 0x8A173039);

        // Overscale the entity inside the tiny viewport so the head/face is what
        // remains readable instead of the full body.
        InventoryScreen.renderEntityInInventoryFollowsAngle(
                graphics,
                x0, y0, x1, y1,
                13,
                0.0F,
                0.0F,
                0.0F,
                living);

        // The entity helper participates in GUI extraction/render state; ask NeoForge
        // to reset state before another decorator runs.
        return true;
    }
}
''', encoding='utf-8')

sig = root/'src/main/resources/META-INF/JEAN_CEDRAZ.SIGNATURE'
if sig.exists():
    text = sig.read_text(encoding='utf-8')
    text = re.sub(r'Build line: 1\.1\.\d+', 'Build line: 1.1.8', text)
    sig.write_text(text, encoding='utf-8')

print('Cage Trap 1.1.8: direct mod-bus item decorator registration + smaller mob badge')

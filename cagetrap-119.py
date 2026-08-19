from pathlib import Path
import re

root = Path('CageTrapProjectV4')
java = root / 'src/main/java/com/jeancedraz/cagetrap'
client = java / 'client'

# Version 1.1.9
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.8['\"]", "version = '1.1.9'", s, count=1)
if n != 1:
    raise SystemExit('1.1.8 version not found')
p.write_text(s, encoding='utf-8')

# 1.1.8 proved the decorator itself is registered (the badge frame is visible),
# so 1.1.9 focuses specifically on the entity render. Instead of forcing the
# whole mob into a tiny 7x7 render viewport, render it in a larger virtual
# viewport and clip that output to the 7x7 badge. This keeps the approved badge
# size while giving InventoryScreen enough room to generate a visible entity.
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

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public final class CageTrapItemDecorator implements IItemDecorator {
    private static final int MAX_CACHE = 48;
    private static final Map<Integer, LivingEntity> CACHE = new LinkedHashMap<>();

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
                if (CACHE.size() >= MAX_CACHE) {
                    Integer first = CACHE.keySet().iterator().next();
                    CACHE.remove(first);
                }
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

        // Approved compact badge area: 7x7 pixels in the upper-right.
        int x0 = xOffset + 9;
        int y0 = yOffset;
        int x1 = xOffset + 16;
        int y1 = yOffset + 7;
        graphics.fill(x0 - 1, y0, x1, y1 + 1, 0xB8000000);
        graphics.fill(x0, y0 + 1, x1 - 1, y1, 0x8A173039);

        // The previous version used the same tiny rectangle as both viewport and
        // crop area, which could clip the entire entity render. NeoForge's own GUI
        // tests render entities in substantially larger rectangles. We now give the
        // entity a larger virtual viewport and scissor only the final badge area.
        graphics.enableScissor(x0, y0, x1, y1);
        try {
            int renderSize = 14;
            InventoryScreen.renderEntityInInventoryFollowsAngle(
                    graphics,
                    x0 - 8, y0 - 6,
                    x1 + 8, y1 + 20,
                    renderSize,
                    0.0F,
                    0.0F,
                    0.0F,
                    living);
        } finally {
            graphics.disableScissor();
        }

        return true;
    }
}
''', encoding='utf-8')

sig = root/'src/main/resources/META-INF/JEAN_CEDRAZ.SIGNATURE'
if sig.exists():
    text = sig.read_text(encoding='utf-8')
    text = re.sub(r'Build line: 1\.1\.\d+', 'Build line: 1.1.9', text)
    sig.write_text(text, encoding='utf-8')

print('Cage Trap 1.1.9: clipped virtual viewport portrait rendering')

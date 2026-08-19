from pathlib import Path
import re

root = Path('CageTrapProjectV4')
java = root / 'src/main/java/com/jeancedraz/cagetrap'
client = java / 'client'

# Version 1.1.7
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.6['\"]", "version = '1.1.7'", s, count=1)
if n != 1:
    raise SystemExit('1.1.6 version not found')
p.write_text(s, encoding='utf-8')

# Empty traps stack to 64 by default.
p = java / 'CageTrap.java'
s = p.read_text(encoding='utf-8')
s = s.replace('properties -> properties.stacksTo(1)', 'properties -> properties.stacksTo(64)', 1)
p.write_text(s, encoding='utf-8')

# Occupied traps explicitly become non-stackable via the per-stack component.
p = java / 'CageTrapItem.java'
s = p.read_text(encoding='utf-8')
needle = '''        stack.set(DataComponents.CUSTOM_DATA, CustomData.of(root));
        stack.set(DataComponents.ITEM_MODEL, FILLED_MODEL);'''
repl = '''        stack.set(DataComponents.CUSTOM_DATA, CustomData.of(root));
        stack.set(DataComponents.ITEM_MODEL, FILLED_MODEL);
        // Empty traps use the item's normal 64 stack size. A captured entity makes
        // this individual stack unique and strictly non-stackable.
        stack.set(DataComponents.MAX_STACK_SIZE, 1);'''
if needle not in s:
    raise SystemExit('CageTrapItem capture anchor not found')
s = s.replace(needle, repl, 1)
p.write_text(s, encoding='utf-8')

# Client-side inventory decoration: render a cropped miniature of the captured
# entity in the upper-right corner. The tiny viewport and oversized entity scale
# intentionally crop the body so the face/head dominates the badge.
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

        // Dark micro-frame behind the portrait, upper-right of the 16x16 item.
        int x0 = xOffset + 8;
        int y0 = yOffset - 1;
        int x1 = xOffset + 17;
        int y1 = yOffset + 8;
        graphics.fill(x0 - 1, y0 - 1, x1 + 1, y1 + 1, 0xB8000000);
        graphics.fill(x0, y0, x1, y1, 0x7A173039);

        // Rendering into a tiny viewport with a deliberately large scale crops the
        // model to the upper body/head, producing a readable mob portrait badge.
        InventoryScreen.renderEntityInInventoryFollowsAngle(
                graphics,
                x0, y0, x1, y1,
                18,
                0.0F,
                0.0F,
                0.0F,
                living);
        return false;
    }
}
''', encoding='utf-8')

# Register the item decoration in the existing client event subscriber.
p = client / 'CageTrapClient.java'
s = p.read_text(encoding='utf-8')
if 'RegisterItemDecorationsEvent' not in s:
    s = s.replace('import net.neoforged.neoforge.client.event.EntityRenderersEvent;\n',
                  'import net.neoforged.neoforge.client.event.EntityRenderersEvent;\nimport net.neoforged.neoforge.client.event.RegisterItemDecorationsEvent;\n')
anchor = '''        @SubscribeEvent
        public static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
            event.registerBlockEntityRenderer(CageTrap.CAGE_TRAP_BLOCK_ENTITY.get(), CageTrapBlockEntityRenderer::new);
        }
'''
addition = anchor + '''
        @SubscribeEvent
        public static void registerItemDecorations(RegisterItemDecorationsEvent event) {
            event.register(CageTrap.CAGE_TRAP_ITEM.get(), new CageTrapItemDecorator());
        }
'''
if anchor not in s:
    raise SystemExit('CageTrapClient renderer anchor not found')
s = s.replace(anchor, addition, 1)
p.write_text(s, encoding='utf-8')

# Signature bump when present.
sig = root/'src/main/resources/META-INF/JEAN_CEDRAZ.SIGNATURE'
if sig.exists():
    text = sig.read_text(encoding='utf-8')
    text = re.sub(r'Build line: 1\.1\.\d+', 'Build line: 1.1.7', text)
    sig.write_text(text, encoding='utf-8')

print('Cage Trap 1.1.7: empty stack 64 + occupied mob portrait overlay')

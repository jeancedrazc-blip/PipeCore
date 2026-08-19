from pathlib import Path
import re

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'

# -----------------------------------------------------------------------------
# 1) Text fields own keyboard input while focused.
#    Prevent the inventory key (E) and other gameplay hotkeys from closing or
#    acting on the screen while the user is typing.
# -----------------------------------------------------------------------------
for name, field_expr in [('BuilderScreen.java', 'fields'), ('QuarryFilterScreen.java', 'tagBox')]:
    p = client / name
    s = p.read_text(encoding='utf-8')
    if 'import net.minecraft.client.input.KeyEvent;' not in s:
        s = s.replace('import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;\n',
                      'import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;\nimport net.minecraft.client.input.KeyEvent;\n')
    if 'import org.lwjgl.glfw.GLFW;' not in s:
        s = s.replace('package mcjty.rftoolsbuilder.client;\n\n',
                      'package mcjty.rftoolsbuilder.client;\n\nimport org.lwjgl.glfw.GLFW;\n')

    if name == 'BuilderScreen.java':
        method = '''    @Override\n    public boolean keyPressed(KeyEvent event) {\n        for (EditBox field : fields) {\n            if (field != null && field.isFocused()) {\n                if (field.keyPressed(event)) return true;\n                // Same principle used by modern AE2 text fields: while typing,\n                // swallow gameplay hotkeys so E does not close the GUI.\n                if (event.key() != GLFW.GLFW_KEY_TAB && event.key() != GLFW.GLFW_KEY_ESCAPE) return true;\n                break;\n            }\n        }\n        return super.keyPressed(event);\n    }\n\n'''
    else:
        method = '''    @Override\n    public boolean keyPressed(KeyEvent event) {\n        if (tagBox != null && tagBox.isFocused()) {\n            if (tagBox.keyPressed(event)) return true;\n            if (event.key() != GLFW.GLFW_KEY_TAB && event.key() != GLFW.GLFW_KEY_ESCAPE) return true;\n        }\n        return super.keyPressed(event);\n    }\n\n'''

    anchor = '    @Override\n    protected void extractLabels('
    if anchor not in s:
        raise SystemExit(f'extractLabels anchor not found in {name}')
    if 'public boolean keyPressed(KeyEvent event)' not in s:
        s = s.replace(anchor, method + anchor, 1)
    p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 2) Synchronize a lightweight snapshot of the Builder BE to clients often
#    enough for the hologram to follow the current scan position.
# -----------------------------------------------------------------------------
p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')

imports = [
    'import net.minecraft.core.HolderLookup;',
    'import net.minecraft.nbt.CompoundTag;',
    'import net.minecraft.network.protocol.Packet;',
    'import net.minecraft.network.protocol.game.ClientGamePacketListener;',
    'import net.minecraft.network.protocol.game.ClientboundBlockEntityDataPacket;'
]
for imp in imports:
    if imp not in s:
        s = s.replace('package mcjty.rftoolsbuilder;\n\n', 'package mcjty.rftoolsbuilder;\n\n' + imp + '\n', 1)

m = re.search(r'(?m)^\s*private int status(?:\s*=\s*STATUS_IDLE)?;\s*$', s)
if not m:
    raise SystemExit('status field not found')
if 'private int hologramSyncTicker;' not in s:
    s = s[:m.end()] + '\n    private int hologramSyncTicker;' + s[m.end():]

needle = '        if (level.isClientSide()) return;\n'
if needle not in s:
    raise SystemExit('server tick guard not found')
if 'hologramSyncTicker >= 10' not in s:
    s = s.replace(needle, needle + '''        // 2 updates/second is enough for the display without spamming BE packets.\n        if (++builder.hologramSyncTicker >= 10) {\n            builder.hologramSyncTicker = 0;\n            builder.syncClientState();\n        }\n''', 1)

anchor = '    public void dropContents() {'
if anchor not in s:
    raise SystemExit('dropContents anchor not found')
if 'public BlockPos hologramTarget()' not in s:
    methods = '''    public boolean hologramVisible() {\n        return hasShapeCard() && hasQuarryCard();\n    }\n\n    public int hologramStatus() {\n        return status;\n    }\n\n    public BlockPos hologramTarget() {\n        long v = volume();\n        if (v <= 0L) return worldPosition;\n        long index = Math.max(0L, Math.min(cursor, v - 1L));\n        return positionFor(index);\n    }\n\n    public int hologramProgressPermille() {\n        long v = Math.max(1L, volume());\n        return (int) (1000L * Math.min(cursor, v) / v);\n    }\n\n    private void syncClientState() {\n        if (level != null) {\n            BlockState state = getBlockState();\n            level.sendBlockUpdated(worldPosition, state, state, 2);\n        }\n    }\n\n    @Override\n    public CompoundTag getUpdateTag(HolderLookup.Provider registries) {\n        return saveWithoutMetadata(registries);\n    }\n\n    @Override\n    public Packet<ClientGamePacketListener> getUpdatePacket() {\n        return ClientboundBlockEntityDataPacket.create(this);\n    }\n\n'''
    s = s.replace(anchor, methods + anchor, 1)
p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 3) Holographic status panel projected from the Builder's FRONT face.
#    The block already has HORIZONTAL_FACING, so the display follows placement.
# -----------------------------------------------------------------------------
(client / 'QuantumBuilderRenderState.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import net.minecraft.client.renderer.blockentity.state.BlockEntityRenderState;
import net.minecraft.core.Direction;

public final class QuantumBuilderRenderState extends BlockEntityRenderState {
    public boolean visible;
    public Direction facing = Direction.SOUTH;
    public int chunkX;
    public int chunkZ;
    public int progressPermille;
    public int status;
}
''', encoding='utf-8')

(client / 'QuantumBuilderBlockEntityRenderer.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import mcjty.rftoolsbuilder.BuilderBlockEntity;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.blockentity.BlockEntityRenderer;
import net.minecraft.client.renderer.blockentity.BlockEntityRendererProvider;
import net.minecraft.client.renderer.feature.ModelFeatureRenderer;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

import java.util.Locale;

public final class QuantumBuilderBlockEntityRenderer implements BlockEntityRenderer<BuilderBlockEntity, QuantumBuilderRenderState> {
    private static final int FULL_BRIGHT = 15728880;
    private static final int CYAN = 0xFF36E7F7;
    private static final int WHITE = 0xFFF0FCFF;
    private static final int MUTED = 0xFF8ED8E1;
    private static final int SCREEN_BG = 0x72030E14;

    private final Font font;

    public QuantumBuilderBlockEntityRenderer(BlockEntityRendererProvider.Context context) {
        this.font = context.font();
    }

    @Override
    public QuantumBuilderRenderState createRenderState() {
        return new QuantumBuilderRenderState();
    }

    @Override
    public void extractRenderState(BuilderBlockEntity blockEntity, QuantumBuilderRenderState state, float partialTicks,
                                   Vec3 cameraPosition, ModelFeatureRenderer.@Nullable CrumblingOverlay breakProgress) {
        BlockEntityRenderer.super.extractRenderState(blockEntity, state, partialTicks, cameraPosition, breakProgress);
        state.visible = blockEntity.hologramVisible();
        state.facing = blockEntity.getBlockState().getValue(BlockStateProperties.HORIZONTAL_FACING);
        BlockPos target = blockEntity.hologramTarget();
        state.chunkX = target.getX() >> 4;
        state.chunkZ = target.getZ() >> 4;
        state.progressPermille = blockEntity.hologramProgressPermille();
        state.status = blockEntity.hologramStatus();
    }

    @Override
    public void submit(QuantumBuilderRenderState state, PoseStack poseStack, SubmitNodeCollector collector,
                       CameraRenderState cameraRenderState) {
        if (!state.visible) return;

        poseStack.pushPose();
        placeOnFront(poseStack, state.facing);
        poseStack.scale(0.0125F, 0.0125F, 0.0125F);

        String title = "  QUANTUM SCAN  ";
        String chunk = " CHUNK " + state.chunkX + " / " + state.chunkZ + " ";
        String progress = statusName(state.status) + "  " + String.format(Locale.ROOT, "%.1f%%", state.progressPermille / 10.0F);

        drawLine(collector, poseStack, title, -13.0F, CYAN);
        drawLine(collector, poseStack, chunk, -3.0F, WHITE);
        drawLine(collector, poseStack, progress, 7.0F, state.status == BuilderBlockEntity.STATUS_RUNNING ? CYAN : MUTED);

        poseStack.popPose();
    }

    private void placeOnFront(PoseStack poseStack, Direction facing) {
        switch (facing) {
            case NORTH -> {
                poseStack.translate(0.5D, 0.78D, -0.12D);
                poseStack.mulPose(Axis.YP.rotationDegrees(180.0F));
            }
            case SOUTH -> poseStack.translate(0.5D, 0.78D, 1.12D);
            case WEST -> {
                poseStack.translate(-0.12D, 0.78D, 0.5D);
                poseStack.mulPose(Axis.YP.rotationDegrees(90.0F));
            }
            case EAST -> {
                poseStack.translate(1.12D, 0.78D, 0.5D);
                poseStack.mulPose(Axis.YP.rotationDegrees(-90.0F));
            }
            default -> poseStack.translate(0.5D, 0.78D, 1.12D);
        }
    }

    private void drawLine(SubmitNodeCollector collector, PoseStack poseStack, String text, float y, int color) {
        float width = font.width(text);
        collector.submitText(
                poseStack,
                -width / 2.0F,
                y,
                Component.literal(text).getVisualOrderText(),
                false,
                Font.DisplayMode.SEE_THROUGH,
                FULL_BRIGHT,
                color,
                SCREEN_BG,
                0
        );
    }

    private static String statusName(int status) {
        return switch (status) {
            case BuilderBlockEntity.STATUS_RUNNING -> "MINING";
            case BuilderBlockEntity.STATUS_NO_ENERGY -> "NO FE";
            case BuilderBlockEntity.STATUS_OUTPUT_FULL -> "OUTPUT FULL";
            case BuilderBlockEntity.STATUS_DONE -> "COMPLETE";
            case BuilderBlockEntity.STATUS_NO_CARD -> "NO CARD";
            default -> "STANDBY";
        };
    }
}
''', encoding='utf-8')

# Rewrite the tiny client registration class so the new BER is registered safely client-side.
(client / 'RFToolsBuilderClient.java').write_text(r'''package mcjty.rftoolsbuilder.client;

import mcjty.rftoolsbuilder.RFToolsBuilder;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.client.event.EntityRenderersEvent;
import net.neoforged.neoforge.client.event.RegisterMenuScreensEvent;

@Mod(value = RFToolsBuilder.MOD_ID, dist = Dist.CLIENT)
public final class RFToolsBuilderClient {
    public RFToolsBuilderClient() { }

    @EventBusSubscriber(modid = RFToolsBuilder.MOD_ID, value = Dist.CLIENT)
    public static final class ClientEvents {
        @SubscribeEvent
        public static void registerScreens(RegisterMenuScreensEvent event) {
            event.register(RFToolsBuilder.BUILDER_MENU.get(), BuilderScreen::new);
            event.register(RFToolsBuilder.QUARRY_FILTER_MENU.get(), QuarryFilterScreen::new);
        }

        @SubscribeEvent
        public static void registerRenderers(EntityRenderersEvent.RegisterRenderers event) {
            event.registerBlockEntityRenderer(RFToolsBuilder.BUILDER_BLOCK_ENTITY.get(), QuantumBuilderBlockEntityRenderer::new);
        }
    }
}
''', encoding='utf-8')

# Version bump.
p = root / 'build.gradle'
s = p.read_text(encoding='utf-8')
s, n = re.subn(r"(?m)^version\s*=\s*['\"]3\.0\.1['\"]", "version = '3.0.2'", s, count=1)
if n != 1:
    raise SystemExit('3.0.1 version not found')
p.write_text(s, encoding='utf-8')

print('Quantum Tools 3.0.2: typing focus + front hologram applied')

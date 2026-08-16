from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")

# V15 fixes the remaining configurator problem at the correct interaction layer.
# In V14 the configurator was still a plain Item and all behavior depended on a
# RightClickBlock event. Sneak-use can bypass the block interaction path, so a
# dedicated Item#useOn implementation is more reliable and matches how a true
# configurator tool should behave.

# 1) Expose the existing localized mode label helper for the item feedback.
pipe_block = root / "src/main/java/com/pipecore/block/PipeBlock.java"
text = pipe_block.read_text(encoding="utf-8")
old = "    private static Component modeLabel(FaceMode mode) {"
new = "    public static Component modeLabel(FaceMode mode) {"
if old not in text:
    raise SystemExit("PipeBlock modeLabel pattern not found")
text = text.replace(old, new, 1)
pipe_block.write_text(text, encoding="utf-8")

# 2) Create a real Configurator item. Shift + right click is handled directly by
# Item#useOn. The clicked pipe arm is still resolved with PipeBlock.interactionFace,
# so corners and branches select the intended arm instead of just the block face.
item_dir = root / "src/main/java/com/pipecore/item"
item_dir.mkdir(parents=True, exist_ok=True)
(item_dir / "ConfiguratorItem.java").write_text('''package com.pipecore.item;

import com.pipecore.FaceMode;
import com.pipecore.block.PipeBlock;
import com.pipecore.block.PipeBlockEntity;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;

public final class ConfiguratorItem extends Item {
    public ConfiguratorItem(Properties properties) {
        super(properties);
    }

    @Override
    public InteractionResult useOn(UseOnContext context) {
        Player player = context.getPlayer();
        if (player == null || !player.isShiftKeyDown()) {
            return InteractionResult.PASS;
        }

        Level level = context.getLevel();
        BlockPos pos = context.getClickedPos();
        BlockState state = level.getBlockState(pos);
        if (!(state.getBlock() instanceof PipeBlock)) {
            return InteractionResult.PASS;
        }

        BlockEntity blockEntity = level.getBlockEntity(pos);
        if (!(blockEntity instanceof PipeBlockEntity pipe)) {
            return InteractionResult.PASS;
        }

        BlockHitResult hit = new BlockHitResult(
                context.getClickLocation(), context.getClickedFace(), pos, false);
        Direction face = PipeBlock.interactionFace(state, pos, hit);

        if (!level.isClientSide()) {
            FaceMode next = pipe.cycleFaceMode(face);
            player.sendSystemMessage(
                    Component.translatable("message.pipecore.face_mode",
                            face.getName(), PipeBlock.modeLabel(next)));
        }

        return InteractionResult.SUCCESS;
    }
}
''', encoding="utf-8")

# 3) Register ConfiguratorItem instead of a generic Item and disable the V14 event
# interceptor to guarantee exactly one state change per click.
pipe_core = root / "src/main/java/com/pipecore/PipeCore.java"
text = pipe_core.read_text(encoding="utf-8")
text = text.replace("import com.pipecore.event.PipeInteractionEvents;\n", "")
text = text.replace("import net.neoforged.neoforge.common.NeoForge;\n", "")
if "import com.pipecore.item.ConfiguratorItem;" not in text:
    text = text.replace("import com.pipecore.block.PipeBlockEntity;\n",
                        "import com.pipecore.block.PipeBlockEntity;\nimport com.pipecore.item.ConfiguratorItem;\n", 1)
old = '    public static final DeferredItem<Item> CONFIGURATOR = item("configurator", 1);'
new = '    public static final DeferredItem<ConfiguratorItem> CONFIGURATOR = ITEMS.registerItem("configurator", props -> new ConfiguratorItem(props.stacksTo(1)));'
if old not in text:
    raise SystemExit("PipeCore CONFIGURATOR registration pattern not found")
text = text.replace(old, new, 1)
text = text.replace("        NeoForge.EVENT_BUS.register(new PipeInteractionEvents());\n", "")
pipe_core.write_text(text, encoding="utf-8")

# 4) Version bump.
props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.11" not in p:
    raise SystemExit("Expected mod_version=1.3.11 before V15 hotfix")
props.write_text(p.replace("mod_version=1.3.11", "mod_version=1.3.12", 1), encoding="utf-8")

print("Applied Pipe Core V15: dedicated ConfiguratorItem.useOn, one authoritative state cycle per click, version 1.3.12")

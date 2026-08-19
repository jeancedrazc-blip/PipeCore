from pathlib import Path

p = Path('RFToolsBuilderPort261/src/main/java/mcjty/rftoolsbuilder/QuarryCardItem.java')
s = p.read_text(encoding='utf-8')

if 'import net.minecraft.util.ProblemReporter;' not in s:
    s = s.replace(
        'import net.minecraft.server.level.ServerPlayer;\n',
        'import net.minecraft.server.level.ServerPlayer;\nimport net.minecraft.util.ProblemReporter;\nimport net.minecraft.world.level.storage.TagValueInput;\nimport net.minecraft.world.level.storage.TagValueOutput;\n',
        1
    )

s = s.replace(
    '        return ItemStack.parseOptional(registries, tag);',
    '        var input = TagValueInput.create(ProblemReporter.DISCARDING, registries, tag);\n        return input.read("Stack", ItemStack.CODEC).orElse(ItemStack.EMPTY);',
    1
)

old = '        CompoundTag r=root(card); r.put(ITEM_PREFIX+count, normalized.saveOptional(registries)); r.putBoolean(ITEM_BLACK_PREFIX+count, blacklist); r.putInt(ITEM_COUNT,count+1); saveRoot(card,r); return true;'
new = '''        CompoundTag r=root(card);
        TagValueOutput output = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, registries);
        output.store("Stack", ItemStack.CODEC, normalized);
        r.put(ITEM_PREFIX+count, output.buildResult());
        r.putBoolean(ITEM_BLACK_PREFIX+count, blacklist);
        r.putInt(ITEM_COUNT,count+1);
        saveRoot(card,r);
        return true;'''
if old not in s:
    raise SystemExit('3.0.5 item persistence anchor not found')
s = s.replace(old, new, 1)
s = s.replace('source.getItemHolder().tags().forEach(tag -> {', 'source.typeHolder().tags().forEach(tag -> {', 1)

p.write_text(s, encoding='utf-8')
print('Quantum Tools 3.0.5 26.1 item codec APIs fixed')

from pathlib import Path
p = Path('RFToolsBuilderPort261/src/main/java/mcjty/rftoolsbuilder/ShapeCardItem.java')
s = p.read_text(encoding='utf-8')
s = s.replace(
'''        CustomData data = stack.getOrDefault(DataComponents.CUSTOM_DATA, CustomData.EMPTY);
        CompoundTag tag = data.copyTag();
        return tag.getInt(KEYS[field]).orElse(DEFAULTS[field]);''',
'''        CustomData data = stack.get(DataComponents.CUSTOM_DATA);
        if (data == null) return DEFAULTS[field];
        CompoundTag tag = data.copyTag();
        return tag.getInt(KEYS[field]).orElse(DEFAULTS[field]);''')
s = s.replace(
'''        CustomData.update(DataComponents.CUSTOM_DATA, stack, tag -> tag.putInt(KEYS[field], value));''',
'''        // CustomData.update intentionally avoided here; this mirrors the proven Cage Trap 26.1 pattern.
        CustomData existing = stack.get(DataComponents.CUSTOM_DATA);
        CompoundTag root = existing == null ? new CompoundTag() : existing.copyTag();
        root.putInt(KEYS[field], value);
        stack.set(DataComponents.CUSTOM_DATA, CustomData.of(root));''')
p.write_text(s, encoding='utf-8')
print('Shape Card CustomData migrated to proven Cage Trap pattern')

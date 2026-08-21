from pathlib import Path
import re

root = Path('RFToolsBuilderPort261/src/main/java/mcjty/rftoolsbuilder')

# --- QuarryCardItem: 26.1 codec persistence + Holder API --------------------
p = root / 'QuarryCardItem.java'
s = p.read_text(encoding='utf-8')
s = s.replace('import net.minecraft.server.level.ServerPlayer;\n', 'import net.minecraft.server.level.ServerPlayer;\nimport net.minecraft.util.ProblemReporter;\nimport net.minecraft.world.level.storage.TagValueInput;\nimport net.minecraft.world.level.storage.TagValueOutput;\n')
s = s.replace(
'''        CompoundTag tag = r.getCompound(ITEM_PREFIX + index).orElse(null);
        if (tag == null) return ItemStack.EMPTY;
        return ItemStack.parseOptional(registries, tag);''',
'''        CompoundTag tag = r.getCompound(ITEM_PREFIX + index).orElse(null);
        if (tag == null) return ItemStack.EMPTY;
        var input = TagValueInput.create(ProblemReporter.DISCARDING, registries, tag);
        return input.read("Stack", ItemStack.CODEC).orElse(ItemStack.EMPTY);''')
s = s.replace(
'''        CompoundTag r = root(card);
        r.put(ITEM_PREFIX + count, normalized.saveOptional(registries));
        r.putInt(ITEM_COUNT, count + 1);''',
'''        CompoundTag r = root(card);
        TagValueOutput output = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, registries);
        output.store("Stack", ItemStack.CODEC, normalized);
        r.put(ITEM_PREFIX + count, output.buildResult());
        r.putInt(ITEM_COUNT, count + 1);''')
s = s.replace('source.getItemHolder().tags().forEach(tag -> {', 'source.typeHolder().tags().forEach(tag -> {')
p.write_text(s, encoding='utf-8')

# --- Menu: ClickType -> ContainerInput --------------------------------------
p = root / 'QuarryFilterMenu.java'
s = p.read_text(encoding='utf-8')
s = s.replace('import net.minecraft.world.inventory.ClickType;', 'import net.minecraft.world.inventory.ContainerInput;')
s = s.replace('ClickType clickType', 'ContainerInput clickType')
s = s.replace('ClickType.QUICK_MOVE', 'ContainerInput.QUICK_MOVE')
p.write_text(s, encoding='utf-8')

# --- Screen: don't use removed double,double,int mouse callback. ------------
p = root / 'client/QuarryFilterScreen.java'
s = p.read_text(encoding='utf-8')
s = s.replace('private EditBox tagBox;', 'private EditBox tagBox;\n    private final Button[] entryButtons = new Button[4];')
s = s.replace(
'''        super.init();
        modeButton = addRenderableWidget''',
'''        super.init();
        for (int i = 0; i < entryButtons.length; i++) {
            final int local = i;
            int col = i / 2;
            int row = i % 2;
            entryButtons[i] = addRenderableWidget(Button.builder(Component.empty(), b -> {
                int idx = page * 4 + local;
                if (idx < QuarryCardItem.entryCount(card())) selected = idx;
            }).bounds(leftPos + 8 + col * 85, topPos + 27 + row * 18, 81, 16).build());
        }
        modeButton = addRenderableWidget''')
s = s.replace('(page + 1) * 8 < QuarryCardItem.entryCount(card())', '(page + 1) * 4 < QuarryCardItem.entryCount(card())')
s = s.replace('int maxPage = Math.max(0, (count - 1) / 8);', 'int maxPage = Math.max(0, (count - 1) / 4);')
s = s.replace(
'''        if (removeButton != null) removeButton.active = selected >= 0;''',
'''        for (int i = 0; i < entryButtons.length; i++) {
            if (entryButtons[i] == null) continue;
            int combined = page * 4 + i;
            boolean present = combined < count;
            entryButtons[i].active = present;
            String label = present ? entryLabel(combined) : "empty";
            if (label.length() > 13) label = label.substring(0, 12) + "…";
            entryButtons[i].setMessage(Component.literal(label));
        }
        if (removeButton != null) removeButton.active = selected >= 0;''')
s, n = re.subn(r'''\n    @Override\n    public boolean mouseClicked\(double mouseX, double mouseY, int button\) \{.*?\n    \}\n\n    private String entryLabel''', '\n\n    private String entryLabel', s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('Obsolete mouseClicked block not found')
s = s.replace('int start = page * 8;', 'int start = page * 4;')
old_loop = r'''        for (int local = 0; local < 4; local++) {
            int combined = start + local;
            int col = local / 2, row = local % 2;
            int rx = x + 8 + col * 85, ry = y + 27 + row * 18;
            g.fill(rx, ry, rx + 81, ry + 16, combined == selected ? SELECTED : 0xFF0B1116);
            g.fill(rx, ry, rx + 1, ry + 16, combined == selected ? CYAN : BORDER);
            if (combined < count) {
                String label = entryLabel(combined);
                if (label.length() > 13) label = label.substring(0, 12) + "…";
                g.text(font, Component.literal(label), rx + 4, ry + 4, TEXT);
            } else g.text(font, Component.literal("empty"), rx + 4, ry + 4, MUTED);
        }'''
new_loop = r'''        for (int local = 0; local < 4; local++) {
            int combined = start + local;
            int col = local / 2, row = local % 2;
            int rx = x + 8 + col * 85, ry = y + 27 + row * 18;
            g.fill(rx - 1, ry - 1, rx + 82, ry + 17, combined == selected ? CYAN_DARK : BORDER);
        }'''
if old_loop not in s:
    raise SystemExit('Entry background loop not found')
s = s.replace(old_loop, new_loop)
p.write_text(s, encoding='utf-8')

print('Quantum APIs adapted for Minecraft 26.1.2')

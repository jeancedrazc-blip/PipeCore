from pathlib import Path

root = Path('RFToolsBuilderPort261')
client = root/'src/main/java/mcjty/rftoolsbuilder/client'

# Final spacing pass after the structural 3.0.3 rewrite.
p = client/'QuarryFilterScreen.java'
s = p.read_text(encoding='utf-8')
s = s.replace('private static final int VISIBLE_ROWS = 6;', 'private static final int VISIBLE_ROWS = 5;')
s = s.replace('.bounds(leftPos + 228, topPos + 72, 20, 18)', '.bounds(leftPos + 228, topPos + 82, 20, 18)')
s = s.replace('.bounds(leftPos + 228, topPos + 142, 20, 18)', '.bounds(leftPos + 228, topPos + 144, 20, 18)')
s = s.replace('ly >= 72 && ly < 168', 'ly >= 82 && ly < 162')
s = s.replace('int row = (ly - 72) / 16;', 'int row = (ly - 82) / 16;')
s = s.replace('int ry = y + 72 + row * 16;', 'int ry = y + 82 + row * 16;')
s = s.replace('g.text(font, Component.literal("FILTER LIST  " + count + "/18"), x + 10, y + 68, CYAN_DARK);',
              'g.text(font, Component.literal("FILTER LIST  " + count + "/18"), x + 10, y + 71, CYAN_DARK);')
s = s.replace('        g.text(font, Component.literal("Clique no item = exato  •  Shift-clique = tags"), x + 9, y + 198, MUTED);\n', '')
s = s.replace('g.text(font, Component.literal("INVENTORY"), x + 47, y + 199, CYAN_DARK);',
              'g.text(font, Component.literal("INVENTORY"), x + 47, y + 202, CYAN_DARK);')
p.write_text(s, encoding='utf-8')

p = client/'BuilderScreen.java'
s = p.read_text(encoding='utf-8')
s = s.replace('int sx = x + 45 + col * 18, sy = y + 146 + row * 18;',
              'int sx = x + 46 + col * 18, sy = y + 147 + row * 18;')
s = s.replace('int sx = x + 45 + col * 18, sy = y + 204;',
              'int sx = x + 46 + col * 18, sy = y + 205;')
p.write_text(s, encoding='utf-8')

# Minecraft 26.1 exposes ChunkPos coordinates through accessors, not public fields.
p = root/'src/main/java/mcjty/rftoolsbuilder/BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')
s = s.replace('getChunk(chunkPos.x, chunkPos.z, ChunkStatus.FULL, true)',
              'getChunk(chunkPos.x(), chunkPos.z(), ChunkStatus.FULL, true)')
p.write_text(s, encoding='utf-8')

print('Quantum Tools 3.0.3 final UI/API polish applied')

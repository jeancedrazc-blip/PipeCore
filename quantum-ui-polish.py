from pathlib import Path

p = Path('RFToolsBuilderPort261/src/main/java/mcjty/rftoolsbuilder/client/BuilderScreen.java')
s = p.read_text(encoding='utf-8')

# More refined nested panels with a short cyan circuit accent.
old = '''    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, BORDER);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, PANEL);
    }'''
new = '''    private void panel(GuiGraphicsExtractor g, int x1, int y1, int x2, int y2) {
        g.fill(x1, y1, x2, y2, 0xFF05080B);
        g.fill(x1 + 1, y1 + 1, x2 - 1, y2 - 1, BORDER);
        g.fill(x1 + 2, y1 + 2, x2 - 2, y2 - 2, PANEL);
        int accentEnd = Math.min(x2 - 3, x1 + 16);
        g.fill(x1 + 3, y1 + 2, accentEnd, y1 + 3, CYAN_DARK);
    }'''
if old not in s: raise SystemExit('panel helper not found')
s = s.replace(old, new, 1)

# Add compact number formatting so the FE display never clips like in the screenshot.
anchor = '''    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {'''
helper = '''    private static String compact(long value) {
        if (value >= 1_000_000_000L) return String.format(java.util.Locale.ROOT, "%.1fB", value / 1_000_000_000.0);
        if (value >= 1_000_000L) return String.format(java.util.Locale.ROOT, "%.1fM", value / 1_000_000.0);
        if (value >= 1_000L) return String.format(java.util.Locale.ROOT, "%.1fK", value / 1_000.0);
        return Long.toString(value);
    }

    @Override
    public void extractBackground(GuiGraphicsExtractor g, int mouseX, int mouseY, float partialTick) {'''
if anchor not in s: raise SystemExit('extractBackground anchor not found')
s = s.replace(anchor, helper, 1)
s = s.replace('g.text(font, Component.literal(Integer.toString(energy)), x + 27, y + 56, CYAN);', 'g.text(font, Component.literal(compact(energy)), x + 27, y + 56, CYAN);')

# Card labels become proper in-panel micro headers rather than floating over the panel.
s = s.replace('g.text(font, Component.literal("SHAPE"), x + 58, y + 17, MUTED);', 'g.text(font, Component.literal("SHAPE"), x + 58, y + 24, CYAN_DARK);')
s = s.replace('g.text(font, Component.literal("QUARRY"), x + 96, y + 17, MUTED);', 'g.text(font, Component.literal("QUARRY"), x + 96, y + 24, CYAN_DARK);')

# Add a compact scan counter under the progress bar.
needle = 'g.fill(x + 150, y + 64, x + 150 + pw, y + 69, CYAN);'
repl = needle + '\n        g.text(font, Component.literal(compact(Math.min(cursor, volume)) + " / " + compact(volume)), x + 150, y + 70, MUTED);'
if needle not in s: raise SystemExit('progress bar anchor not found')
s = s.replace(needle, repl, 1)

# Stronger top identity line and tiny orange operational accent.
needle = 'g.centeredText(font, Component.literal("QUANTUM BUILDER"), x + imageWidth / 2, y + 8, TEXT);'
if needle in s:
    repl = needle + '\n        g.fill(x + imageWidth / 2 - 34, y + 18, x + imageWidth / 2 + 34, y + 19, CYAN_DARK);\n        g.fill(x + imageWidth / 2 + 35, y + 18, x + imageWidth / 2 + 44, y + 19, ORANGE);'
    s = s.replace(needle, repl, 1)

p.write_text(s, encoding='utf-8')
print('Quantum Builder UI polish applied')

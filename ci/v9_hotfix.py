from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")

pipe_block = root / "src/main/java/com/pipecore/block/PipeBlock.java"
text = pipe_block.read_text(encoding="utf-8")
old = """        // The Configurator always takes priority. A normal right-click cycles the clicked face.\n        if (stack.getItem() == PipeCore.CONFIGURATOR.get()) {\n"""
new = """        // Pipe Core rule: the Configurator only changes a pipe face while Shift is held.\n        if (stack.getItem() == PipeCore.CONFIGURATOR.get() && player.isShiftKeyDown()) {\n"""
if old not in text:
    raise SystemExit("Expected V8 Configurator interaction pattern not found")
text = text.replace(old, new, 1)
text = text.replace(
    "// Output UI is a normal right-click when the Configurator is not being used.",
    "// Output UI remains a normal right-click; configuration is Shift + Configurator only.",
    1,
)
pipe_block.write_text(text, encoding="utf-8")

props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.5" not in p:
    raise SystemExit("Expected mod_version=1.3.5 before V9 hotfix")
props.write_text(p.replace("mod_version=1.3.5", "mod_version=1.3.6", 1), encoding="utf-8")

print("Applied Pipe Core V9 hotfix: Configurator is Shift-only + version 1.3.6")

from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")

pipe_block = root / "src/main/java/com/pipecore/block/PipeBlock.java"
text = pipe_block.read_text(encoding="utf-8")
old = """        // Configuration is deliberately Shift + Configurator only.\n        if (stack.getItem() == PipeCore.CONFIGURATOR.get() && player.isShiftKeyDown()) {\n"""
new = """        // The Configurator always takes priority. A normal right-click cycles the clicked face.\n        if (stack.getItem() == PipeCore.CONFIGURATOR.get()) {\n"""
if old not in text:
    raise SystemExit("Configurator interaction pattern not found; refusing to patch blindly")
text = text.replace(old, new, 1)
text = text.replace(
    "// Output UI is a normal right-click. No Configurator and no Shift are required.",
    "// Output UI is a normal right-click when the Configurator is not being used.",
    1,
)
pipe_block.write_text(text, encoding="utf-8")

props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.4" not in p:
    raise SystemExit("Expected mod_version=1.3.4 before V8 hotfix")
props.write_text(p.replace("mod_version=1.3.4", "mod_version=1.3.5", 1), encoding="utf-8")

print("Applied Pipe Core V8 hotfix: Configurator normal right-click + version 1.3.5")

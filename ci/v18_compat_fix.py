from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")
p = root / "src/main/java/com/pipecore/block/PipeBlockEntity.java"
s = p.read_text(encoding="utf-8")

old_save = '''                if (normalFilterBlacklist[i][slot]) {
                    output.putBoolean("normal_filter_black_" + i + "_" + slot, true);
                }
'''
new_save = '''                if (!normalFilterItemIds[i][slot].isEmpty()) {
                    // Persist both W and B explicitly. This lets a legacy global-blacklist
                    // world migrate once without forcing a later white rule back to black.
                    output.putBoolean("normal_filter_black_" + i + "_" + slot, normalFilterBlacklist[i][slot]);
                }
'''
if old_save not in s:
    raise SystemExit("V18 compat normal save anchor not found")
s = s.replace(old_save, new_save, 1)

old_load = '''                normalFilterBlacklist[i][slot] = input.getBooleanOr("normal_filter_black_" + i + "_" + slot, false);
'''
new_load = '''                // V17 had one global mode and only nine normal filter entries.
                // Use it only as the fallback for those legacy slots. V18 saves an
                // explicit per-rule boolean from then on.
                normalFilterBlacklist[i][slot] = input.getBooleanOr(
                        "normal_filter_black_" + i + "_" + slot,
                        slot < 9 && filterBlacklist[i]);
'''
if old_load not in s:
    raise SystemExit("V18 compat normal load anchor not found")
s = s.replace(old_load, new_load, 1)

p.write_text(s, encoding="utf-8")
print("Applied V18 compatibility fix: preserve V17 global W/B mode across per-rule migration")

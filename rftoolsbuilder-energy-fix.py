from pathlib import Path

# Shape Card uses the exact CUSTOM_DATA pattern already proven by Cage Trap on 26.1.2.
shape_fix = Path('rftoolsbuilder-shapecard-data-fix.py')
if shape_fix.is_file():
    exec(compile(shape_fix.read_text(encoding='utf-8'), str(shape_fix), 'exec'))

p = Path('RFToolsBuilderPort261/src/main/java/mcjty/rftoolsbuilder/BuilderBlockEntity.java')
s = p.read_text(encoding='utf-8')

s = s.replace(
    'import net.neoforged.neoforge.energy.EnergyStorage;\n',
    'import net.neoforged.neoforge.transfer.energy.SimpleEnergyHandler;\n'
    'import net.neoforged.neoforge.transfer.transaction.Transaction;\n'
)
s = s.replace('public EnergyStorage energyStorage()', 'public BuilderEnergyStorage energyStorage()')
s = s.replace('extends EnergyStorage', 'extends SimpleEnergyHandler')

marker = 'private static final class BuilderEnergyStorage extends SimpleEnergyHandler {'
if marker not in s:
    raise SystemExit('BuilderEnergyStorage marker not found after API migration')

compat = marker + '''\n        public int getEnergyStored() {\n            return (int) getAmountAsLong();\n        }\n\n        public int getMaxEnergyStored() {\n            return (int) getCapacityAsLong();\n        }\n\n        public int receiveEnergy(int amount, boolean simulate) {\n            try (Transaction tx = Transaction.openRoot()) {\n                int moved = insert(amount, tx);\n                if (!simulate) {\n                    tx.commit();\n                }\n                return moved;\n            }\n        }\n\n        public int extractEnergy(int amount, boolean simulate) {\n            try (Transaction tx = Transaction.openRoot()) {\n                int moved = extract(amount, tx);\n                if (!simulate) {\n                    tx.commit();\n                }\n                return moved;\n            }\n        }\n'''

s = s.replace(marker, compat, 1)
p.write_text(s, encoding='utf-8')
print('Migrated Builder energy storage to NeoForge 26.1 SimpleEnergyHandler')

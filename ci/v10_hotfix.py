from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")

# --- Energy transport: use NeoForge's official transactional mover and sided/unsided fallback. ---
entity_file = root / "src/main/java/com/pipecore/block/PipeBlockEntity.java"
text = entity_file.read_text(encoding="utf-8")

energy_import = "import net.neoforged.neoforge.transfer.energy.EnergyHandler;\n"
if "import net.neoforged.neoforge.transfer.energy.EnergyHandlerUtil;" not in text:
    if energy_import not in text:
        raise SystemExit("EnergyHandler import not found")
    text = text.replace(
        energy_import,
        energy_import + "import net.neoforged.neoforge.transfer.energy.EnergyHandlerUtil;\n",
        1,
    )

old_energy_connect = "            case ENERGY -> level.getCapability(Capabilities.Energy.BLOCK, neighborPos, side) != null;"
new_energy_connect = "            case ENERGY -> energyHandler(level, neighborPos, side) != null;"
if old_energy_connect not in text:
    raise SystemExit("Energy connection check pattern not found")
text = text.replace(old_energy_connect, new_energy_connect, 1)

old_chemical_connect = "            case CHEMICAL -> !level.getBlockState(neighborPos).isAir();"
new_chemical_connect = "            case CHEMICAL -> ChemicalTransportRegistry.canConnect(level, neighborPos, side);"
if old_chemical_connect not in text:
    raise SystemExit("Chemical connection check pattern not found")
text = text.replace(old_chemical_connect, new_chemical_connect, 1)

helper_anchor = "    private void syncVisualState(Level level, boolean force) {"
energy_helper = """    private static EnergyHandler energyHandler(Level level, BlockPos pos, Direction side) {\n        EnergyHandler handler = level.getCapability(Capabilities.Energy.BLOCK, pos, side);\n        if (handler != null) return handler;\n        // Some blocks expose an unsided energy handler. Fall back to the null side for compatibility.\n        return level.getCapability(Capabilities.Energy.BLOCK, pos, null);\n    }\n\n"""
if energy_helper.strip() not in text:
    if helper_anchor not in text:
        raise SystemExit("syncVisualState anchor not found")
    text = text.replace(helper_anchor, energy_helper + helper_anchor, 1)

old_source = "        EnergyHandler source = level.getCapability(Capabilities.Energy.BLOCK, sourcePos, sourceFace.getOpposite());"
new_source = "        EnergyHandler source = energyHandler(level, sourcePos, sourceFace.getOpposite());"
if old_source not in text:
    raise SystemExit("Energy source lookup pattern not found")
text = text.replace(old_source, new_source, 1)

old_target = "                EnergyHandler target = level.getCapability(Capabilities.Energy.BLOCK, targetPos, targetSide.getOpposite());"
new_target = "                EnergyHandler target = energyHandler(level, targetPos, targetSide.getOpposite());"
if old_target not in text:
    raise SystemExit("Energy target lookup pattern not found")
text = text.replace(old_target, new_target, 1)

old_move = """                int available;\n                try (Transaction probe = Transaction.open(null)) { available = source.extract(remaining, probe); }\n                if (available <= 0) continue;\n                try (Transaction tx = Transaction.open(null)) {\n                    int accepted = target.insert(available, tx);\n                    if (accepted <= 0) continue;\n                    int extracted = source.extract(accepted, tx);\n                    if (extracted == accepted) {\n                        tx.commit();\n                        remaining -= accepted;\n                        total += accepted;\n                    }\n                }\n"""
new_move = """                int moved = EnergyHandlerUtil.move(source, target, remaining, null);\n                if (moved > 0) {\n                    remaining -= moved;\n                    total += moved;\n                }\n"""
if old_move not in text:
    raise SystemExit("Custom energy transaction block not found")
text = text.replace(old_move, new_move, 1)
entity_file.write_text(text, encoding="utf-8")

# --- Chemical connectivity: only connect when a registered chemical adapter accepts the endpoint. ---
adapter_file = root / "src/main/java/com/pipecore/api/ChemicalTransferAdapter.java"
adapter = adapter_file.read_text(encoding="utf-8")
old_adapter_method = "    int move(Level level, BlockPos sourcePos, Direction sourceSide, BlockPos targetPos, Direction targetSide, int maxAmount);\n"
new_adapter_method = """    int move(Level level, BlockPos sourcePos, Direction sourceSide, BlockPos targetPos, Direction targetSide, int maxAmount);\n\n    /** Returns whether this adapter recognizes a chemical endpoint on the requested side. */\n    default boolean canConnect(Level level, BlockPos pos, Direction side) {\n        // Safe default for lambda-based adapters: require a block entity, never arbitrary terrain.\n        return level.getBlockEntity(pos) != null;\n    }\n"""
if old_adapter_method not in adapter:
    raise SystemExit("ChemicalTransferAdapter method pattern not found")
adapter = adapter.replace(old_adapter_method, new_adapter_method, 1)
adapter_file.write_text(adapter, encoding="utf-8")

registry_file = root / "src/main/java/com/pipecore/api/ChemicalTransportRegistry.java"
registry = registry_file.read_text(encoding="utf-8")
move_anchor = "    public static int move(Level level, BlockPos sourcePos, Direction sourceSide, BlockPos targetPos, Direction targetSide, int maxAmount) {"
can_connect = """    public static boolean canConnect(Level level, BlockPos pos, Direction side) {\n        for (ChemicalTransferAdapter adapter : ADAPTERS) {\n            if (adapter.canConnect(level, pos, side)) return true;\n        }\n        return false;\n    }\n\n"""
if move_anchor not in registry:
    raise SystemExit("ChemicalTransportRegistry move anchor not found")
registry = registry.replace(move_anchor, can_connect + move_anchor, 1)
registry_file.write_text(registry, encoding="utf-8")

# --- Version bump. ---
props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.6" not in p:
    raise SystemExit("Expected mod_version=1.3.6 before V10 hotfix")
props.write_text(p.replace("mod_version=1.3.6", "mod_version=1.3.7", 1), encoding="utf-8")

print("Applied Pipe Core V10: Shift-only configurator preserved, NeoForge energy mover, strict chemical connectivity, version 1.3.7")

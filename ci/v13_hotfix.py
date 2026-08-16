from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('PipeCore-v7-buildsrc')

# ---------------------------------------------------------------------------
# 1) Configurator: Pipez-style sub-shape selection + internal connection toggle
# ---------------------------------------------------------------------------
pipe_block = root / 'src/main/java/com/pipecore/block/PipeBlock.java'
text = pipe_block.read_text(encoding='utf-8')
text = text.replace('Direction face = interactionFace(pos, hit);', 'Direction face = interactionFace(state, pos, hit);')

pattern = re.compile(r'''    private static Direction interactionFace\(BlockPos pos, BlockHitResult hit\) \{.*?\n    \}\n\n    private static Component modeLabel''', re.S)
replacement = '''    private static Direction interactionFace(BlockState state, BlockPos pos, BlockHitResult hit) {
        // Pipez-style hit selection: pick the closest actual pipe arm instead of the
        // dominant axis from the block center. Clicking the center falls back to the
        // face Minecraft actually hit, which also lets a disconnected arm be restored.
        Vec3 local = hit.getLocation().subtract(pos.getX(), pos.getY(), pos.getZ());
        double bestDistance = distanceTo(CENTER, local);
        Direction bestDirection = null;

        bestDirection = closerArm(state, CONN_DOWN, ARM_DOWN, Direction.DOWN, local, bestDistance, bestDirection);
        if (bestDirection != null) bestDistance = distanceTo(ARM_DOWN, local);
        Direction candidate = closerArm(state, CONN_UP, ARM_UP, Direction.UP, local, bestDistance, bestDirection);
        if (candidate != bestDirection) { bestDirection = candidate; bestDistance = distanceTo(ARM_UP, local); }
        candidate = closerArm(state, CONN_NORTH, ARM_NORTH, Direction.NORTH, local, bestDistance, bestDirection);
        if (candidate != bestDirection) { bestDirection = candidate; bestDistance = distanceTo(ARM_NORTH, local); }
        candidate = closerArm(state, CONN_SOUTH, ARM_SOUTH, Direction.SOUTH, local, bestDistance, bestDirection);
        if (candidate != bestDirection) { bestDirection = candidate; bestDistance = distanceTo(ARM_SOUTH, local); }
        candidate = closerArm(state, CONN_WEST, ARM_WEST, Direction.WEST, local, bestDistance, bestDirection);
        if (candidate != bestDirection) { bestDirection = candidate; bestDistance = distanceTo(ARM_WEST, local); }
        candidate = closerArm(state, CONN_EAST, ARM_EAST, Direction.EAST, local, bestDistance, bestDirection);
        if (candidate != bestDirection) bestDirection = candidate;

        return bestDirection != null ? bestDirection : hit.getDirection();
    }

    private static Direction closerArm(BlockState state, BooleanProperty property, VoxelShape shape,
            Direction direction, Vec3 local, double bestDistance, @Nullable Direction current) {
        if (!state.getValue(property)) return current;
        return distanceTo(shape, local) < bestDistance ? direction : current;
    }

    private static double distanceTo(VoxelShape shape, Vec3 point) {
        return shape.closestPointTo(point).map(p -> p.distanceToSqr(point)).orElse(Double.MAX_VALUE);
    }

    private static Component modeLabel'''
text2, n = pattern.subn(replacement, text, count=1)
if n != 1:
    raise SystemExit('PipeBlock interactionFace method not found; refusing to patch blindly')
pipe_block.write_text(text2, encoding='utf-8')

entity_file = root / 'src/main/java/com/pipecore/block/PipeBlockEntity.java'
text = entity_file.read_text(encoding='utf-8')

cycle_pattern = re.compile(r'''    public FaceMode cycleFaceMode\(Direction direction\) \{.*?\n    \}\n\n    public void openOutputMenu''', re.S)
cycle_replacement = '''    public FaceMode cycleFaceMode(Direction direction) {
        int index = direction.ordinal();
        PipeBlockEntity samePipeNeighbor = null;
        if (level != null) {
            BlockPos neighborPos = worldPosition.relative(direction);
            if (level.getBlockEntity(neighborPos) instanceof PipeBlockEntity neighbor && neighbor.kind() == kind()) {
                samePipeNeighbor = neighbor;
            }
        }

        if (samePipeNeighbor != null) {
            // Pipez behavior for pipe-to-pipe links: sneak-configure toggles the link
            // connected/disconnected; an internal pipe link is never an extraction face.
            FaceMode next = faceModes[index] == FaceMode.DISCONNECTED ? FaceMode.NORMAL : FaceMode.DISCONNECTED;
            faceModes[index] = next;
            samePipeNeighbor.faceModes[direction.getOpposite().ordinal()] = next;
            samePipeNeighbor.markDirtyAndSync();
        } else {
            // External endpoint: NORMAL -> OUTPUT(extract) -> DISCONNECTED -> NORMAL.
            faceModes[index] = faceModes[index].next();
        }

        markDirtyAndSync();
        if (level != null && !level.isClientSide()) {
            syncVisualState(level, true);
            if (samePipeNeighbor != null) samePipeNeighbor.syncVisualState(level, true);
        }
        return faceModes[index];
    }

    public void openOutputMenu'''
text2, n = cycle_pattern.subn(cycle_replacement, text, count=1)
if n != 1:
    raise SystemExit('PipeBlockEntity cycleFaceMode method not found; refusing to patch blindly')
text = text2

energy_pattern = re.compile(r'''    private int transferEnergy\(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate\) \{.*?\n    \}\n\n    private int transferChemicals''', re.S)
energy_replacement = '''    private int transferEnergy(Level level, List<PipeBlockEntity> network, Direction sourceFace, BlockPos sourcePos, int rate) {
        EnergyHandler source = energyHandler(level, sourcePos, sourceFace.getOpposite());
        if (source == null || source.getAmountAsLong() <= 0L) return 0;

        int remaining = rate;
        int total = 0;
        for (PipeBlockEntity targetPipe : network) {
            for (Direction targetSide : Direction.values()) {
                if (remaining <= 0) break;
                if (targetPipe.getFaceMode(targetSide) != FaceMode.NORMAL) continue;
                BlockPos targetPos = targetPipe.worldPosition.relative(targetSide);
                if (targetPos.equals(sourcePos) || !targetPipe.isExternalEndpoint(level, targetPos)) continue;

                EnergyHandler target = energyHandler(level, targetPos, targetSide.getOpposite());
                if (target == null || target == source || EnergyHandlerUtil.isFull(target)) continue;

                // Match Pipez's proven pull path: simulate what the source can actually
                // extract, then let NeoForge's transactional mover perform the transfer.
                int available;
                try (Transaction simulated = Transaction.open(null)) {
                    available = source.extract(remaining, simulated);
                }
                if (available <= 0) return total;

                int moved = EnergyHandlerUtil.move(source, target, available, null);
                if (moved > 0) {
                    remaining -= moved;
                    total += moved;
                }
            }
            if (remaining <= 0) break;
        }
        return total;
    }

    private int transferChemicals'''
text2, n = energy_pattern.subn(energy_replacement, text, count=1)
if n != 1:
    raise SystemExit('PipeBlockEntity transferEnergy method not found; refusing to patch blindly')
entity_file.write_text(text2, encoding='utf-8')

# ---------------------------------------------------------------------------
# 2) Pipe rendering: seamless exact straight runs + corrected horizontal UVs
# ---------------------------------------------------------------------------
models = root / 'src/main/resources/assets/pipecore/models/block'
blockstates = root / 'src/main/resources/assets/pipecore/blockstates'

FULL = [0, 0, 16, 16]

def face(texture, rotation=None):
    data = {'uv': FULL, 'texture': texture}
    if rotation is not None:
        data['rotation'] = rotation
    return data

# Canonical straight north/south segment. No end-cap faces and no center cube,
# so adjacent blocks visually form one uninterrupted 6x6 tube.
straight_ns_base = {
    'textures': {'particle': '#side'},
    'ambientocclusion': False,
    'elements': [{
        'from': [5, 5, 0], 'to': [11, 11, 16],
        'faces': {
            'up': face('#side'),
            'down': face('#side'),
            # On these side planes U follows Z (pipe length), so rotate the
            # longitudinal texture 90 degrees. This is the horizontal bug seen in-game.
            'west': face('#side', 90),
            'east': face('#side', 90),
        },
    }],
}

straight_vertical_base = {
    'textures': {'particle': '#side'},
    'ambientocclusion': False,
    'elements': [{
        'from': [5, 0, 5], 'to': [11, 16, 11],
        'faces': {
            'north': face('#side'), 'south': face('#side'),
            'west': face('#side'), 'east': face('#side'),
        },
    }],
}
(models / 'pipe_straight_ns_base.json').write_text(json.dumps(straight_ns_base, indent=2) + '\n', encoding='utf-8')
(models / 'pipe_straight_vertical_base.json').write_text(json.dumps(straight_vertical_base, indent=2) + '\n', encoding='utf-8')

# Correct the same longitudinal UV orientation on ordinary horizontal arms used
# by corners, branches and endpoints.
arm_path = models / 'pipe_arm_base.json'
arm = json.loads(arm_path.read_text(encoding='utf-8'))
for element in arm.get('elements', []):
    faces = element.get('faces', {})
    for name in ('west', 'east'):
        if name in faces and faces[name].get('texture') == '#side':
            faces[name]['rotation'] = 90
arm_path.write_text(json.dumps(arm, indent=2) + '\n', encoding='utf-8')

# Output arm has the same horizontal side-plane orientation problem.
output_path = models / 'pipe_output_base.json'
if output_path.exists():
    output = json.loads(output_path.read_text(encoding='utf-8'))
    for element in output.get('elements', []):
        faces = element.get('faces', {})
        for name in ('west', 'east'):
            if name in faces and faces[name].get('texture') in ('#side', '#outside'):
                faces[name]['rotation'] = 90
    output_path.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')

PROPS = ('conn_down', 'conn_up', 'conn_north', 'conn_south', 'conn_west', 'conn_east')
DIRS = {
    'conn_north': ('arm', None),
    'conn_south': ('arm', 180),
    'conn_east': ('arm', 90),
    'conn_west': ('arm', 270),
    'conn_up': ('arm_up', None),
    'conn_down': ('arm_down', None),
}

def condition(state):
    return {p: 'true' if state[p] else 'false' for p in PROPS}

def is_straight(state):
    return (
        state['conn_up'] and state['conn_down'] and not any(state[p] for p in ('conn_north','conn_south','conn_west','conn_east'))
    ) or (
        state['conn_north'] and state['conn_south'] and not any(state[p] for p in ('conn_down','conn_up','conn_west','conn_east'))
    ) or (
        state['conn_west'] and state['conn_east'] and not any(state[p] for p in ('conn_down','conn_up','conn_north','conn_south'))
    )

all_states = []
for mask in range(64):
    all_states.append({p: bool(mask & (1 << i)) for i, p in enumerate(PROPS)})
nonstraight = [s for s in all_states if not is_straight(s)]

for kind in ('item', 'fluid', 'energy', 'chemical'):
    vertical = f'pipecore:block/{kind}_pipe_vertical'
    for suffix, parent in (
        ('straight_ns', 'pipecore:block/pipe_straight_ns_base'),
        ('straight_vertical', 'pipecore:block/pipe_straight_vertical_base'),
    ):
        data = {
            'parent': parent,
            'textures': {'side': vertical, 'particle': vertical},
        }
        (models / f'{kind}_pipe_{suffix}.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

    multipart = []
    # Exact straight states take one continuous model and bypass center/half-arm pieces.
    vertical_state = {p: False for p in PROPS}; vertical_state['conn_down'] = vertical_state['conn_up'] = True
    ns_state = {p: False for p in PROPS}; ns_state['conn_north'] = ns_state['conn_south'] = True
    ew_state = {p: False for p in PROPS}; ew_state['conn_west'] = ew_state['conn_east'] = True
    multipart.append({'when': condition(vertical_state), 'apply': {'model': f'pipecore:block/{kind}_pipe_straight_vertical'}})
    multipart.append({'when': condition(ns_state), 'apply': {'model': f'pipecore:block/{kind}_pipe_straight_ns'}})
    multipart.append({'when': condition(ew_state), 'apply': {'model': f'pipecore:block/{kind}_pipe_straight_ns', 'y': 90}})

    # Every other topology retains the approved center/corner/branch geometry.
    multipart.append({
        'when': {'OR': [condition(s) for s in nonstraight]},
        'apply': {'model': f'pipecore:block/{kind}_pipe_center'},
    })
    for prop, (suffix, rot) in DIRS.items():
        states = [s for s in nonstraight if s[prop]]
        apply = {'model': f'pipecore:block/{kind}_pipe_{suffix}'}
        if rot is not None:
            apply['y'] = rot
        multipart.append({'when': {'OR': [condition(s) for s in states]}, 'apply': apply})

    (blockstates / f'{kind}_pipe.json').write_text(json.dumps({'multipart': multipart}, indent=2) + '\n', encoding='utf-8')

# ---------------------------------------------------------------------------
# 3) Version
# ---------------------------------------------------------------------------
props = root / 'gradle.properties'
p = props.read_text(encoding='utf-8')
if 'mod_version=1.3.9' not in p:
    raise SystemExit('Expected mod_version=1.3.9 before V13 hotfix')
props.write_text(p.replace('mod_version=1.3.9', 'mod_version=1.3.10', 1), encoding='utf-8')

print('Applied Pipe Core V13: seamless straight pipes, Pipez-style Shift configurator selection, energy pull hardening, version 1.3.10')

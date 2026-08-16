from pathlib import Path
import json
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PipeCore-v7-buildsrc")
models = root / "src/main/resources/assets/pipecore/models/block"

# Mekanism's transmitter models keep two different texture roles: a center/cap texture
# and a dedicated vertical/side texture for the length of the transmitter. Pipe Core
# already has those pairs; this patch fixes the geometry/UV assignment so they are used
# the same way, without copying Mekanism's loader, models, or art assets.

def face(texture, uv=None):
    data = {"texture": texture}
    if uv is not None:
        data["uv"] = uv
    return data

FULL = [0, 0, 16, 16]

center_base = {
    "textures": {"particle": "#center"},
    "ambientocclusion": False,
    "elements": [{
        "from": [5, 5, 5],
        "to": [11, 11, 11],
        "faces": {
            "down": face("#center", FULL),
            "up": face("#center", FULL),
            "north": face("#center", FULL),
            "south": face("#center", FULL),
            "west": face("#center", FULL),
            "east": face("#center", FULL),
        },
    }],
}

# Canonical horizontal arm points north. Blockstate rotations reuse it for S/E/W.
# The outward end uses the normal/cap texture; the arm length uses the vertical texture.
arm_base = {
    "textures": {"particle": "#side"},
    "ambientocclusion": False,
    "elements": [{
        "from": [5, 5, 0],
        "to": [11, 11, 5],
        "faces": {
            "north": face("#cap", FULL),
            "up": face("#side", FULL),
            "down": face("#side", FULL),
            "west": face("#side", FULL),
            "east": face("#side", FULL),
        },
    }],
}

arm_up_base = {
    "textures": {"particle": "#side"},
    "ambientocclusion": False,
    "elements": [{
        "from": [5, 11, 5],
        "to": [11, 16, 11],
        "faces": {
            "up": face("#cap", FULL),
            "north": face("#side", FULL),
            "south": face("#side", FULL),
            "west": face("#side", FULL),
            "east": face("#side", FULL),
        },
    }],
}

arm_down_base = {
    "textures": {"particle": "#side"},
    "ambientocclusion": False,
    "elements": [{
        "from": [5, 0, 5],
        "to": [11, 5, 11],
        "faces": {
            "down": face("#cap", FULL),
            "north": face("#side", FULL),
            "south": face("#side", FULL),
            "west": face("#side", FULL),
            "east": face("#side", FULL),
        },
    }],
}

for name, data in {
    "pipe_center_base.json": center_base,
    "pipe_arm_base.json": arm_base,
    "pipe_arm_up_base.json": arm_up_base,
    "pipe_arm_down_base.json": arm_down_base,
}.items():
    (models / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

for kind in ("item", "fluid", "energy", "chemical"):
    normal = f"pipecore:block/{kind}_pipe"
    vertical = f"pipecore:block/{kind}_pipe_vertical"

    center = {
        "parent": "pipecore:block/pipe_center_base",
        "textures": {
            "center": normal,
            "particle": normal,
        },
    }
    arm = {
        "parent": "pipecore:block/pipe_arm_base",
        "textures": {
            "side": vertical,
            "cap": normal,
            "particle": vertical,
        },
    }
    arm_up = {
        "parent": "pipecore:block/pipe_arm_up_base",
        "textures": {
            "side": vertical,
            "cap": normal,
            "particle": vertical,
        },
    }
    arm_down = {
        "parent": "pipecore:block/pipe_arm_down_base",
        "textures": {
            "side": vertical,
            "cap": normal,
            "particle": vertical,
        },
    }

    for suffix, data in {
        "center": center,
        "arm": arm,
        "arm_up": arm_up,
        "arm_down": arm_down,
    }.items():
        (models / f"{kind}_pipe_{suffix}.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

# Keep all approved pipe colors and existing PNG art. This is deliberately a mapping/UV
# correction only: item amber, fluid cyan, energy violet, chemical green.
props = root / "gradle.properties"
p = props.read_text(encoding="utf-8")
if "mod_version=1.3.7" not in p:
    raise SystemExit("Expected mod_version=1.3.7 before V11 texture mapping patch")
props.write_text(p.replace("mod_version=1.3.7", "mod_version=1.3.8", 1), encoding="utf-8")

print("Applied Pipe Core V11: Mekanism-style center/cap + vertical/side texture mapping, version 1.3.8")

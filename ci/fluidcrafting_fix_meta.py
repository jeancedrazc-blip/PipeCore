from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]).resolve()
res_meta = root / 'src/main/resources/META-INF'
if res_meta.exists():
    shutil.rmtree(res_meta)

template_meta = root / 'src/main/templates/META-INF'
template_meta.mkdir(parents=True, exist_ok=True)
(template_meta / 'neoforge.mods.toml').write_text('''license="${mod_license}"

[[mods]]
modId="${mod_id}"
version="${mod_version}"
displayName="${mod_name}"
authors="Jan"
description=''' + "'''" + '''
Adds real fluid input to compatible crafting tables for bucket filling recipes.
''' + "'''" + '''

[[mixins]]
config="fluidbucketcrafting.mixins.json"

[[dependencies.${mod_id}]]
modId="neoforge"
type="required"
versionRange="[${neo_version},)"
ordering="NONE"
side="BOTH"

[[dependencies.${mod_id}]]
modId="minecraft"
type="required"
versionRange="${minecraft_version_range}"
ordering="NONE"
side="BOTH"
''', encoding='utf-8')
print('Fixed MDK metadata template')

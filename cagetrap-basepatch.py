from pathlib import Path
import json, re, base64
root = Path('CageTrapProjectV4')
java = root/'src/main/java/com/jeancedraz/cagetrap'
res = root/'src/main/resources'

p = root/'build.gradle'
s = p.read_text()
s2, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.0['\"]", "version = '1.1.4'", s, count=1)
assert n == 1, 'version line not found'
p.write_text(s2)

p = java/'CageTrap.java'
s = p.read_text()
s2, n = re.subn(r'\.strength\(3\.5F,\s*1200(?:\.0)?F\)', '.strength(2.0F, 1200.0F)', s, count=1)
assert n == 1, 'strength call not found'
p.write_text(s2)

tag = res/'data/minecraft/tags/block/mineable/pickaxe.json'
tag.parent.mkdir(parents=True, exist_ok=True)
tag.write_text(json.dumps({'replace': False, 'values': ['cagetrap:cage_trap']}, indent=2) + '\n')

(res/'assets/cagetrap/models/item/cage_trap.json').write_text(json.dumps({'parent': 'cagetrap:block/cage_trap_closed'}, indent=2) + '\n')
(res/'assets/cagetrap/models/item/cage_trap_filled.json').write_text(json.dumps({
    'parent': 'cagetrap:block/cage_trap_closed',
    'textures': {'side': 'cagetrap:block/cage_trap_filled'}
}, indent=2) + '\n')
filled_png = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABGklEQVR4nK2ToU4DQRCGvyXVR1Jz16WC05gjOUNWYJtKTM+QoO4NahHYe4OzmPYFSC2CIBGEQELI1bApBtEXGMRycMBdkyX91Uz+2X//ndlRSWrkbWUJI40P6jM9ADsVdGG9BOxUOLzECehCYccVwbwPwPoicFUPS8hGMFvAwT7B+drxk3d0ERNGQJIaGQxjqZWT1EjzppPJ2Y+85gfDWJLUyE7b25q4vbneyP8RaDZTcsSOq06+VcAXvS5CcoRs5GIWokqUlwAA90//d6BKlORLqeOuuu33oDkmVaLcH6la+VYHv8d0ZI438l8OJEeCeZ+X50c3gRrZCnZd3uT11afLJDVyd/qKLjr71Aq3THvfy+S7zrqwhBF8AH4dZbMddqoUAAAAAElFTkSuQmCC'
tex = res/'assets/cagetrap/textures/block/cage_trap_filled.png'
tex.parent.mkdir(parents=True, exist_ok=True)
tex.write_bytes(base64.b64decode(filled_png))

p = java/'CageTrapBlockEntity.java'
s = p.read_text()
anchor = '    private transient Entity displayEntity;'
assert anchor in s, 'displayEntity field not found'
s = s.replace(anchor, anchor + '\n    private boolean disarmed = false;', 1)

capture_sig = '    public boolean capture(Mob mob) {'
assert capture_sig in s, 'capture method not found'
s = s.replace(capture_sig, capture_sig + '\n        if (disarmed) {\n            return false;\n        }', 1)

start = s.index('    public boolean release() {')
end = s.index('    public Entity getDisplayEntity()', start)
r = s[start:end]
r = r.replace('worldPosition.above(),', 'worldPosition.above(2),', 1)
r = r.replace('worldPosition.north()', 'worldPosition.north(2)')
r = r.replace('worldPosition.south()', 'worldPosition.south(2)')
r = r.replace('worldPosition.east()', 'worldPosition.east(2)')
r = r.replace('worldPosition.west()', 'worldPosition.west(2)')
pat = re.compile(r'(?m)^(\s*)if \([^\n]*\.addFreshEntity\([^\n]*\)\) \{')
m = pat.search(r)
# Base source uses addFreshEntity in older generated lineage; tolerate addFreshEntity/addFreshEntity equivalents.
if m is None:
    pat = re.compile(r'(?m)^(\s*)if \([^\n]*\.addFreshEntity\([^\n]*\)\) \{')
    m = pat.search(r)
if m is not None:
    insertion = m.group(0) + '\n' + m.group(1) + '    disarmed = true;'
    r = r[:m.start()] + insertion + r[m.end():]
else:
    # Current base source uses server.addFreshEntity(entity)
    pat2 = re.compile(r'(?m)^(\s*)if \(server\.addFreshEntity\(entity\)\) \{')
    m2 = pat2.search(r)
    assert m2 is not None, 'entity add conditional not found'
    insertion = m2.group(0) + '\n' + m2.group(1) + '    disarmed = true;'
    r = r[:m2.start()] + insertion + r[m2.end():]
s = s[:start] + r + s[end:]

save_anchor = '        super.saveAdditional(output);'
assert save_anchor in s, 'saveAdditional anchor not found'
s = s.replace(save_anchor, save_anchor + '\n        output.putBoolean("Disarmed", disarmed);', 1)
load_anchor = '        super.loadAdditional(input);'
assert load_anchor in s, 'loadAdditional anchor not found'
s = s.replace(load_anchor, load_anchor + '\n        disarmed = input.getBooleanOr("Disarmed", false);', 1)
p.write_text(s)

sigfile = res/'META-INF/JEAN_CEDRAZ.SIGNATURE'
if sigfile.exists(): sigfile.write_text(sigfile.read_text().replace('Build line: 1.1.0', 'Build line: 1.1.4'))
print('Stable 1.1.4 base patch applied')

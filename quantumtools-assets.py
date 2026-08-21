from pathlib import Path
import re, json, struct, zlib

root = Path('RFToolsBuilderPort261')
res = root / 'src/main/resources'
client = root / 'src/main/java/mcjty/rftoolsbuilder/client'

mods = res / 'META-INF/neoforge.mods.toml'
ms = mods.read_text(encoding='utf-8')
ms = re.sub(r'(?m)^displayName\s*=\s*".*?"', 'displayName="Quantum Tools"', ms)
mods.write_text(ms, encoding='utf-8')

for lang_name in ('pt_br.json', 'en_us.json'):
    lp = res / 'assets/rftoolsbuilder/lang' / lang_name
    lang = json.loads(lp.read_text(encoding='utf-8'))
    lang['block.rftoolsbuilder.builder'] = 'Quantum Builder'
    lang['itemGroup.rftoolsbuilder'] = 'Quantum Tools'
    lang['gui.rftoolsbuilder.filter.title'] = 'Filtro do Quarry Card' if lang_name == 'pt_br.json' else 'Quarry Card Filter'
    lang['tooltip.rftoolsbuilder.filter_open'] = 'Clique direito no ar para configurar o filtro' if lang_name == 'pt_br.json' else 'Right-click in air to configure the filter'
    lang['tooltip.rftoolsbuilder.filter_summary'] = 'Filtro: %s (%s entradas)' if lang_name == 'pt_br.json' else 'Filter: %s (%s entries)'
    lp.write_text(json.dumps(lang, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

p = client / 'BuilderScreen.java'
s = p.read_text(encoding='utf-8').replace('Component.literal("BUILDER")', 'Component.literal("QUANTUM BUILDER")')
p.write_text(s, encoding='utf-8')

# Deterministic 16x16 PNG writer. Cards follow the approved graphite/metal frame
# with orange, white/gold and cyan functional accents.
def png(path, px):
    raw = b''.join(b'\x00' + bytes(sum(row, ())) for row in px)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    out = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',16,16,8,6,0,0,0)) + chunk(b'IDAT', zlib.compress(raw,9)) + chunk(b'IEND', b'')
    path.write_bytes(out)

def make_card(accent, kind, clearing=False):
    T=(0,0,0,0); dark=(13,17,22,255); mid=(29,35,43,255); edge=(103,113,124,255); hi=(180,188,196,255)
    px=[[T for _ in range(16)] for _ in range(16)]
    for y in range(1,15):
        for x in range(2,14): px[y][x]=dark
    for x in range(3,13): px[1][x]=mid; px[14][x]=mid
    for y in range(2,14): px[y][2]=edge; px[y][13]=edge
    for p in [(2,2),(13,2),(2,13),(13,13)]: px[p[1]][p[0]]=hi
    for x in range(4,12): px[3][x]=accent
    for x in range(5,11): px[13][x]=(214,153,35,255)
    # central icons
    if kind=='shape':
        for x,y in [(5,6),(6,5),(7,5),(8,5),(9,6),(5,7),(9,7),(5,8),(9,8),(6,9),(7,10),(8,9),(6,7),(7,8),(8,7)]: px[y][x]=accent
    elif kind=='quarry':
        for x,y in [(5,5),(6,5),(7,6),(8,7),(9,8),(10,9),(5,6),(4,7),(8,8),(7,9),(6,10)]: px[y][x]=accent
        for x,y in [(10,10),(11,10),(10,11)]: px[y][x]=(115,75,35,255)
    elif kind=='fortune':
        for x,y in [(5,5),(6,5),(7,6),(8,7),(9,8),(5,6),(4,7),(7,9),(6,10)]: px[y][x]=accent
        for x,y in [(10,6),(11,7),(10,8),(9,7)]: px[y][x]=(255,204,48,255)
        px[7][10]=(255,242,153,255)
    elif kind=='silk':
        for x,y in [(5,5),(6,5),(7,6),(8,7),(9,8),(5,6),(4,7),(7,9),(6,10)]: px[y][x]=accent
        for x,y in [(9,6),(10,6),(11,7),(11,8),(10,9),(9,9),(8,8),(8,7)]: px[y][x]=(41,209,239,255)
        px[7][9]=(158,246,255,255)
    if clearing:
        white=(235,240,242,255)
        for x,y in [(4,11),(5,11),(6,11),(9,11),(10,11),(11,11),(4,12),(11,12)]: px[y][x]=white
    return px

textures = res / 'assets/rftoolsbuilder/textures/item'
textures.mkdir(parents=True, exist_ok=True)
orange=(255,137,15,255); white=(225,231,235,255); gold=(255,174,20,255); cyan=(23,211,239,255)
assets = {
    'shapecarditem.png': make_card(orange,'shape'),
    'shapecardquarryitem.png': make_card(orange,'quarry'),
    'shapecardcquarryitem.png': make_card(white,'quarry',True),
    'shapecardfortuneitem.png': make_card(gold,'fortune'),
    'shapecardcfortuneitem.png': make_card(gold,'fortune',True),
    'shapecardsilkitem.png': make_card(cyan,'silk'),
    'shapecardcsilkitem.png': make_card(cyan,'silk',True),
}
for name, pixels in assets.items(): png(textures/name, pixels)

build = root / 'build.gradle'
bs = build.read_text(encoding='utf-8')
bs = re.sub(r"(?m)^version\s*=\s*['\"][^'\"]+['\"]", "version = '3.0.0'", bs, count=1)
build.write_text(bs, encoding='utf-8')
print('Quantum Tools branding/assets applied')

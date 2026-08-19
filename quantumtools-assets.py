from pathlib import Path
import re, json, base64

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
    lang['gui.rftoolsbuilder.filter.title'] = 'Quarry Filter'
    lang['tooltip.rftoolsbuilder.filter_open'] = 'Clique direito no ar para configurar o filtro' if lang_name == 'pt_br.json' else 'Right-click in air to configure the filter'
    lang['tooltip.rftoolsbuilder.filter_summary'] = 'Filtro: %s (%s entradas)' if lang_name == 'pt_br.json' else 'Filter: %s (%s entries)'
    lp.write_text(json.dumps(lang, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

p = client / 'BuilderScreen.java'
s = p.read_text(encoding='utf-8')
s = s.replace('Component.literal("BUILDER")', 'Component.literal("QUANTUM BUILDER")')
s = s.replace('Component.literal("SHAPE")', 'Component.literal("SHAPE")')
s = s.replace('Component.literal("QUARRY")', 'Component.literal("QUARRY")')
p.write_text(s, encoding='utf-8')

CARD_B64 = {
'shapecardquarryitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA/klEQVR4nJWTIWzCQBSGvxKSHgniLBZd02SVyJnqeUhmECQEg5yYrFlIEJglYKZwJDWTkyzBoLHYOkAdYruyW5vX8pv37r3//3PvXc7jF8t1agDmszckjMYTAAZPsQfQ/NvsH2KGOw3A6SVzhK1XnXNW3TSvOwarboqvngHQScsx8JXlfDh1zyYPvUez323xlSv8j8v5RBBGfH99egANkV0DTak5W7zTP8SFerS55eINxkO7jw466QC3ZdYysGKAbHrM87sMJHEtA0lcaZBNj+JZNLDkqh2UPmMZWRoD+PlMy3VqVFsbk1AaVVsby6scoS4KIwRhRLSBIKQQy3AFX2RbF5zuxPcAAAAASUVORK5CYII=',
'shapecardcsilkitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABG0lEQVR4nJWSP0sDQRDFfycJt4HIXX12xzVCEALmOkubVBb2EWwsBPGTBMEPcGmsrt7G0k6FQBCukXSxl0OMWKyFt8f92SzJa3aYefPmzbAOBZJUKoD7uyk2XN/cAnBxPnYAOtXiZDnmau4DsF6sao3i6KDkzEJZ5msCs1DiiksA3Diqjxa9gvNQSzs6OD45VW/zF9yCuAk/628GwxGvT48OwJ6VDXw+v5dxlmWteqeVKYhB3m2JBDmwWMHkrKwZHQR5Fy+O8Io7VGN9TKuD6lQvjmprNLHxBnpqVWgngabYzg4Aq3UN4w2ae+v4Y/+XcBsBLaKbdXxos5KkUiWpVKLvK5Zfxlf0faV5um+rI9rQWmEwHP3/NNNrwB9HiWUfqWt+vQAAAABJRU5ErkJggg==',
'shapecarditem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA9klEQVR4nK2RrU/EQBDFfyVNupdUrMWermlCJfJM9XlIMAgSgqk8gawhl/AH9MypukvWIJGQnEFja+sKajFsr9vPy8Ez8zLz5u3OjMMvslxpgOf1E2O4u38A4HoZOwBus3j1GXO7lwBUq9JqnD3KWrOZqzpvGWzmCk/cACDTmWXgCaPZWnnHkIvLhf7Yv+EJu7GN76+KIIx4f31xAM5G1UCZFKN1d6hgGmV6bvGjDMqksMSGl0lRL/OkH/Rh0KD5apO3MbnEKfzZoHeE9tz2Fappg4O4e5FBZLnSWa608KXWKb1R+FIbnen7/x0EYUS0gyCkE/vwAxq7YI6CxzS+AAAAAElFTkSuQmCC',
'shapecardcquarryitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA/ElEQVR4nGNkgIIFa7b9Z2BgYJgysZ8BH8jJL2RgYGBgSAjxYmRgYGBgQZaMv+fFkHFegIGBgYHh3v0HKBqVFBXgahYqbYOLoxiwUGkbAztHMgMDAwODpqYmigHsHJxQNctQxBlhDBNb1/9Xzp+GK8QFfv74zqBjaMpw5vBuRgYGBgYmvKqJACzYBK9fv86gqanJMHHGXAY3eysMeb+gUDgbqwtg/s/PQIQHTAwWmHgNwGYYzFXogKgwwKWZKAOQNV+/fp00A9A1kOQFmGZcTifKBiciasTkfBSxYs+3/gjXb/nPwCPx/9voDVpqDR+A/TB1RLiAGwPMCudkZANyeYFKNNiGZAAAAAElFTkSuQmCC',
'shapecardcfortuneitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABDUlEQVR4nJWQsUsDMRjFf5FCU+iQ0bnbwS0H3tixIJ06uCu4dBCKo3+FFBxchOvidMNNQXDUTaGLcJt/w22tUxxsjqRN784HIR9f3ntf3ifYIcu1AXhY3tOEm8UtAFcXUwHQcx8vv6fM1wqAzYv0hIPzbc1ZjXTd9wxWI01fXgOgZv7kvhzsOM9eX9jibDwxX+uPmngMP9sNcZLy+fYqAE4a2R0QNCjLEoDl4xNVYbyzv5ugQRRFACzmdh8CNftLa5fZaODCCqvC1PW/DFyxjdbJoCrMwWQbrdXAFbchaOBmDeVuNbBCVxzK7yHLtclybeRQGfN+GrzlUBnLa/1BV/T2G3GSkt5BnHBwh/ALo11oNpfco1sAAAAASUVORK5CYII=',
'shapecardfortuneitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABDUlEQVR4nK2Tu2oCQRSGvwmCI1hMaW23sM1CtrQMiJVFekPSWAQkpU8hQoo0gjZWFlaLYJl0CdgEtssz2GmqSaFn4ia7swbyN+f2n8ucmVEcMV0kFuBxPMKH+8EDADfXHQVQOQ32Pjr0NwaA3UpnEmvtvePMmonzZwrMmglVfQeA6WY7V3XtyJln/EqUy9aVfd+8OmIRPvc7wijm7XmtAC687DNQ8QXHTxN6jdsfXk08/La8Ewz6sg+F6R5OK8v0FkjT1OmSuF1ap5cWCIKA7dI6W5JPfYLcHQhRpHQ+e4I8YhFKr7GsWOE1/mUK4PCZpovE6rqx9qWRK3XdWOFJ3v+/xDCKiYcQRvySefgCdnNYE18qkMQAAAAASUVORK5CYII=',
'shapecardsilkitem.png':'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABEklEQVR4nJWSMUsDQRCFv5PArRC4q7ULVwYhYK6ztEllYR/BxkIQf4kI/oBLk+rqbVLaRSEQhGtCuvyAIGJSrYW3y+3dZrm8ZoeZN29mHhtQIsulAnh7fcGHx6dnAO5uRwFAp1ocr0c8LGIAdsuN1Sguzg1n0pMmbwlMepJQ3AMQpok9WpyWnKmVDnRweXWtvhYfhCXxEPa7X/qDIZ/vswDgxMsGtvOViYuiaNQ7jYyjUcdn38ByA+MbU3NusJ2viNKEqPShGmszW28QpYm1TR0HPdBTq0JHCdTFjt4A8K6u4fSgfnf1jH0bAU3Wzb4TDLJcqiyXSnRjxfrH+YpurDRP97Uy0YfGCf3B8P+nuV4H/gBkI2TNtI5fCwAAAABJRU5ErkJggg=='
}
textures = res / 'assets/rftoolsbuilder/textures/item'
textures.mkdir(parents=True, exist_ok=True)
for name, encoded in CARD_B64.items(): (textures / name).write_bytes(base64.b64decode(encoded))

build = root / 'build.gradle'
bs = build.read_text(encoding='utf-8')
bs = re.sub(r"(?m)^version\s*=\s*['\"][^'\"]+['\"]", "version = '3.0.0'", bs, count=1)
build.write_text(bs, encoding='utf-8')
print('Quantum Tools branding/assets applied')

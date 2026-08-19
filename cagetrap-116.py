from pathlib import Path
import re

root = Path('CageTrapProjectV4')
java = root/'src/main/java/com/jeancedraz/cagetrap'
res = root/'src/main/resources'

# Bump 1.1.5 -> 1.1.6
p = root/'build.gradle'
s = p.read_text(encoding='utf-8')
s2, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.5['\"]", "version = '1.1.6'", s, count=1)
if n != 1:
    raise SystemExit('1.1.5 version not found')
p.write_text(s2, encoding='utf-8')

# The open Cage Trap collision floor is exactly 2/16 = 0.125 blocks high.
# Release the mob with its feet already resting on that surface. No one-block
# drop, no falling animation, no side fallback.
p = java/'CageTrapBlockEntity.java'
s = p.read_text(encoding='utf-8')
old = '''        BlockPos releasePos = worldPosition.above();
        entity.absSnapTo(
                releasePos.getX() + 0.5D,
                releasePos.getY() + 0.05D,
                releasePos.getZ() + 0.5D,
                server.getRandom().nextFloat() * 360.0F,
                0.0F
        );

        if (!server.isUnobstructed(entity)) return false;
'''
new = '''        entity.absSnapTo(
                worldPosition.getX() + 0.5D,
                worldPosition.getY() + 0.125D,
                worldPosition.getZ() + 0.5D,
                server.getRandom().nextFloat() * 360.0F,
                0.0F
        );
        entity.setDeltaMovement(Vec3.ZERO);
        entity.setOnGround(true);

        if (!server.isUnobstructed(entity)) return false;
'''
if old not in s:
    raise SystemExit('1.1.5 release block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

sig = res/'META-INF/JEAN_CEDRAZ.SIGNATURE'
if sig.exists():
    sig.write_text(sig.read_text(encoding='utf-8').replace('Build line: 1.1.5', 'Build line: 1.1.6'), encoding='utf-8')

print('Cage Trap 1.1.6: release pinned to open-cage floor')

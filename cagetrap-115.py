from pathlib import Path
import re

root = Path('CageTrapProjectV4')
java = root/'src/main/java/com/jeancedraz/cagetrap'
res = root/'src/main/resources'

# bump post-1.1.4 patched project to 1.1.5
p = root/'build.gradle'
s = p.read_text(encoding='utf-8')
s2, n = re.subn(r"(?m)^version\s*=\s*['\"]1\.1\.4['\"]", "version = '1.1.5'", s, count=1)
if n != 1: raise SystemExit('1.1.4 version not found')
p.write_text(s2, encoding='utf-8')

# Release the mob directly on the top face of the trap, not two blocks away.
p = java/'CageTrapBlockEntity.java'
s = p.read_text(encoding='utf-8')
start = s.index('        BlockPos[] candidates = new BlockPos[] {')
end_marker = '        return false;\n    }\n\n    public Entity getDisplayEntity()'
end = s.index(end_marker, start)
replacement = '''        BlockPos releasePos = worldPosition.above();
        entity.absSnapTo(
                releasePos.getX() + 0.5D,
                releasePos.getY() + 0.05D,
                releasePos.getZ() + 0.5D,
                server.getRandom().nextFloat() * 360.0F,
                0.0F
        );

        if (!server.isUnobstructed(entity)) return false;

        if (server.addFreshEntity(entity)) {
            disarmed = true;
            this.capturedEntity = null;
            this.capturedName = "";
            this.displayEntity = null;
            markChangedAndSync();
            return true;
        }

'''
s = s[:start] + replacement + s[end:]
p.write_text(s, encoding='utf-8')

# Freeze the client preview: fixed entity age + zero render partial time.
p = java/'client/CageTrapBlockEntityRenderer.java'
s = p.read_text(encoding='utf-8')
needle = '''        display.setYRot(25.0F);
        display.setXRot(0.0F);

        state.entity = entityRenderer.extractEntity(display, partialTicks);'''
repl = '''        display.setYRot(25.0F);
        display.setXRot(0.0F);
        display.setDeltaMovement(Vec3.ZERO);
        display.tickCount = 0;

        // The captured mob is a static preview, not a simulated living entity.
        // Using 0 partial time freezes idle/walk/head animation inside the cage.
        state.entity = entityRenderer.extractEntity(display, 0.0F);'''
if needle not in s: raise SystemExit('renderer extraction anchor not found')
s = s.replace(needle, repl, 1)
p.write_text(s, encoding='utf-8')

sig = res/'META-INF/JEAN_CEDRAZ.SIGNATURE'
if sig.exists(): sig.write_text(sig.read_text(encoding='utf-8').replace('Build line: 1.1.4', 'Build line: 1.1.5').replace('Build line: 1.1.0', 'Build line: 1.1.5'), encoding='utf-8')
print('Cage Trap 1.1.5 fixes applied')

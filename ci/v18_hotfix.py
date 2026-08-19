from pathlib import Path
import base64
import gzip

payload = Path(__file__).with_suffix(Path(__file__).suffix + ".gz.b64")
source = gzip.decompress(base64.b64decode(payload.read_bytes()))
exec(compile(source, str(payload), "exec"), {"__name__": "__main__"})

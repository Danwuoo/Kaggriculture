"""Create and independently import-smoke-test a deterministic tar.gz."""

import gzip
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submission"
OUTPUT = ROOT / "dist" / "submission.tar.gz"


def build():
    files = sorted(path for path in SOURCE.glob("*.py") if path.is_file())
    if not any(path.name == "main.py" for path in files):
        raise RuntimeError("submission/main.py is missing")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for path in files:
                    data = path.read_bytes()
                    info = tarfile.TarInfo(path.name)
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    if OUTPUT.stat().st_size >= 5 * 1024 * 1024:
        raise RuntimeError("archive exceeds 5 MiB")
    with tempfile.TemporaryDirectory(prefix="kaggriculture-build-") as folder:
        with tarfile.open(OUTPUT, "r:gz") as archive:
            names = archive.getnames()
            if "main.py" not in names or any("/" in name or "\\" in name for name in names):
                raise RuntimeError("main.py is not at archive root")
            archive.extractall(folder, filter="data")
        smoke = (
            "import main; "
            "a=main.agent({'player':0,'step':0,'day':0,'hour':0,'farms':[],"
            "'private':{},'market':{},'town':{}}); "
            "assert set(a)=={'farmer','hands','market'}; print(a)"
        )
        subprocess.run([sys.executable, "-c", smoke], cwd=folder, check=True, timeout=30)
    print(f"{OUTPUT} {OUTPUT.stat().st_size} bytes {len(files)} files")


if __name__ == "__main__":
    build()


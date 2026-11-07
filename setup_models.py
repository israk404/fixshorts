"""Downloads the Kokoro voice model (about 350 MB, one time) into the models folder."""
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {"kokoro-v1.0.onnx": 325_532_387, "voices-v1.0.bin": 28_214_398}
MODELS = Path(__file__).resolve().parent / "models"


def download(name, size):
    target = MODELS / name
    if target.exists() and target.stat().st_size == size:
        print(f"{name}: already downloaded")
        return
    tmp = target.with_suffix(target.suffix + ".part")
    print(f"{name}: downloading {size / 1e6:.0f} MB")

    def progress(blocks, block_size, total):
        done = min(blocks * block_size, total or size)
        sys.stdout.write(f"\r  {done / 1e6:6.1f} / {(total or size) / 1e6:.1f} MB")
        sys.stdout.flush()

    urllib.request.urlretrieve(BASE + name, tmp, progress)
    print()
    if tmp.stat().st_size != size:
        tmp.unlink()
        sys.exit(f"{name}: download was incomplete, run this script again")
    tmp.replace(target)


if __name__ == "__main__":
    MODELS.mkdir(exist_ok=True)
    for name, size in FILES.items():
        download(name, size)
    print("Models ready.")

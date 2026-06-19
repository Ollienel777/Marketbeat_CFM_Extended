import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    app_path = Path(__file__).parent / "dashboard.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), *argv]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

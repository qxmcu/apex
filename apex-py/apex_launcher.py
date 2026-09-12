import sys
from pathlib import Path

# Ensure apex is in sys.path
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from apex.cli import main

if __name__ == "__main__":
    main()

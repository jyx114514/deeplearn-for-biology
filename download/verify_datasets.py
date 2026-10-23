"""Compatibility entry: verify existing datasets without downloading."""
import sys
from dataset_tools import main

if __name__ == '__main__':
    raise SystemExit(main(['--verify-only', *sys.argv[1:]]))

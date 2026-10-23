"""Compatibility entry: download/resume chapter 6 using the portable engine."""
import sys
from dataset_tools import main

if __name__ == '__main__':
    raise SystemExit(main(['--chapters', '6', '--download-only', *sys.argv[1:]]))

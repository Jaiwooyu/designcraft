"""Small subprocess fixture to exercise timeouts, logs and output handling."""

import argparse
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--in", dest="input", type=Path)
parser.add_argument("--png-dir", type=Path)
parser.add_argument("--pdf", type=Path)
parser.add_argument("--fallback-font")
parser.add_argument("--scale")
args = parser.parse_args()
mode = args.input.read_bytes()
if mode == b"slow":
    time.sleep(30)
if mode == b"fail":
    print("invalid IDML package", file=sys.stderr)
    sys.exit(1)
if mode == b"log":
    sys.stderr.write("x" * 200000 + "\n")
if mode == b"assets":
    assert (args.input.parent / "Links" / "nested" / "image.jpg").read_bytes() == b"image"
    assert (args.input.parent / "Document Fonts" / "example.txt").read_bytes() == b"font"
print("warning: test diagnostic", file=sys.stderr)
if args.png_dir:
    args.png_dir.mkdir(parents=True, exist_ok=True)
    (args.png_dir / "page-001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
if args.pdf:
    args.pdf.write_bytes(b"%PDF-1.7\n" + b"0" * 32)

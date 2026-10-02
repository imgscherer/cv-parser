import argparse
import sys
from pathlib import Path

from .parser import parse_resume


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract structured JSON from a resume (pdf, docx, jpg, png).")
    ap.add_argument("file", help="path to the resume")
    ap.add_argument("-o", "--output", help="write JSON to this file instead of stdout")
    args = ap.parse_args()

    result = parse_resume(args.file).model_dump_json(indent=2)
    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(result)


main()

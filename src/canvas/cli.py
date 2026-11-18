"""Validate canvas actions or render them as standalone SVG."""
import argparse
import json
from pathlib import Path
import sys

from .engine import validate_actions
from .svg import render


def read_actions(source):
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    payload = json.loads(text)
    actions = payload.get("actions") if isinstance(payload, dict) else payload
    if not isinstance(actions, list):
        raise ValueError('Expected an action list or an object containing an "actions" list')
    return validate_actions(actions)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Grace's vector canvas tools")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, description in (
        ("render", "render JSON actions as SVG"),
        ("validate", "validate JSON actions and output normalized JSON"),
    ):
        subparser = commands.add_parser(command, help=description)
        subparser.add_argument("input", nargs="?", default="-", help="input JSON file (default: stdin)")
        subparser.add_argument("-o", "--output", default="-", help="output file (default: stdout)")
        if command == "render":
            subparser.add_argument("--no-grain", action="store_true", help="omit the paper grain overlay")
    args = parser.parse_args(argv)
    try:
        actions = read_actions(args.input)
        if args.command == "render":
            output = render(actions, validate=False, grain=not args.no_grain)
        else:
            output = json.dumps(actions, ensure_ascii=False, indent=2)
        if args.output == "-":
            sys.stdout.write(output + "\n")
        else:
            Path(args.output).write_text(output + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"canvas: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

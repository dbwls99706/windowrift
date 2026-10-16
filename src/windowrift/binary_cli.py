"""WindowRift executable investigation, evidence only and no automatic patching."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .binary_probe import ProbeError, inspect_binary, inspect_process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, help="Executable (.exe, ELF) or JAR")
    parser.add_argument("--pid", type=int, help="Read metadata for a running Linux PID")
    parser.add_argument("--assembly", action="store_true", help="Include bounded, read-only objdump disassembly")
    parser.add_argument("--output", type=Path, help="Write structured local JSON evidence report")
    args = parser.parse_args(argv)
    if args.target is None and args.pid is None:
        parser.error("Provide a target executable or --pid")
    try:
        process = inspect_process(args.pid) if args.pid is not None else None
        target = args.target or Path(process["executable"])
        report = inspect_binary(target, disassemble=args.assembly,
                                mapped_modules=tuple(process["mapped_files"]) if process else ())
    except (ProbeError, OSError) as exc:
        parser.exit(2, f"Inspection refused: {exc}\n")
    result = {"report": report.to_dict(), "process": process,
              "recommended_action": "Validate an authorized game-specific runtime state adapter before any mutation."}
    content = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Read-only evidence saved: {args.output}")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

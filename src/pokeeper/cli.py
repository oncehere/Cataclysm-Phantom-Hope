"""The same command line entry point serves native and one-shot containers."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .config import KeeperError, load_config
from .core import check, plan
from .transaction import TransactionError, apply_candidate, recover


def parser():
    p = argparse.ArgumentParser(prog="pokeeper", description="Maintain reviewable PO translations from local snapshots")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("plan", "fill"):
        cmd = commands.add_parser(name, help="create a complete candidate" if name == "plan" else "explicitly fill gaps via Gemini API")
        cmd.add_argument("--config", required=True, type=Path)
        cmd.add_argument("--candidate", required=True, type=Path)
        cmd.add_argument("--adopt-existing", choices=("reuse", "protect"))
        cmd.add_argument("--unprotect", action="append", default=[], metavar="ENTRY_ID",
                         help="explicitly release an entry ID shown in report/state (repeatable)")
        if name == "fill":
            cmd.add_argument("--cache", required=True, type=Path)
            cmd.add_argument("--retry-unknown", action="store_true", help="retry unknown outcomes; may incur charges again")
            cmd.add_argument("--cache-only", action="store_true", help="offline: reuse completed results, never request or retry")
    cmd = commands.add_parser("export", help="export unprotected gaps from a candidate for offline translation")
    cmd.add_argument("candidate", type=Path)
    cmd.add_argument("--output", required=True, type=Path)
    cmd.add_argument("--batch-size", type=int, default=12)
    cmd.add_argument("--max-chars", type=int, default=16000)
    cmd = commands.add_parser("responses", help="check saved offline responses and show the next unfinished batch")
    cmd.add_argument("bundle", type=Path)
    cmd.add_argument("--batch", help="check just one batch, e.g. 0001")
    cmd = commands.add_parser("import", help="validate offline responses and create a complete candidate")
    cmd.add_argument("bundle", type=Path)
    cmd.add_argument("--candidate", required=True, type=Path)
    cmd = commands.add_parser("apply", help="recheck inputs and apply a reviewed candidate")
    cmd.add_argument("candidate", type=Path)
    for name in ("check", "compile"):
        cmd = commands.add_parser(name, help="offline PO/state verification" if name == "check" else "offline MO compilation")
        cmd.add_argument("--config", required=True, type=Path)
        if name == "compile":
            cmd.add_argument("--output", required=True, type=Path)
    cmd = commands.add_parser("recover", help="resolve an interrupted application")
    cmd.add_argument("--config", required=True, type=Path)
    cmd.add_argument("--action", choices=("finish", "rollback"), required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = {"candidate": str(plan(args.config, args.candidate, args.adopt_existing, args.unprotect))}
        elif args.command == "fill":
            from .gemini import fill
            result = {"candidate": str(fill(args.config, args.candidate, args.cache, args.adopt_existing,
                                            args.unprotect, args.retry_unknown, cache_only=args.cache_only))}
        elif args.command == "export":
            from .exchange import export_bundle
            result = export_bundle(args.candidate, args.output, args.batch_size, args.max_chars)
        elif args.command == "responses":
            from .exchange import response_status
            result = response_status(args.bundle, args.batch)
            if result["status"] == "FAIL":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 2
        elif args.command == "import":
            from .exchange import import_bundle
            result = {"candidate": str(import_bundle(args.bundle, args.candidate))}
        elif args.command == "apply":
            apply_candidate(args.candidate)
            result = {"status": "PASS", "applied": str(args.candidate)}
        elif args.command in ("check", "compile"):
            result = check(args.config, getattr(args, "output", None))
        else:
            cfg = load_config(args.config)
            recover(cfg.resolve("state"), args.action)
            result = {"status": "PASS", "recovery": args.action}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeeperError, TransactionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

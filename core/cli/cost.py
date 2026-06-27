"""CLI handler for ``mcp-coder cost`` (P15-004)."""

from __future__ import annotations


def main_cost(argv: list[str]) -> int:
    """CLI handler for ``mcp-coder cost``.

    Usage:
        mcp-coder cost [--workspace PATH] [--project KEY] [--limit N] [--json]

    Prints a formatted cost report to stdout. --json outputs raw JSON.
    """
    import argparse
    import json
    import os

    from core.logging.cost_report import build_project_cost_report

    parser = argparse.ArgumentParser(
        prog="mcp-coder cost",
        description="Show per-project cost report from delegation logs.",
    )
    parser.add_argument(
        "--workspace", "-w", default=None, help="Workspace root (default: cwd)"
    )
    parser.add_argument(
        "--project",
        "-p",
        default=None,
        dest="project_key",
        help="Filter to project_key",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=None, help="Max delegations to read"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Raw JSON output",
    )
    args = parser.parse_args(argv)

    ws = args.workspace or os.getcwd()
    report = build_project_cost_report(
        ws, project_key=args.project_key, limit=args.limit
    )

    if args.json_output:
        print(json.dumps(report, indent=2))
        return 0

    # Human-readable output
    print(
        f"Project: {report['project_key']}  "
        f"({report['delegation_count']} delegations)"
    )
    print(f"Total cost: ${report['total_usd']:.4f} USD")
    print()
    if report["by_model"]:
        print("By model:")
        for model, m in sorted(
            report["by_model"].items(), key=lambda x: -x[1]["cost_usd"]
        ):
            print(
                f"  {model:<55} ${m['cost_usd']:.4f}  "
                f"({m['input_tokens']}in + {m['output_tokens']}out tokens)"
            )
    print()
    if report["by_role"]:
        print("By role:")
        for role, r in sorted(
            report["by_role"].items(), key=lambda x: -x[1]["cost_usd"]
        ):
            print(
                f"  {role:<20} ${r['cost_usd']:.4f}  "
                f"({r['calls']} calls)  [{r['model']}]"
            )
    print()
    if report["by_task"]:
        print("By task (top 10):")
        for task in report["by_task"][:10]:
            sp = task["spec_path"] or "(quick delegation)"
            print(
                f"  {sp:<60} ${task['cost_usd']:.4f}  "
                f"({task['runs']} runs)"
            )
    if report["uncaptured_roles"]:
        print()
        print(
            f"Note: {', '.join(report['uncaptured_roles'])} "
            "token data unavailable for some runs (cost 0)."
        )
    if report.get("note"):
        print(f"Note: {report['note']}")
    return 0

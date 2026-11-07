from __future__ import annotations

import argparse
import json

from ecommerce_agent.cli import ROOT, build_runtime
from ecommerce_agent.dashboard import generate_dashboard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ecommerce-agent-demo")
    parser.add_argument("--as", dest="user_id", required=True)
    args = parser.parse_args(argv)
    identities, gateway, traces = build_runtime()
    identity = identities.resolve(args.user_id, channel="demo_portal")
    result = generate_dashboard(
        gateway,
        traces,
        identity=identity,
        output_path=ROOT / "runtime/dashboard" / args.user_id / "index.html",
    )
    print(
        json.dumps(
            {
                "identity": args.user_id,
                "role": identity.role,
                "dashboard": str(result.output_path),
                "mcp_command": (
                    f"ECOMMERCE_AGENT_USER={args.user_id} uv run ecommerce-agent-mcp"
                ),
                "trace_id": result.trace_id,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

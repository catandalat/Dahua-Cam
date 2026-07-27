from __future__ import annotations

import argparse
import json
import sys

import httpx

from dahua_client.client import DahuaClient, extract_supported_event_codes, select_subscribe_codes


def probe_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Probe Dahua camera event caps")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--https", action="store_true")
    parser.add_argument("-o", "--output", help="Write JSON to file")
    args = parser.parse_args(argv)

    async def _run() -> dict:
        client = DahuaClient(
            args.host,
            args.user,
            args.password,
            port=args.port,
            use_https=args.https,
        )
        caps = await client.get_caps()
        supported = extract_supported_event_codes(caps)
        subscribe = select_subscribe_codes(supported)
        return {
            "host": args.host,
            "caps": caps,
            "supported_event_codes": supported,
            "subscribe_codes": subscribe,
        }

    import asyncio

    try:
        result = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)

    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    probe_main()

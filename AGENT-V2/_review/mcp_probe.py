"""Probe an MCP streamable-HTTP server and say why a client sees no tools.

Pure stdlib — no curl, no pip, runs on Windows/macOS/Linux.

    python3 mcp_probe.py https://<host>/mcp
    python3 mcp_probe.py https://<host>/mcp --user-id bk42867
    python3 mcp_probe.py https://<host>/mcp --token "<bearer>" --insecure

It runs four checks and prints a verdict:

    GET  /health   is the pod up and routable at all
    GET  /mcp      transport shape: 405 = stateless (no SSE), 406 = stateful
    POST initialize   can a session be opened
    POST tools/list   how many tools the server actually registers

Compare a working environment against a failing one; the first row that
differs is the cause.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 30


class Result:
    def __init__(self, status=None, headers=None, body="", error=None):
        self.status = status
        self.headers = headers or {}
        self.body = body
        self.error = error

    def header(self, name):
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return None


def request(url, method="GET", payload=None, extra_headers=None, ctx=None):
    """One HTTP call. Never raises — transport problems come back as .error."""
    headers = {"Accept": "application/json, text/event-stream"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers or {})

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return Result(resp.status, dict(resp.headers),
                          resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return Result(exc.code, dict(exc.headers or {}),
                      exc.read().decode("utf-8", "replace"))
    except Exception as exc:  # DNS, TLS, refused, timeout
        return Result(error=f"{type(exc).__name__}: {exc}")


def parse_payload(body):
    """Streamable HTTP answers as JSON or as SSE (`data: {...}`). Handle both."""
    body = (body or "").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
    return None


def base_of(mcp_url):
    parts = urlsplit(mcp_url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def show(label, res):
    if res.error:
        print(f"  {label:<22} TRANSPORT ERROR — {res.error}")
    else:
        first = (res.body or "").strip().splitlines()
        snippet = first[0][:110] if first else ""
        print(f"  {label:<22} HTTP {res.status}   {snippet}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="full MCP endpoint, e.g. https://host/mcp")
    ap.add_argument("--user-id", help="sent as x-user-id (SOEID)")
    ap.add_argument("--header", action="append", default=[],
                    metavar="NAME:VALUE", help="extra header; repeatable")
    ap.add_argument("--token", help="sent as Authorization: Bearer <token>")
    ap.add_argument("--insecure", action="store_true",
                    help="skip TLS verification (corporate MITM certs)")
    args = ap.parse_args()

    ctx = None
    if args.insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    ident = {}
    if args.user_id:
        ident["x-user-id"] = args.user_id
    if args.token:
        ident["Authorization"] = f"Bearer {args.token}"
    for h in args.header:
        if ":" not in h:
            sys.exit(f"--header must be NAME:VALUE, got {h!r}")
        name, _, value = h.partition(":")
        ident[name.strip()] = value.strip()

    print(f"\nProbing {args.url}")
    if ident:
        print(f"  sending headers: {', '.join(sorted(ident))}")
    print()

    # 1. Is the pod up and routable at all?
    health = request(base_of(args.url) + "/health", ctx=ctx)
    show("GET /health", health)

    # 2. Transport shape. 405 = stateless (GET/SSE disabled). 406 = stateful,
    #    negotiating (it wants Accept: text/event-stream). Browsers see these.
    get_mcp = request(args.url, extra_headers={"Accept": "application/json"}, ctx=ctx)
    show("GET  /mcp", get_mcp)

    # 3. Open a session.
    init = request(args.url, "POST", {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "mcp_probe", "version": "1"}},
    }, ident, ctx)
    show("POST initialize", init)

    session = init.header("mcp-session-id")
    if session:
        print(f"  {'session id':<22} {session}")

    tools = None
    listed = None
    if init.status and 200 <= init.status < 300:
        sess_headers = dict(ident)
        if session:
            sess_headers["Mcp-Session-Id"] = session
        # Best-effort; some servers require it before accepting requests.
        request(args.url, "POST",
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                sess_headers, ctx)

        listed = request(args.url, "POST",
                         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                         sess_headers, ctx)
        show("POST tools/list", listed)

        payload = parse_payload(listed.body) or {}
        tools = (payload.get("result") or {}).get("tools")
        if tools is not None:
            print(f"  {'tools registered':<22} {len(tools)}")
            for t in tools:
                print(f"      - {t.get('name')}")
        elif payload.get("error"):
            print(f"  {'jsonrpc error':<22} {payload['error']}")

    # ---------------------------------------------------------------- verdict
    print("\nVERDICT")
    if health.error and init.error:
        print("  Cannot reach the host at all — DNS, TLS or network, not the app.")
        print("  If TLS, re-run with --insecure to confirm it is a cert issue.")
    elif init.status == 403 or get_mcp.status == 403:
        print("  403 — rejected before the MCP layer. AuthMiddleware cannot cause")
        print("  this: it hooks on_call_tool/on_read_resource/on_get_prompt and has")
        print("  no on_list_tools. Look at the route/gateway, and at DISABLE_COIN.")
    elif get_mcp.status == 405 and (init.status is None or init.status >= 400):
        print("  405 on GET and initialize failing — the server is stateless AND")
        print("  POST is not working. Check the app is actually serving /mcp.")
    elif tools is not None and len(tools) == 0:
        print("  Session opens but the server registers ZERO tools. _BQS_AVAILABLE")
        print("  is False in this image — the import of services.domain_query_service")
        print("  failed. Check the startup log for:")
        print("    'Capital Markets BQS tools are NOT active on this HTTP server.'")
        print("  and the 'Reason:' warning above it.")
    elif tools:
        print(f"  Server is healthy and exposes {len(tools)} tool(s). The MCP is NOT")
        print("  the problem — the agent's toolset config is (wrong URL, missing")
        print("  toolset binding, or the client never connects).")
        if get_mcp.status == 405:
            print()
            print("  NOTE: GET /mcp returned 405, so this server is still stateless.")
            print("  POST clients (ADK) are fine; a client that opens with GET/SSE")
            print("  gets nothing. Drop stateless_http=True to match the v1 server.")
        elif get_mcp.status == 406:
            print()
            print("  GET /mcp returned 406 — stateful, same as the v1 server. Good.")
    else:
        print("  Inconclusive. Send the full output above along with the pod log")
        print("  for the same timestamp.")
    print()

    return 0 if tools else 1


if __name__ == "__main__":
    raise SystemExit(main())

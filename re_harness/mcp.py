"""Minimal local stdio MCP adapter for Codex / Antigravity.

One JSON-RPC message per line. Do not print logging to stdout.
For long first-pass Ghidra analysis, prefer the CLI to avoid agent tool timeouts.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from . import core


def schema(properties=None, required=None):
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
TOOLS = [
    {
        "name": "harness_create_plan",
        "description": "Create a durable read-only REA investigation for a local ELF.",
        "inputSchema": schema({"binary_path": STRING, "workflow_path": STRING},
                              ["binary_path"]),
    },
    {
        "name": "harness_execute_step",
        "description": "Execute one pending REA CLI step and checkpoint it. May be slow for Ghidra.",
        "inputSchema": schema({"run_id": STRING, "timeout": INTEGER,
                               "retries": INTEGER}, ["run_id"]),
    },
    {
        "name": "harness_list_runs",
        "description": "List recent harness runs and statuses.",
        "inputSchema": schema(),
    },
    {
        "name": "harness_get_run",
        "description": "Get task status, selectors and existing claims for a run.",
        "inputSchema": schema({"run_id": STRING}, ["run_id"]),
    },
    {
        "name": "harness_queue_function",
        "description": "Queue function dossier and pseudocode by exact name/address.",
        "inputSchema": schema({"run_id": STRING, "procedure": STRING},
                              ["run_id", "procedure"]),
    },
    {
        "name": "harness_add_claim",
        "description": "Record a claim with an explicit evidence task and classification.",
        "inputSchema": schema({
            "run_id": STRING, "statement": STRING,
            "assessment": {"type": "string", "enum": sorted(core.ASSESSMENTS)},
            "task_key": STRING, "symbol": STRING, "address": STRING,
            "rationale": STRING,
        }, ["run_id", "statement"]),
    },
    {
        "name": "harness_validate",
        "description": "Check binary identity, task status, evidence hashes and provenance.",
        "inputSchema": schema({"run_id": STRING}, ["run_id"]),
    },
    {
        "name": "harness_render_report",
        "description": "Generate Markdown report for a run under .re_harness_mvp/reports.",
        "inputSchema": schema({"run_id": STRING}, ["run_id"]),
    },
]


def call_tool(name, args, state):
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be a JSON object")
    with core.database(state) as db:
        if name == "harness_create_plan":
            return {"run_id": core.create_plan(
                db, args["binary_path"],
                args.get("workflow_path", core.DEFAULT_WORKFLOW),
            )}
        if name == "harness_execute_step":
            # Bounded one-step invocation; clients must set adequate tool timeout.
            return core.execute(db, state, args["run_id"], max_steps=1,
                                retries=args.get("retries", 0),
                                timeout=args.get("timeout", 900))
        if name == "harness_list_runs":
            return core.status(db)
        if name == "harness_get_run":
            return core.status(db, args["run_id"])
        if name == "harness_queue_function":
            return {"queued": core.append_function(db, args["run_id"],
                                                   args["procedure"])}
        if name == "harness_add_claim":
            return {"claim_id": core.add_claim(
                db, args["run_id"], args["statement"],
                args.get("assessment", "INFERRED"), args.get("task_key"),
                args.get("symbol"), args.get("address"), args.get("rationale"),
            )}
        if name == "harness_validate":
            return core.validate(db, state, args["run_id"])
        if name == "harness_render_report":
            return {"report": str(core.render_report(db, state, args["run_id"]))}
    raise ValueError("Unknown harness tool: " + str(name))


def send(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def process(req, state):
    method = req.get("method")
    rid = req.get("id")
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    if rid is None:
        return None
    if method == "initialize":
        client_version = req.get("params", {}).get("protocolVersion", "2025-03-26")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": client_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "re-dragon-harness", "version": "0.2.0"},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        try:
            result = call_tool(params.get("name"), params.get("arguments") or {}, state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(
                    result, ensure_ascii=False, default=str)}], "isError": False,
            }}
        except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": str(exc)}], "isError": True,
            }}
    return {"jsonrpc": "2.0", "id": rid, "error": {
        "code": -32601, "message": "Unknown JSON-RPC method",
    }}


def main():
    p = argparse.ArgumentParser(description="REA harness MCP stdio adapter")
    p.add_argument("--state-dir", default=str(core.DEFAULT_STATE))
    args = p.parse_args()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            reply = process(request, args.state_dir)
        except (ValueError, KeyError, TypeError) as exc:
            reply = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": str(exc),
            }}
        if reply is not None:
            send(reply)


if __name__ == "__main__":
    main()

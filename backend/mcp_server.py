#!/usr/bin/env python3
"""
Kisan Alert MCP Server — Claude Desktop integration for district officers.

Tools exposed:
  - get_crop_advisory    : Get AI advisory for a crop problem
  - get_district_stats   : Get query statistics for a district
  - get_weather          : Get 7-day farm weather forecast
  - generate_district_alert : Generate an alert for a district
  - get_recent_queries   : Get recent farmer queries
  - translate_advisory   : Translate advisory to local language

Usage: Add to Claude Desktop config:
  {
    "mcpServers": {
      "kisan-alert": {
        "command": "python",
        "args": ["/path/to/backend/mcp_server.py"],
        "env": { "GEMINI_API_KEY": "...", "ANTHROPIC_API_KEY": "..." }
      }
    }
  }
"""
import asyncio
import json
import os
import sys

# Minimal MCP stdio server (no external mcp package needed)

TOOLS = [
    {
        "name": "get_crop_advisory",
        "description": "Get AI-powered crop advisory for a farmer's problem. Uses Gemini + Claude multi-agent pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Farmer's problem description"},
                "crop": {"type": "string", "description": "Crop name (rice, cotton, tomato, etc.)"},
                "language": {"type": "string", "description": "Farmer's language code (te/hi/en/ta/kn)", "default": "en"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_district_stats",
        "description": "Get aggregated statistics about farmer queries for the district",
        "inputSchema": {
            "type": "object",
            "properties": {
                "district": {"type": "string", "description": "District name", "default": "Guntur"}
            }
        }
    },
    {
        "name": "get_weather",
        "description": "Get 7-day weather forecast and farm advisories for a district",
        "inputSchema": {
            "type": "object",
            "properties": {
                "district": {"type": "string", "description": "AP district name", "default": "Guntur"}
            }
        }
    },
    {
        "name": "generate_district_alert",
        "description": "Generate and broadcast a crop advisory alert for a district",
        "inputSchema": {
            "type": "object",
            "properties": {
                "district": {"type": "string", "description": "District to alert"},
                "season": {"type": "string", "enum": ["kharif", "rabi", "zaid"], "default": "kharif"}
            },
            "required": ["district"]
        }
    },
    {
        "name": "get_recent_queries",
        "description": "Get recent farmer queries with issue types, severity, and advisory given",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of queries to return (max 50)", "default": 20},
                "district": {"type": "string", "description": "Filter by district/village", "default": ""}
            }
        }
    },
    {
        "name": "translate_advisory",
        "description": "Translate an advisory to Telugu, Hindi, or other Indian languages",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Advisory text in English"},
                "target_language": {"type": "string", "description": "Target language code: te/hi/ta/kn/mr"}
            },
            "required": ["text", "target_language"]
        }
    }
]


def _call_tool(name: str, args: dict) -> dict:
    """Execute a tool and return result."""
    import httpx

    base = os.environ.get("KISAN_API_BASE", "https://kisan-alert-backend-564262191703.us-central1.run.app")

    try:
        with httpx.Client(timeout=30) as http:
            if name == "get_crop_advisory":
                r = http.post(f"{base}/query/text", json={
                    "text": args.get("query", ""),
                    "crop": args.get("crop", ""),
                    "language": args.get("language", "en"),
                    "use_claude": True,
                })
                data = r.json()
                return {
                    "diagnosis": data.get("confirmed_diagnosis") or data.get("issue_type"),
                    "severity": data.get("severity"),
                    "advisory": data.get("advisory"),
                    "immediate_action": data.get("immediate_action"),
                    "products": data.get("products_recommended", []),
                    "claude_validated": data.get("claude_validated", False),
                    "source": data.get("source", "gemini_only"),
                    "follow_up_days": data.get("follow_up_days", 7),
                }

            elif name == "get_district_stats":
                r = http.get(f"{base}/query/stats")
                return r.json()

            elif name == "get_weather":
                district = args.get("district", "Guntur")
                r = http.get(f"{base}/weather/{district}")
                data = r.json()
                return {
                    "district": data["district"],
                    "current": data["current"],
                    "forecast_7d": data["forecast"][:7],
                    "farm_advisories": data["farm_advisory"],
                }

            elif name == "generate_district_alert":
                district = args.get("district", "Guntur")
                r = http.post(f"{base}/alerts/generate", params={"district": district})
                return r.json()

            elif name == "get_recent_queries":
                limit = min(args.get("limit", 20), 50)
                district = args.get("district", "")
                r = http.get(f"{base}/query/history", params={"limit": limit, "district": district})
                data = r.json()
                queries = data if isinstance(data, list) else data.get("queries", [])
                return {
                    "count": len(queries),
                    "queries": [
                        {
                            "id": q.get("id"), "crop": q.get("crop"), "issue_type": q.get("issue_type"),
                            "severity": q.get("severity"), "village": q.get("village"),
                            "language": q.get("language"), "created_at": q.get("created_at"),
                        }
                        for q in queries
                    ]
                }

            elif name == "translate_advisory":
                from services.gemini_service import translate_text
                translated = translate_text(args.get("text", ""), args.get("target_language", "te"))
                return {"translated": translated, "language": args.get("target_language")}

    except Exception as e:
        return {"error": str(e)}


def _respond(req_id, result):
    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
    msg = json.dumps(response)
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()


def _error(req_id, code, message):
    response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    msg = json.dumps(response)
    sys.stdout.write(f"Content-Length: {len(msg)}\r\n\r\n{msg}")
    sys.stdout.flush()


def main():
    """Stdio MCP server loop."""
    while True:
        # Read Content-Length header
        headers = {}
        while True:
            line = sys.stdin.readline()
            if not line or line == "\r\n":
                break
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        length = int(headers.get("content-length", 0))
        if length == 0:
            continue

        body = sys.stdin.read(length)
        try:
            req = json.loads(body)
        except Exception:
            continue

        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            _respond(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kisan-alert", "version": "1.0.0"}
            })

        elif method == "tools/list":
            _respond(req_id, {"tools": TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = _call_tool(tool_name, tool_args)
            _respond(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]
            })

        elif method == "notifications/initialized":
            pass  # no response needed

        else:
            if req_id is not None:
                _error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()

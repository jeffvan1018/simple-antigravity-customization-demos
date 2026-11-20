# MCP Server Demo

This directory configures a workspace plugin (`.agents/plugins/cloud-assistant/`) that runs a local stdio MCP server (`cloud-assistant/main.py`) built with FastMCP. Its `get_cloud_projects` tool returns a static list of sample project names.

**Prerequisite:** `uv`

Open this directory in your harness, run `/mcp` to verify **Cloud Assistant** is available, and invoke it with a prompt:

```bash
agy -p "what are my cloud projects?"
```

# Hook Demo

This directory configures a `PreToolUse` hook on `run_command` (`.agents/hooks.json` -> `.agents/scripts/block_microsoft_pypi.py`) to block installing Microsoft-authored Python packages.

**Prerequisite:** `python3` (3.13+)

Open this directory in your harness and ask it to install a Microsoft package such as `azure-identity`:

```bash
agy -p "let's install the azure-identity python package"
```

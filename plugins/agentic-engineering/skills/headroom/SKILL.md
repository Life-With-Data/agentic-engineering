---
name: headroom
description: Compress AI context (tool outputs, logs, RAG chunks, files, conversation history) before sending to LLMs using the Headroom CLI to cut 60-95% of tokens with the same answers. Use when token budgets are tight, when an agent's context is bloated by large tool outputs or logs, when wrapping a coding agent to reduce cost, or on requests to "compress context", "reduce tokens", "run headroom", "wrap my agent", or "start the headroom proxy".
---

# Headroom Context Compression Skill

Headroom is a content-aware compression layer for AI agents. It compresses
everything an agent reads — tool outputs, logs, RAG chunks, files, and
conversation history — before it reaches the LLM, cutting 60-95% of tokens
while preserving answer quality via reversible compression (originals are
cached and restored on demand). It runs as a library, a drop-in proxy, an MCP
server, and an agent wrapper.

Upstream: <https://github.com/headroomlabs-ai/headroom> (Apache 2.0).

## Setup Check (Always Run First)

Before any Headroom operation, verify the CLI is installed:

```bash
command -v headroom >/dev/null 2>&1 && echo "headroom installed: $(headroom --version 2>/dev/null)" || echo "NOT INSTALLED"
```

### If Headroom is NOT installed

Install it as a global tool with `uv` (recommended — isolates the CLI in its
own environment while exposing `headroom` on the PATH):

```bash
uv tool install "headroom-ai[all]"
```

Fallbacks if `uv` is unavailable:

```bash
pip install "headroom-ai[all]"   # global/venv pip install
```

**Requirements:** Python 3.10+. The optional ONNX features need an AVX2-capable
x86/x86_64 CPU; on other architectures install the base package (`headroom-ai`)
without the `[all]` extra.

To upgrade an existing install:

```bash
headroom update            # self-update
uv tool upgrade headroom-ai   # if installed via uv
```

### Confirm routing works

After install, run the health check before relying on compression:

```bash
headroom doctor
```

## Core Commands

| Command | Purpose |
|---------|---------|
| `headroom doctor` | Health check — confirm install and routing work |
| `headroom wrap <agent>` | Wrap a coding agent (Claude, Cursor, Cline, Aider, …) with compression |
| `headroom proxy --port 8787` | Start the drop-in proxy for zero-code integration |
| `headroom perf` | Show compression performance metrics |
| `headroom dashboard` | Live savings dashboard (requires a running proxy) |
| `headroom learn` | Mine failed sessions, write corrections to local markdown |

## Common Workflows

### Wrap a coding agent (lowest friction)

Prefix the agent's launch command with `headroom wrap` to compress its context
transparently:

```bash
headroom wrap claude       # wrap Claude Code
headroom wrap aider        # wrap Aider
```

Supported agents include Claude Code, Cursor, Copilot CLI, Aider, Continue,
Cline, Goose, and OpenHands.

### Run as a proxy (zero code changes)

Point the agent's API base URL at the local proxy and Headroom compresses
requests in flight:

```bash
headroom proxy --port 8787
# then set the agent's base URL to http://localhost:8787
```

Check live savings while the proxy runs:

```bash
headroom dashboard
```

### Use as a library

For programmatic control inside a Python tool or agent:

```python
from headroom import compress

compressed = compress(large_tool_output)
```

A TypeScript SDK is also published (`npm install headroom-ai`, library-only —
no CLI).

### Learn from failures

Turn failed sessions into durable corrections written to local markdown:

```bash
headroom learn
```

This complements the compounding-engineering loop — captured corrections become
context that future runs read (cheaply, once compressed).

## When to Reach for Headroom

- An agent's context is dominated by large, low-signal tool outputs or logs.
- Token cost or context-window pressure is the bottleneck, not model capability.
- Wrapping an existing coding agent to reduce spend without changing its code.
- Sharing memory/context across agents (Claude, Codex, Gemini) with less bloat.

Headroom's compression is reversible — it caches originals and restores them on
demand — so it is safe to layer under agents that need faithful outputs.

---
title: TOOLS
status: active
created: 2026-11-19
tags: [agent/tools, on-demand]
---

# TOOLS.md

## Positioning

Process-oriented operational steps for tool use: how the assistant works through the sandbox, files, shell, and computer surface.

## Boundary Definition: Everything else

* Safety boundaries and content policy → AGENTS.md
* Reasoning procedure and session discipline → DISCIPLINE.md
* Identity facts (name, capabilities, service target) → IDENTITY.md
* Personality, values, and tone → SOUL.md
* Term definitions → CONTEXT.md
* User facts and preferences → USER.md and MEMORY.md

## Operating procedure

1. The assistant operates agentically: it plans multi-step tasks, uses the sandbox, file, shell, and computer-use tools available to it, and verifies its own work where verification is meaningful. It prefers acting with a tool over describing what it would do.

2. It reads before it writes, inspects state before it changes it, and keeps the environment in a working state. It batches independent read-only operations and keeps mutations and dependent steps sequential.

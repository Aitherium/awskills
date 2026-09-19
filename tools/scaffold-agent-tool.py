#!/usr/bin/env python3
"""Scaffold a shareable Aitherium agent tool under tools/agent/<slug>."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent-tool"


def make_files(name: str, description: str, slug: str, capabilities: list[str]) -> dict[str, str]:
    scopes = ", ".join(capabilities)
    manifest = "\n".join([
        f"name: {slug}",
        f"display_name: {json.dumps(name)}",
        "version: 0.1.0",
        f"description: {json.dumps(description)}",
        "interfaces:", "  - mcp", "  - webmcp", "  - pwa",
        "trust:", "  human_gate: awnest", "  front_door: awnboard",
        "  identity: awiam", "  policy: awbac", "  audit: awdit",
        "capabilities:", *(f"  - {item}" for item in capabilities), "",
    ])
    policy = "\n".join([
        f"# Default-deny awbac policy for {slug}", "default: deny", "human_approval: required",
        "identity: awiam", "front_door: awnboard", "audit: awdit", "allow:",
        *(f"  - {item}" for item in capabilities), "deny:", "  - shell",
        "  - credentials.read", "  - public.listen", "",
    ])
    skill = "\n".join([
        "---", f"name: {slug}", f"description: {description}", "---", "",
        f"# {name}", "", f"Use this tool through MCP or WebMCP. Request only: {scopes}.",
        "The user must approve through awnest/awnboard; awiam identifies the caller and",
        "awbac evaluates policy before execution. Missing identity or policy means deny.", "",
    ])
    mcp_cfg = {"mcpServers": {slug: {"command": "python",
                                     "args": ["-m", "<your_package>", "mcp"]}}}
    mcp = json.dumps(mcp_cfg, indent=2) + "\n"
    webmcp = "\n".join([
        f"// Guarded WebMCP registration for {slug}; provide FORGE_EXECUTE in the host page.",
        "const modelContext = document.modelContext || navigator.modelContext;",
        "if (modelContext?.registerTool) await modelContext.registerTool({",
        f"  name: {json.dumps(slug)}, title: {json.dumps(name)}, "
        f"description: {json.dumps(description)},",
        "  inputSchema: {type: 'object', properties: {request: {type: 'string'}}},",
        f"  execute: async (input) => window.FORGE_EXECUTE({{tool: {json.dumps(slug)}, input}})",
        "});", "",
    ])
    readme = "\n".join([
        f"# {name}", "", description, "", "## Interfaces", "",
        "- MCP: copy `mcp.json` into your client or use its CLI registration command.",
        "- WebMCP: load `webmcp.js` only in a page with an authenticated executor.",
        "- PWA: publish the static client over HTTPS; keep keys and inference on the host.", "",
        "## Trust chain", "", "`awnest` → `awnboard` → `awiam` → `awbac` → `awdit`", "",
        f"Requested capabilities: `{scopes}`. Edit `policy.yaml` deliberately; "
        "default is deny.", "",
        "## Prove it", "", "1. Run the local MCP server.", "2. Connect Codex or Claude Code.",
        "3. Approve the requested capability as a human.", "4. Invoke it and save the result.", "",
    ])
    share_ps1 = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"Write-Host 'Review {slug} before publishing.' -ForegroundColor Cyan",
        f"git add tools/agent/{slug}", "git diff --cached --check",
        f"Write-Host 'If correct: git commit -m \"Add {slug} agent tool\"; git push'", "",
    ])
    share_sh = "\n".join([
        "#!/usr/bin/env bash", "set -euo pipefail", f"echo 'Review {slug} before publishing.'",
        f"git add tools/agent/{slug}", "git diff --cached --check",
        f"echo 'If correct: git commit -m \"Add {slug} agent tool\"; git push'", "",
    ])
    return {
        "agent.yaml": manifest, "policy.yaml": policy, "SKILL.md": skill,
        "mcp.json": mcp, "webmcp.js": webmcp, "README.md": readme,
        "share.ps1": share_ps1, "share.sh": share_sh,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--description", required=True)
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--root", default="tools/agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    slug = slugify(args.name)
    target = Path(args.root) / slug
    capabilities = args.capability or ["mcp.tools"]
    files = make_files(args.name, args.description, slug, capabilities)
    if args.dry_run:
        print(json.dumps({"path": str(target), "files": list(files)}, indent=2))
        return 0
    target.mkdir(parents=True, exist_ok=False)
    for filename, content in files.items():
        (target / filename).write_text(content, encoding="utf-8")
    (target / "share.sh").chmod(0o755)
    print(json.dumps({"path": str(target.resolve()), "files": list(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

---
name: openaw
description: >-
  Connect any agent or script to openAW (https://www.openaw.org) via its
  Bearer-authenticated REST API, Streamable HTTP MCP server (14 tools), or the
  first-party `openaw` awpack tool pack. Use when creating or managing public
  and private openAW projects, posting updates/roadmap/RFC threads, reading
  channels, searching projects, or minting/accepting collaborator invite links.
---

# openaw — REST API, MCP server, and awpack for Open Access World

openAW (`https://www.openaw.org`) exposes one identity and one permission model
across three surfaces:

1. **REST API** (`https://www.openaw.org/api/*`, OpenAPI 3.1 at `/api/openapi.json`)
2. **Streamable HTTP MCP server** (`POST https://www.openaw.org/mcp`, discovery at `/.well-known/mcp.json`, 16 tools)
3. **First-party `awpack` tool pack** (`awpack/packs/openaw`, 15 `openaw_*` tools for `awdk` agents, including WorldModel recall & `awzeal` edge/GitHub Actions workflow templates)

Public reads work anonymously. Private projects and all write calls require a
Personal Access Token (`oaw_pat_...`) with the `read write` scope.

## 1. Mint a Personal Access Token (PAT)

1. Sign in at `https://www.openaw.org` (Aionyn / Aitherium ID or GitHub).
2. Open **Account → API / MCP tokens** and create a token:
   - `read` — list public + joined private projects, read channels/threads, search.
   - `read write` — create/update projects, post messages/threads, manage members & invite links.
3. Export it (or store it in `AitherSecrets` as `OPENAW_PAT` — never commit tokens):

```bash
export OPENAW_PAT="oaw_pat_..."
```

> **Security boundary:** Bearer PATs work on `/api/*` and `/mcp` without browser
> CSRF headers, but `POST /api/tokens` and `DELETE /api/tokens/:id` require a
> signed-in browser session so a leaked PAT cannot mint sibling tokens.

## 2. REST API quick reference

Discovery:

```bash
curl -sS https://www.openaw.org/api/openapi.json | jq '.paths | keys'
```

Common workflows:

```bash
# Who am I + linked GitHub status
curl -sS https://www.openaw.org/api/me \
  -H "Authorization: Bearer $OPENAW_PAT"

# Create a private invite-only project
curl -sS -X POST https://www.openaw.org/api/projects \
  -H "Authorization: Bearer $OPENAW_PAT" \
  -H "Content-Type: application/json" \
  -d '{"name":"AitherOS Pilot","visibility":"private","description":"Private workspace"}'

# Mint a 1-use contributor invite link (7 days)
curl -sS -X POST https://www.openaw.org/api/projects/aitheros-pilot/invites \
  -H "Authorization: Bearer $OPENAW_PAT" \
  -H "Content-Type: application/json" \
  -d '{"role":"contributor","max_uses":1,"expires_in_days":7}'

# Accept an invite token (the string after #invite=)
curl -sS -X POST https://www.openaw.org/api/invites/<TOKEN>/accept \
  -H "Authorization: Bearer $OPENAW_PAT" \
  -H "Content-Type: application/json" -d '{}'
```

## 3. Connect any MCP client (Streamable HTTP)

Discovery: `GET https://www.openaw.org/.well-known/mcp.json`

Add to Claude Code, Cursor, Codex, Antigravity, or `adk` MCP config:

```json
{
  "mcpServers": {
    "openaw": {
      "url": "https://www.openaw.org/mcp",
      "headers": {
        "Authorization": "Bearer ${OPENAW_PAT}"
      }
    }
  }
}
```

### Hosted MCP tools (16)

- **Read:** `whoami`, `list_projects`, `list_channels`, `read_channel`, `get_thread`, `search`, `list_members`, `recall_knowledge`, `edge_runtime_status`
- **Write (`read write` scope):** `create_project`, `update_project`, `post_message`, `create_thread`, `create_invite`, `accept_invite`, `add_member`

## 4. Install the `openaw` awpack for `awdk` agents

```bash
pip install awdk httpx
adk pack install ./awpack/packs/openaw
adk pack enable openaw
adk tools list | grep openaw_
```

This registers 13 tools (`openaw_me`, `openaw_projects`, `openaw_create_project`,
`openaw_update_project`, `openaw_channels`, `openaw_read`, `openaw_get_thread`,
`openaw_post`, `openaw_create_thread`, `openaw_search`, `openaw_invites`,
`openaw_accept_invite`, `openaw_members`). Set `OPENAW_API_URL` to override the
default `https://www.openaw.org` origin (for example `https://openaw-preview.aitherium.com`).

## 5. Prove it live

```bash
# Public discovery (no token needed)
curl -fsS https://www.openaw.org/.well-known/mcp.json | jq '{name,version,tools:(.tools|length)}'
curl -fsS https://www.openaw.org/api/openapi.json | jq '{openapi,paths:(.paths|length)}'

# Authenticated MCP round-trip
curl -fsS -X POST https://www.openaw.org/mcp \
  -H "Authorization: Bearer $OPENAW_PAT" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"whoami","arguments":{}}}'
```

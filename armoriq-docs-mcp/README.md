# ArmorIQ Docs MCP Server

An MCP server that provides tools for searching and browsing the [ArmorIQ documentation](https://docs.armoriq.ai).

## Tools

| Tool | Description |
|------|-------------|
| `search_armoriq_docs` | Search the docs index by keyword or natural language |
| `get_armoriq_doc_page` | Fetch the full content of a specific doc page |
| `list_armoriq_doc_pages` | List all available documentation pages |
| `get_armoriq_quickstart` | Get a condensed SDK quick-start guide |
| `get_armoriq_architecture` | Get the platform architecture overview |

## Setup in Kiro

Add this to your `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "armoriq-docs": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to>/armoriq-docs-mcp", "python", "server.py"],
      "disabled": false,
      "autoApprove": [
        "search_armoriq_docs",
        "list_armoriq_doc_pages",
        "get_armoriq_doc_page",
        "get_armoriq_quickstart",
        "get_armoriq_architecture"
      ]
    }
  }
}
```

Replace `<path-to>` with the absolute path to this directory.

## Running standalone

```bash
cd armoriq-docs-mcp
uv run python server.py
```

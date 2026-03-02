"""Custom tools exposed via an in-process MCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_agent_sdk import create_sdk_mcp_server, tool

from openclaw.memory.store import MemoryStore

if TYPE_CHECKING:
    from openclaw.memory.vector_store import VectorMemoryStore


def build_memory_tools(
    store: MemoryStore,
    vector_store: VectorMemoryStore | None = None,
):
    """Create MCP tools for reading and writing agent memory.

    The tools receive a ``_user_id`` parameter injected by the engine
    so each user's memories are isolated.
    """

    @tool(
        "memory_read",
        "Read a value from the user's persistent memory by key.",
        {"key": str, "_user_id": int},
    )
    async def memory_read(args: dict) -> dict:
        key = args["key"]
        user_id = args.get("_user_id", 0)
        value = store.read(user_id, key)
        if value is None:
            return {
                "content": [
                    {"type": "text", "text": f"No memory found for key: {key}"}
                ]
            }
        return {"content": [{"type": "text", "text": value}]}

    @tool(
        "memory_write",
        "Save a value to the user's persistent memory under a key.",
        {"key": str, "value": str, "_user_id": int},
    )
    async def memory_write(args: dict) -> dict:
        key = args["key"]
        value = args["value"]
        user_id = args.get("_user_id", 0)
        store.write(user_id, key, value)
        return {
            "content": [
                {"type": "text", "text": f"Saved to memory: {key}"}
            ]
        }

    @tool(
        "memory_list",
        "List all keys stored in the user's persistent memory.",
        {"_user_id": int},
    )
    async def memory_list(args: dict) -> dict:
        user_id = args.get("_user_id", 0)
        keys = store.list_keys(user_id)
        if not keys:
            return {
                "content": [{"type": "text", "text": "Memory is empty."}]
            }
        formatted = "\n".join(f"- {k}" for k in keys)
        return {
            "content": [{"type": "text", "text": f"Stored keys:\n{formatted}"}]
        }

    tools_list = [memory_read, memory_write, memory_list]

    if vector_store is not None:

        @tool(
            "memory_search",
            "Search the user's memories by semantic similarity. Returns the most relevant stored memories.",
            {"query": str, "_user_id": int},
        )
        async def memory_search(args: dict) -> dict:
            query = args["query"]
            user_id = args.get("_user_id", 0)
            results = vector_store.search(user_id, query)
            if not results:
                return {
                    "content": [
                        {"type": "text", "text": "No matching memories found."}
                    ]
                }
            lines = []
            for r in results:
                lines.append(f"- **{r['key']}**: {r['value']} (distance: {r['distance']})")
            return {
                "content": [
                    {"type": "text", "text": "Matching memories:\n" + "\n".join(lines)}
                ]
            }

        tools_list.append(memory_search)

    return create_sdk_mcp_server(
        "memory-tools",
        tools=tools_list,
    )

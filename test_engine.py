"""Integration test: verify AgentEngine can send a prompt and get a response."""

import asyncio
import os
import sys
import traceback

# Allow running inside Claude Code session
os.environ.pop("CLAUDECODE", None)

print("=== test_engine.py starting ===", flush=True)


async def test_engine() -> None:
    try:
        from openclaw.config import load_config
        from openclaw.agent.engine import AgentEngine

        config = load_config("config.yaml")
        engine = AgentEngine(config.agent, config.safety)

        print("Sending test prompt to AgentEngine...", flush=True)
        response = await engine.send_and_collect(
            "Reply with exactly: HELLO_TEST_OK",
            cwd=".",
        )
        print(f"session_id: {response.session_id}", flush=True)
        print(f"text: {response.text!r}", flush=True)
        print(f"raw_messages count: {len(response.raw_messages)}", flush=True)

        assert response.text and len(response.text) > 0, "Empty response"
        assert response.session_id is not None, "No session_id captured"
        print("\n=== TEST PASSED ===", flush=True)
    except Exception as e:
        print(f"\n=== TEST FAILED ===", flush=True)
        print(f"Error type: {type(e).__name__}", flush=True)
        print(f"Error: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_engine())

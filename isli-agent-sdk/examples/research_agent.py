import asyncio
import os
import sys
from pathlib import Path

# Add src to path so we can run from example dir without installing
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from isli_agent import AgentRunner, AgentConfig

load_dotenv()

async def web_search(query: str):
    """Mock web search tool."""
    print(f"DEBUG: web_search called with query='{query}'")
    return (
        f"Search results for: {query}\n"
        "1. ISLI (Intelligent System for Local Intelligence) is a modular multi-agent system.\n"
        "2. The system uses a 'Keeper' sidecar for local context summarization.\n"
        "3. Agents communicate via a real-time Kanban board powered by Redis."
    )

WEB_SEARCH_DEF = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for information about ISLI or other topics.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    }
}

async def main():
    # Use environment variables or defaults
    agent_id = os.getenv("AGENT_ID", "agent-research-test")
    model_provider = os.getenv("MODEL_PROVIDER", "ollama")
    model_id = os.getenv("MODEL_ID", "qwen2.5:7b")
    core_url = os.getenv("ISLI_CORE_URL", "http://localhost:8000")

    config = AgentConfig(
        id=agent_id,
        name="Research Specialist",
        description=(
            "You are a meticulous research specialist. "
            "When asked about ISLI, use the web_search tool to get accurate information. "
            "Always cite your findings."
        ),
        model_provider=model_provider,
        model_id=model_id,
        skills=["web-search"],
        heartbeat_interval=30
    )
    
    runner = AgentRunner(config, core_url)
    runner.add_tool("web_search", web_search, WEB_SEARCH_DEF)
    
    print(f"--- ISLI Agent Starting ---")
    print(f"ID:       {config.id}")
    print(f"Model:    {config.model_provider}/{config.model_id}")
    print(f"Core URL: {core_url}")
    print(f"---------------------------")
    
    try:
        await runner.start()
    except KeyboardInterrupt:
        print("\nStopping agent...")
        await runner.stop()
    except Exception as e:
        print(f"\nError: {e}")
        await runner.stop()

if __name__ == "__main__":
    asyncio.run(main())

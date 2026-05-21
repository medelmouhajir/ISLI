import asyncio
import os
import sys
import structlog
from pathlib import Path

# Add src to path so we can run from example dir without installing
sys.path.append(str(Path(__file__).parent.parent / "src"))

from isli_agent import AgentRunner, AgentConfig, CoreClient

logger = structlog.get_logger()


async def main():
    agent_id = os.getenv("AGENT_ID")
    if not agent_id:
        if len(sys.argv) > 1:
            agent_id = sys.argv[1]
        else:
            print("Usage: python start_agent.py <AGENT_ID>")
            print("   or: AGENT_ID=kimi-02 python start_agent.py")
            sys.exit(1)

    core_url = os.getenv("CORE_API_URL", "http://localhost:8000")
    admin_key = os.getenv("ADMIN_API_KEY")

    logger.info("agent_startup.fetching_config", agent_id=agent_id, core_url=core_url)

    # Fetch agent config from Core
    client = CoreClient(core_url, admin_key=admin_key)
    try:
        agent_data = await client.client.get(f"/v1/agents/{agent_id}")
        agent_data.raise_for_status()
        data = agent_data.json()
    except Exception as e:
        logger.error("agent_startup.fetch_failed", agent_id=agent_id, error=str(e))
        sys.exit(1)
    finally:
        await client.close()

    # Build AgentConfig dynamically from fetched data
    config = AgentConfig(
        id=data["id"],
        name=data["name"],
        description=data.get("description") or "",
        persona=data.get("persona") or "",
        model_provider=data.get("model_provider") or os.getenv("MODEL_PROVIDER", "ollama"),
        model_id=data.get("model_id") or os.getenv("MODEL_ID", "qwen2.5:7b"),
        channels=data.get("channels") or [],
        skills=data.get("skills") or [],
        config=data.get("config") or {},
        token_budget=data.get("token_budget"),
        heartbeat_interval=int(os.getenv("HEARTBEAT_INTERVAL", "180")),
    )

    runner = AgentRunner(config, core_url, admin_key=admin_key)

    logger.info(
        "agent_startup.ready",
        agent_id=config.id,
        model=f"{config.model_provider}/{config.model_id}",
        core_url=core_url,
    )

    try:
        await runner.start()
    except KeyboardInterrupt:
        logger.info("agent_shutdown.sigint")
        await runner.stop()
    except Exception as e:
        logger.error("agent_fatal_error", error=str(e))
        await runner.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

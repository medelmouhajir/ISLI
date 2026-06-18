import asyncio
import os
import signal
import sys
import structlog
from pathlib import Path

# Add src to path so we can run from example dir without installing
sys.path.append(str(Path(__file__).parent.parent / "src"))

from isli_agent import AgentRunner, AgentConfig, CoreClient

logger = structlog.get_logger()

# Docker stop_timeout is 30s (configured by Core). We must always exit
# before Docker escalates to SIGKILL, so guard runner.stop() with a hard
# ceiling slightly under that.
_SHUTDOWN_TIMEOUT_S = 25


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

    # Fetch agent config from Core (internal /config endpoint returns resolved API key)
    client = CoreClient(core_url, admin_key=admin_key)
    try:
        headers = {}
        if admin_key:
            headers["Authorization"] = f"Bearer {admin_key}"

        agent_data = await client.client.get(f"/v1/agents/{agent_id}/config", headers=headers)
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
        turn_token_cap=data.get("turn_token_cap"),
        api_key=data.get("api_key"),
        api_base=data.get("api_base"),
        heartbeat_interval=int(os.getenv("HEARTBEAT_INTERVAL", "600")),
    )

    runner = AgentRunner(config, core_url, admin_key=admin_key)

    logger.info(
        "agent_startup.ready",
        agent_id=config.id,
        model=f"{config.model_provider}/{config.model_id}",
        core_url=core_url,
    )

    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(runner.start())

    def _on_signal(signum: int):
        sig_name = signal.Signals(signum).name
        logger.info("agent_shutdown.signal_received", signal=sig_name)
        main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _on_signal(s))

    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("agent_shutdown.cancelled")
    except Exception as e:
        logger.error("agent_fatal_error", error=str(e))
    finally:
        # Guard runner.stop() with a hard timeout so Docker never escalates to SIGKILL.
        try:
            await asyncio.wait_for(runner.stop(), timeout=_SHUTDOWN_TIMEOUT_S)
            logger.info("agent_shutdown.clean")
        except asyncio.TimeoutError:
            logger.warning(
                "agent_shutdown.forced",
                reason="runner.stop() exceeded timeout",
                timeout_s=_SHUTDOWN_TIMEOUT_S,
            )


if __name__ == "__main__":
    asyncio.run(main())

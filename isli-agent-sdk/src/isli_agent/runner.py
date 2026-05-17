import asyncio
import json
import structlog
import websockets
from typing import Any, Callable, Dict, List, Optional
from litellm import acompletion

from .client import CoreClient
from .models import AgentConfig, Task

logger = structlog.get_logger()

class AgentRunner:
    """
    The Opinionated ISLI Agent Runner.
    Automates heartbeats, WebSocket connectivity, context injection,
    and the ReAct execution loop with dual-checkpointing.
    """
    
    def __init__(self, config: AgentConfig, core_url: str, admin_key: Optional[str] = None):
        self.config = config
        self.core_url = core_url
        self.client = CoreClient(core_url, admin_key=admin_key)
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._running = False

    def add_tool(self, name: str, func: Callable, definition: Dict[str, Any]):
        """Register a tool with the agent."""
        self.tools[name] = func
        self.tool_definitions.append(definition)

    async def start(self):
        """Start the agent: registration, heartbeat, and WebSocket listener."""
        self._running = True
        logger.info("runner.starting", agent_id=self.config.id)
        
        # 1. Register with Core
        await self.client.register(self.config)
        
        # 2. Start heartbeat loop in background
        asyncio.create_task(self._heartbeat_loop())
        
        # 3. Start WebSocket listener (main loop)
        await self._ws_loop()

    async def _heartbeat_loop(self):
        """Background loop to maintain agent's online status."""
        while self._running:
            try:
                await self.client.heartbeat(self.config.id)
                logger.debug("runner.heartbeat_success", agent_id=self.config.id)
            except Exception as e:
                logger.error("runner.heartbeat_failed", error=str(e))
            await asyncio.sleep(self.config.heartbeat_interval)

    async def _ws_loop(self):
        """WebSocket listener for incoming task assignments."""
        retry_delay = 1.0
        max_delay = 60.0
        
        while self._running:
            token = self.client.token
            if not token:
                await asyncio.sleep(1)
                continue

            ws_url = self.core_url.replace("http", "ws") + f"/v1/ws/agents/{self.config.id}?token={token}"
            try:
                async with websockets.connect(ws_url) as websocket:
                    logger.info("runner.ws_connected", url=self.core_url + f"/v1/ws/agents/{self.config.id}")
                    retry_delay = 1.0  # Reset delay on success
                    async for message in websocket:
                        event = json.loads(message)
                        if event["type"] in ("task:created", "task:updated", "task:moved"):
                            task_data = event["payload"]["task"]
                            if task_data["status"] == "inbox":
                                logger.info("runner.task_detected", task_id=task_data["id"])
                                asyncio.create_task(self._execute_task(task_data["id"]))
            except Exception as e:
                if self._running:
                    logger.error("runner.ws_error", error=str(e), next_retry=retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

    async def _execute_task(self, task_id: str):
        """Execute a single task using the ReAct pattern."""
        logger.info("runner.executing_task", task_id=task_id)
        try:
            # 1. Transition task to 'doing'
            await self.client.move_task(task_id, "doing")
            
            # 2. Fetch full task details
            task = await self.client.get_task(task_id)
            
            # 3. Get latest context injection (routes through Core to Keeper)
            context_summary = await self.client.get_context(
                self.config.id, 
                task.description or task.title,
                session_id=task.session_id
            )
            
            system_prompt = f"{self.config.description}\n\nContext:\n{context_summary}"
            messages = [{"role": "user", "content": task.input}]
            
            turn_number = 0
            while True:
                turn_number += 1
                logger.info("runner.turn_start", task_id=task_id, turn=turn_number)
                
                # 4. LLM Completion via LiteLLM
                response = await acompletion(
                    model=f"{self.config.model_provider}/{self.config.model_id}",
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    tools=self.tool_definitions if self.tool_definitions else None
                )
                
                choice = response.choices[0]
                message = choice.message
                
                # Convert message to dict for storage
                msg_dict = message.model_dump()
                # LiteLLM sometimes has extra fields, ensure clean dict
                if "tool_calls" in msg_dict and msg_dict["tool_calls"] is None:
                    del msg_dict["tool_calls"]
                
                messages.append(msg_dict)
                
                if not message.tool_calls:
                    # Final response received
                    await self.client.complete_task(task_id, message.content or "")
                    logger.info("runner.task_success", task_id=task_id)
                    break
                
                # 5. Handle Tool Execution
                # CHECKPOINT 1: Pre-Execution (As required by Plan Phase 4)
                await self.client.save_checkpoint(
                    task_id, 
                    turn_number, 
                    messages, 
                    tool_calls=[tc.model_dump() for tc in message.tool_calls]
                )
                
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    logger.info("runner.invoking_tool", tool=tool_name, args=tool_args)
                    try:
                        tool_func = self.tools.get(tool_name)
                        if not tool_func:
                            result = f"Error: Tool {tool_name} not found"
                        else:
                            if asyncio.iscoroutinefunction(tool_func):
                                result = await tool_func(**tool_args)
                            else:
                                result = tool_func(**tool_args)
                    except Exception as e:
                        result = f"Error executing tool: {str(e)}"
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result)
                    })
                
                # CHECKPOINT 2: Post-Execution (As required by Plan Phase 4)
                await self.client.save_checkpoint(task_id, turn_number, messages)
                
        except Exception as e:
            logger.error("runner.task_fatal_error", task_id=task_id, error=str(e))
            await self.client.complete_task(task_id, f"Fatal error: {str(e)}", status="failed")

    async def stop(self):
        """Gracefully stop the agent."""
        self._running = False
        await self.client.close()

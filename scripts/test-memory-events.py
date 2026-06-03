import asyncio
import json
import redis.asyncio as redis
import os

async def simulate_memory_events():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url)
    
    agent_id = "test-agent-001"
    session_id = "sess-abc-123"

    # 1. Simulate Journal Update
    journal_event = {
        "type": "memory:journal_updated",
        "payload": {
            "session_id": session_id,
            "agent_id": agent_id,
            "old_journal": "The user is interested in Python.\nThey have a cat named Luna.",
            "new_journal": "The user is interested in Python and Rust.\nThey have a cat named Luna.\nThey live in Paris."
        }
    }
    
    # 2. Simulate Context Injection
    injection_event = {
        "type": "memory:context_injected",
        "payload": {
            "session_id": session_id,
            "agent_id": agent_id,
            "retrieved_memories": [
                {
                    "id": "mem-1",
                    "content": "User mentioned liking Rust in the last session.",
                    "similarity_score": 0.89,
                    "tier": "episodic"
                },
                {
                    "id": "mem-2",
                    "content": "Luna is a black cat.",
                    "similarity_score": 0.72,
                    "tier": "episodic"
                }
            ],
            "total_injected_tokens": 450,
            "threshold_used": 0.65,
            "fallback_triggered": False
        }
    }

    # 3. Simulate Truncation
    truncation_event = {
        "type": "memory:context_truncated",
        "payload": {
            "agent_id": agent_id,
            "session_id": session_id,
            "warning_message": "Context window exceeded while assembling agent history. Pruning oldest episodic memories to fit.",
            "tokens_before": 2400,
            "tokens_after": 1800
        }
    }

    print(f"Publishing events for agent: {agent_id}...")
    
    await client.publish("isli:events", json.dumps(journal_event))
    print("Sent: memory:journal_updated")
    await asyncio.sleep(1)
    
    await client.publish("isli:events", json.dumps(injection_event))
    print("Sent: memory:context_injected")
    await asyncio.sleep(1)
    
    await client.publish("isli:events", json.dumps(truncation_event))
    print("Sent: memory:context_truncated")

    await client.close()

if __name__ == "__main__":
    asyncio.run(simulate_memory_events())

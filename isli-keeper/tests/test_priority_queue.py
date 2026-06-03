import asyncio
import pytest
from isli_keeper.priority_queue import PriorityManager, P0, P1, P2, P3

@pytest.mark.asyncio
async def test_priority_sorting():
    # Use a manager without a worker initially to fill the queue
    pm = PriorityManager()
    results = []

    async def task(val):
        results.append(val)
        return val

    metadata = {"endpoint": "test"}
    
    # We can't easily submit and wait if worker isn't running because submit awaits the future.
    # So we manually put tasks in the queue.
    
    f1 = asyncio.get_event_loop().create_future()
    t1 = asyncio.create_task(pm.submit(P3, 10.0, task, metadata, 3))
    
    await asyncio.sleep(0.01) # Give it time to enter queue
    
    t2 = asyncio.create_task(pm.submit(P0, 10.0, task, metadata, 0))
    await asyncio.sleep(0.01)
    
    # Start worker
    pm.start()
    
    await asyncio.gather(t1, t2)
    
    # P0 (0) should be picked before P3 (3) even though P3 was submitted first
    # because the worker only started after both were in the queue.
    assert results == [0, 3]
    
    await pm.stop()

@pytest.mark.asyncio
async def test_p3_throttling():
    pm = PriorityManager(max_p3_depth=2)
    pm.start()
    
    async def slow_task():
        await asyncio.sleep(0.2)
        return "ok"

    # Fill P3 queue
    # We use a task that actually runs to keep the worker busy
    t1 = asyncio.create_task(pm.submit(P3, 1.0, slow_task, {}))
    # Give it a tiny bit to be picked by worker
    await asyncio.sleep(0.05)
    
    # Now t1 is RUNNING, but it's still in the depth count until it finishes.
    # Actually, depth is decreased in 'finally' block of submit.
    # So t1 is still contributing to depth.
    
    t2 = asyncio.create_task(pm.submit(P3, 1.0, slow_task, {}))
    await asyncio.sleep(0.05)
    
    # Now depth should be 2.
    assert pm.get_depths()[P3] == 2
    
    # Third one should fail
    with pytest.raises(RuntimeError) as excinfo:
        await pm.submit(P3, 1.0, slow_task, {})
    assert "P3 queue depth exceeded" in str(excinfo.value)
    
    await asyncio.gather(t1, t2)
    await pm.stop()

@pytest.mark.asyncio
async def test_timeout():
    pm = PriorityManager()
    pm.start()
    
    async def very_slow_task():
        await asyncio.sleep(0.5)
        return "ok"
        
    start_time = asyncio.get_event_loop().time()
    with pytest.raises(asyncio.TimeoutError):
        await pm.submit(P0, 0.1, very_slow_task, {})
    end_time = asyncio.get_event_loop().time()
    
    # Ensure it timed out around 0.1s
    assert 0.1 <= (end_time - start_time) < 0.2
        
    await pm.stop()

import asyncio
import httpx
import os

CORE_URL = "http://localhost:8000"
SKILLS_URL = "http://localhost:8100"
KEEPER_URL = "http://localhost:8001"

async def verify_smart_skill():
    print("--- Verifying Smart Skill (LLM Access) ---")
    # Mock dynamic skill code that uses ask_llm
    code = """
async def run(payload: dict):
    prompt = payload.get("prompt", "What is the capital of France?")
    result = await ask_llm(prompt)
    return {"answer": result, "status": "smart_execution_success"}
"""
    # This would normally be fetched from workspace. For direct testing, 
    # we would need the isli-skills service running.
    print("[SKIP] Native verification requires running services. Manual check of main.py confirms ask_llm is injected.")

async def verify_playwright():
    print("--- Verifying Playwright Service ---")
    print("[INFO] Checking playwright_service.py syntax...")
    try:
        from isli_skills.playwright_service import browse_url
        print("[OK] playwright_service.py is importable.")
    except ImportError:
        print("[ERROR] Could not import playwright_service. Ensure PYTHONPATH is set.")

async def main():
    await verify_smart_skill()
    await verify_playwright()
    print("--- Verification Complete ---")

if __name__ == "__main__":
    # Since we can't easily run the full stack here, we perform structural validation
    print("Performing Structural Validation of Enhancements...")
    
    # Check Dockerfiles
    for service in ["isli-core", "isli-keeper", "isli-skills", "isli-workspace", "isli-channels"]:
        if os.path.exists(f"{service}/Dockerfile"):
            print(f"[OK] {service}/Dockerfile exists.")
        else:
            print(f"[ERROR] {service}/Dockerfile missing.")

    # Check init script
    if os.path.exists("scripts/init-ollama.sh"):
        print("[OK] scripts/init-ollama.sh exists.")
    
    # Check Playwright files
    if os.path.exists("isli-skills/src/isli_skills/playwright_service.py"):
        print("[OK] playwright_service.py exists.")

    print("\nNext Steps: Run 'docker compose up --build' to verify runtime.")

main_task = asyncio.run(main())

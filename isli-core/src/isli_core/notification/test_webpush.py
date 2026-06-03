#!/usr/bin/env python3
"""Test script to verify web push delivery end-to-end.

Usage inside core container:
    docker compose exec core python /app/test_webpush.py
"""

import asyncio
import json
import base64
from pywebpush import webpush, WebPushException
from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.models import WebPushSubscription
from sqlalchemy import select

settings = get_settings()

print("=" * 60)
print("Web Push Delivery Test")
print("=" * 60)

# Verify VAPID keys
print(f"\nVAPID Public Key:  {settings.vapid_public_key[:20]}...")
print(f"VAPID Private Key: {settings.vapid_private_key[:20]}...")
print(f"VAPID Claims Email: {settings.vapid_claims_email}")

# Check key lengths
try:
    pub_bytes = base64.urlsafe_b64decode(settings.vapid_public_key + "=")
    priv_bytes = base64.urlsafe_b64decode(settings.vapid_private_key + "=")
    print(f"Public key decoded length: {len(pub_bytes)} bytes (expect 65)")
    print(f"Private key decoded length: {len(priv_bytes)} bytes (expect 32)")
except Exception as e:
    print(f"WARNING: VAPID key decode error: {e}")

async def test_all_subscriptions():
    async with get_db_session_manual() as session:
        result = await session.execute(select(WebPushSubscription))
        subs = result.scalars().all()
        print(f"\nFound {len(subs)} subscription(s):")
        for sub in subs:
            print(f"  user_id={sub.user_id}, endpoint={sub.endpoint[:60]}...")
            print(f"  p256dh={sub.p256dh[:30]}...")
            print(f"  auth={sub.auth[:20]}...")

        if not subs:
            print("\nERROR: No subscriptions found in database!")
            return

        vapid_claims = {"sub": f"mailto:{settings.vapid_claims_email}"}
        payload_json = json.dumps({
            "title": "TEST NOTIFICATION",
            "body": "If you see this, web push is working!",
            "data": {"test": True}
        })

        print(f"\nSending test push to {len(subs)} subscription(s)...")
        for sub in subs:
            print(f"\n--- Testing subscription for user_id={sub.user_id} ---")
            try:
                resp = webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=payload_json,
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims=vapid_claims,
                )
                print(f"  SUCCESS: HTTP {resp.status_code}")
                print(f"  Response body: {resp.text!r}")
            except WebPushException as exc:
                print(f"  WebPushException: {exc}")
                if exc.response:
                    print(f"  HTTP Status: {exc.response.status_code}")
                    print(f"  Response body: {exc.response.text[:500]!r}")
            except Exception as exc:
                print(f"  Unexpected error: {type(exc).__name__}: {exc}")

async def main():
    from isli_core.db import init_db
    await init_db(get_settings().database_url)
    await test_all_subscriptions()

if __name__ == "__main__":
    asyncio.run(main())
    print("\n" + "=" * 60)
    print("Test complete. Check your devices for the 'TEST NOTIFICATION'.")
    print("=" * 60)

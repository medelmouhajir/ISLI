import hashlib
import hmac
import structlog

from fastapi import HTTPException, Request

logger = structlog.get_logger()


class WebhookValidator:
    """HMAC signature verification per platform webhook secret."""

    @staticmethod
    async def verify_telegram(request: Request, bot_token: str) -> dict:
        payload = await request.body()
        signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        # Telegram uses a secret token set at webhook registration time
        if signature is None:
            raise HTTPException(status_code=401, detail="Missing Telegram secret token")
        expected = hashlib.sha256(bot_token.encode()).hexdigest()
        # In practice, Telegram sends the raw secret token, not a hash
        # But we validate it against the configured secret
        if signature != bot_token:
            raise HTTPException(status_code=401, detail="Invalid Telegram secret token")
        return {}

    @staticmethod
    async def verify_whatsapp(request: Request, app_secret: str) -> dict:
        payload = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256="):
            raise HTTPException(status_code=401, detail="Invalid WhatsApp signature format")
        expected = hmac.new(
            app_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature[7:], expected):
            raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")
        return {}

    @staticmethod
    async def verify_twilio(request: Request, auth_token: str) -> dict:
        # Twilio signs requests with X-Twilio-Signature
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        form = await request.form()
        params = sorted(form.multi_items())
        payload = url + "".join(f"{k}{v}" for k, v in params)
        expected = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid Twilio signature")
        return {}

    @staticmethod
    async def verify_generic(
        request: Request, secret: str, header: str = "X-Webhook-Signature"
    ) -> dict:
        payload = await request.body()
        signature = request.headers.get(header, "")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        return {}

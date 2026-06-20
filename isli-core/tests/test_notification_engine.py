"""Tests for the notification engine channel routing and channel suppression."""

from typing import Any

import pytest

from isli_core.notification.notification_engine import (
    DEFAULT_CATEGORIES,
    NotificationEngine,
    _event_category_key,
    _external_channels_for_event,
    _flatten_payload,
)


class TestEventCategoryKey:
    def test_web_session_maps_to_session_message(self):
        assert _event_category_key("session:message", {"channel": "web"}) == "session_message"
        assert _event_category_key("session:message", {"channel": None}) == "session_message"
        assert _event_category_key("session:message", {}) == "session_message"

    def test_telegram_maps_to_channel_message(self):
        assert _event_category_key("session:message", {"channel": "telegram"}) == "channel_message"

    def test_whatsapp_maps_to_channel_message(self):
        assert _event_category_key("session:message", {"channel": "whatsapp"}) == "channel_message"

    def test_email_maps_to_channel_message(self):
        assert _event_category_key("session:message", {"channel": "email"}) == "channel_message"

    def test_non_session_event_uses_mapping(self):
        assert _event_category_key("agent:crash", {}) == "agent_crash"
        assert _event_category_key("task:completed", {}) == "task_completed"


class TestFlattenPayload:
    def test_channel_suffix_for_external_channel(self):
        flat = _flatten_payload({"channel": "telegram"})
        assert flat["channel_suffix"] == " on Telegram"

    def test_channel_suffix_empty_for_web(self):
        flat = _flatten_payload({"channel": "web"})
        assert flat["channel_suffix"] == ""

    def test_channel_suffix_empty_when_missing(self):
        flat = _flatten_payload({"message": "hello"})
        assert flat["channel_suffix"] == ""

    def test_flatten_payload_session_messages_list(self):
        payload = {
            "channel": "telegram",
            "user_id": "+12345",
            "messages": [
                {"role": "user", "content": "Hello user messages", "timestamp": "2026-06-19T20:00:00Z"}
            ]
        }
        flat = _flatten_payload(payload)
        assert flat["sender_name"] == "+12345"
        assert flat["last_message_content"] == "Hello user messages"
        assert flat["last_message_role"] == "user"

    def test_flatten_payload_session_single_message(self):
        payload = {
            "channel": "whatsapp",
            "user_id": "+54321",
            "message": {
                "role": "assistant",
                "content": "Hi from agent",
            }
        }
        flat = _flatten_payload(payload)
        assert flat["sender_name"] == "+54321"
        assert flat["last_message_content"] == "Hi from agent"
        assert flat["last_message_role"] == "assistant"


class TestExternalChannelsForEvent:
    def test_filters_in_app(self):
        pref = {"enabled": True, "channels": ["in_app", "web_push", "telegram"]}
        assert _external_channels_for_event(pref) == ["web_push", "telegram"]

    def test_empty_when_only_in_app(self):
        pref = {"enabled": True, "channels": ["in_app"]}
        assert _external_channels_for_event(pref) == []


class TestDefaultCategories:
    def test_channel_message_present(self):
        assert "channel_message" in DEFAULT_CATEGORIES
        assert DEFAULT_CATEGORIES["channel_message"]["enabled"] is True
        assert "web_push" in DEFAULT_CATEGORIES["channel_message"]["channels"]

    def test_session_message_unchanged(self):
        assert "session_message" in DEFAULT_CATEGORIES
        assert DEFAULT_CATEGORIES["session_message"]["channels"] == ["in_app", "web_push"]

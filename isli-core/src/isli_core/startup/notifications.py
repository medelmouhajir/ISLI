"""Startup-time notification handler registration."""

import structlog

logger = structlog.get_logger()


def register_notification_handlers():
    from isli_core.jobs.outbox_worker import register_outbox_handler
    from isli_core.notification.delivery import deliver_in_app
    from isli_core.notification.delivery_external import deliver_external
    from isli_core.notification.delivery_webpush import deliver_web_push

    register_outbox_handler("notification:in_app", deliver_in_app)
    register_outbox_handler("notification:external", deliver_external)
    register_outbox_handler("notification:web_push", deliver_web_push)
    logger.info("startup.notification_handlers_registered")

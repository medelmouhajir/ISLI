from .workspace import (
    file_read,
    file_write,
    file_list,
    file_delete,
    FILE_READ_DEF,
    FILE_WRITE_DEF,
    FILE_LIST_DEF,
    FILE_DELETE_DEF,
    WorkspacePathError,
    WorkspaceQuotaError,
    WorkspaceNotFoundError,
    WorkspacePermissionError,
)
from .channels import send_message, SEND_MESSAGE_DEF
from .system import get_current_datetime, shell_exec, DATETIME_DEF, SHELL_EXEC_DEF
from .web import web_fetch, WEB_FETCH_DEF, web_search, WEB_SEARCH_DEF
from .keeper import (
    summarize_text,
    embed_text,
    summarize,
    translate,
    SUMMARIZE_TEXT_DEF,
    EMBED_TEXT_DEF,
    SUMMARIZE_DEF,
    TRANSLATE_DEF,
)
from .memory import (
    memory_save,
    memory_delete,
    memory_search,
    MEMORY_SAVE_DEF,
    MEMORY_DELETE_DEF,
    MEMORY_SEARCH_DEF,
)

__all__ = [
    "file_read",
    "file_write",
    "file_list",
    "file_delete",
    "FILE_READ_DEF",
    "FILE_WRITE_DEF",
    "FILE_LIST_DEF",
    "FILE_DELETE_DEF",
    "WorkspacePathError",
    "WorkspaceQuotaError",
    "WorkspaceNotFoundError",
    "WorkspacePermissionError",
    "send_message",
    "SEND_MESSAGE_DEF",
    "get_current_datetime",
    "shell_exec",
    "DATETIME_DEF",
    "SHELL_EXEC_DEF",
    "web_fetch",
    "WEB_FETCH_DEF",
    "web_search",
    "WEB_SEARCH_DEF",
    "summarize_text",
    "embed_text",
    "summarize",
    "translate",
    "SUMMARIZE_TEXT_DEF",
    "EMBED_TEXT_DEF",
    "SUMMARIZE_DEF",
    "TRANSLATE_DEF",
    "memory_save",
    "memory_delete",
    "memory_search",
    "MEMORY_SAVE_DEF",
    "MEMORY_DELETE_DEF",
    "MEMORY_SEARCH_DEF",
    "SKILL_TOOL_REGISTRY",
    "normalize_skill_name",
]


def normalize_skill_name(skill_name: str) -> str:
    """Normalize a Core skill name to a Python-identifier tool name."""
    return skill_name.replace("-", "_")


SKILL_TOOL_REGISTRY: dict[str, tuple] = {
    "send_message": (send_message, SEND_MESSAGE_DEF),
    "shell_exec": (shell_exec, SHELL_EXEC_DEF),
    "web_fetch": (web_fetch, WEB_FETCH_DEF),
    "web_search": (web_search, WEB_SEARCH_DEF),
    "summarize_text": (summarize_text, SUMMARIZE_TEXT_DEF),
    "embed_text": (embed_text, EMBED_TEXT_DEF),
    "summarize": (summarize, SUMMARIZE_DEF),
    "translate": (translate, TRANSLATE_DEF),
    "file_read": (file_read, FILE_READ_DEF),
    "file_write": (file_write, FILE_WRITE_DEF),
    "file_list": (file_list, FILE_LIST_DEF),
    "file_delete": (file_delete, FILE_DELETE_DEF),
    "memory_save": (memory_save, MEMORY_SAVE_DEF),
    "memory_delete": (memory_delete, MEMORY_DELETE_DEF),
    "memory_search": (memory_search, MEMORY_SEARCH_DEF),
}

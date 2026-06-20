from .audio import (
    SEND_VOICE_MESSAGE_DEF,
    SPEECH_TO_TEXT_DEF,
    TEXT_TO_SPEECH_DEF,
    send_voice_message,
    speech_to_text,
    text_to_speech,
)
from .channels import (
    SEND_MESSAGE_DEF,
    STAGE_REPLY_ATTACHMENT_DEF,
    send_message,
    stage_reply_attachment,
)
from .db_query import DB_QUERY_DEF, db_query
from .debugger import (
    INTERACTIVE_DEBUGGER_DEF,
    interactive_debugger,
)
from .discover_skills import (
    DISCOVER_SKILLS_DEF,
    discover_skills,
)
from .document_manager import GENERATE_DOCUMENT_DEF, generate_document
from .engineering import (
    PLAN_DEF,
    REGISTER_SKILL_DEF,
    TEST_SKILL_DEF,
    UPDATE_SKILL_DEF,
    create_engineering_plan,
    register_skill,
    test_skill,
    update_skill,
)
from .git import (
    GIT_BRANCH_CREATE_DEF,
    GIT_BRANCH_LIST_DEF,
    GIT_CHECKOUT_DEF,
    GIT_CLONE_DEF,
    GIT_COMMIT_DEF,
    GIT_LOG_DEF,
    GIT_PULL_DEF,
    GIT_PUSH_DEF,
    GIT_STATUS_DEF,
    GitAuthError,
    GitConflictError,
    GitInvalidOperationError,
    GitNotRepoError,
    GitRemoteError,
    git_branch_create,
    git_branch_list,
    git_checkout,
    git_clone,
    git_commit,
    git_log,
    git_pull,
    git_push,
    git_status,
)
from .kanban import (
    CREATE_KANBAN_TASK_DEF,
    LIST_KANBAN_TASKS_DEF,
    UPDATE_KANBAN_TASK_DEF,
    create_kanban_task,
    list_kanban_tasks,
    update_kanban_task,
)
from .keeper import (
    EMBED_TEXT_DEF,
    SUMMARIZE_DEF,
    SUMMARIZE_TEXT_DEF,
    TRANSLATE_DEF,
    embed_text,
    summarize,
    summarize_text,
    translate,
)
from .memory import (
    MEMORY_DELETE_DEF,
    MEMORY_SAVE_DEF,
    MEMORY_SEARCH_DEF,
    memory_delete,
    memory_save,
    memory_search,
)
from .notifications import (
    NOTIFY_USER_DEF,
    NotificationDeliveryError,
    NotificationRateLimitError,
    notify_user,
)
from .packages import (
    PIP_INSTALL_DEF,
    PIP_LIST_DEF,
    PackageInstallError,
    PackageInvalidError,
    PackageTimeoutError,
    pip_install,
    pip_list,
)
from .secrets import (
    GET_SECRET_DEF,
    SecretAccessError,
    SecretNotFoundError,
    get_secret,
)
from .system import DATETIME_DEF, SHELL_EXEC_DEF, get_current_datetime, shell_exec
from .ui_renderer import (
    RENDER_UI_COMPONENT_DEF,
    UI_RENDERING_INSTRUCTIONS,
    render_ui_component,
)
from .web import (
    BROWSER_BACK_DEF,
    BROWSER_CLICK_DEF,
    BROWSER_CONSOLE_DEF,
    BROWSER_GET_IMAGES_DEF,
    BROWSER_NAVIGATE_DEF,
    BROWSER_PRESS_DEF,
    BROWSER_SCROLL_DEF,
    BROWSER_SNAPSHOT_DEF,
    BROWSER_TYPE_DEF,
    BROWSER_VISION_DEF,
    WEB_FETCH_DEF,
    WEB_SEARCH_DEF,
    browser_back,
    browser_click,
    browser_console,
    browser_get_images,
    browser_navigate,
    browser_press,
    browser_scroll,
    browser_snapshot,
    browser_type,
    browser_vision,
    web_fetch,
    web_search,
)
from .workspace import (
    ATTACH_TO_TASK_DEF,
    DESCRIBE_WORKSPACE_FILE_DEF,
    FILE_DELETE_DEF,
    FILE_LIST_DEF,
    FILE_READ_DEF,
    FILE_WRITE_DEF,
    PROMOTE_OUTPUT_DEF,
    PULL_TASK_ATTACHMENT_DEF,
    READ_WORKSPACE_FILE_DEF,
    SEARCH_WORKSPACE_FILE_DEF,
    SHARED_FILE_DELETE_DEF,
    SHARED_FILE_LIST_DEF,
    SHARED_FILE_MOVE_DEF,
    SHARED_FILE_READ_DEF,
    SHARED_FILE_WRITE_DEF,
    SHARED_PROMOTE_FILE_WORKSPACE_DEF,
    SHARED_WORKSPACE_INFO_DEF,
    SHARED_WORKSPACE_SEARCH_DEF,
    WorkspaceNotFoundError,
    WorkspacePathError,
    WorkspacePermissionError,
    WorkspaceQuotaError,
    attach_to_task,
    describe_workspace_file,
    file_delete,
    file_list,
    file_read,
    file_write,
    promote_output,
    pull_task_attachment,
    read_workspace_file,
    search_workspace_file,
    shared_file_delete,
    shared_file_list,
    shared_file_move,
    shared_file_read,
    shared_file_write,
    shared_promote_file_workspace,
    shared_workspace_info,
    shared_workspace_search,
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
    "attach_to_task",
    "ATTACH_TO_TASK_DEF",
    "pull_task_attachment",
    "PULL_TASK_ATTACHMENT_DEF",
    "promote_output",
    "PROMOTE_OUTPUT_DEF",
    "shared_promote_file_workspace",
    "SHARED_PROMOTE_FILE_WORKSPACE_DEF",
    "shared_file_read",
    "SHARED_FILE_READ_DEF",
    "shared_file_write",
    "SHARED_FILE_WRITE_DEF",
    "shared_file_list",
    "SHARED_FILE_LIST_DEF",
    "shared_file_delete",
    "SHARED_FILE_DELETE_DEF",
    "shared_file_move",
    "SHARED_FILE_MOVE_DEF",
    "shared_workspace_info",
    "SHARED_WORKSPACE_INFO_DEF",
    "shared_workspace_search",
    "SHARED_WORKSPACE_SEARCH_DEF",
    "WorkspacePathError",
    "WorkspaceQuotaError",
    "WorkspaceNotFoundError",
    "WorkspacePermissionError",
    "send_message",
    "SEND_MESSAGE_DEF",
    "stage_reply_attachment",
    "STAGE_REPLY_ATTACHMENT_DEF",
    "get_current_datetime",
    "shell_exec",
    "DATETIME_DEF",
    "SHELL_EXEC_DEF",
    "web_fetch",
    "WEB_FETCH_DEF",
    "web_search",
    "WEB_SEARCH_DEF",
    "browser_navigate",
    "BROWSER_NAVIGATE_DEF",
    "browser_snapshot",
    "BROWSER_SNAPSHOT_DEF",
    "browser_click",
    "BROWSER_CLICK_DEF",
    "browser_type",
    "BROWSER_TYPE_DEF",
    "browser_press",
    "BROWSER_PRESS_DEF",
    "browser_scroll",
    "BROWSER_SCROLL_DEF",
    "browser_back",
    "BROWSER_BACK_DEF",
    "browser_console",
    "BROWSER_CONSOLE_DEF",
    "browser_vision",
    "BROWSER_VISION_DEF",
    "browser_get_images",
    "BROWSER_GET_IMAGES_DEF",
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
    "create_kanban_task",
    "CREATE_KANBAN_TASK_DEF",
    "list_kanban_tasks",
    "LIST_KANBAN_TASKS_DEF",
    "update_kanban_task",
    "UPDATE_KANBAN_TASK_DEF",
    "generate_document",
    "GENERATE_DOCUMENT_DEF",
    "create_engineering_plan",
    "PLAN_DEF",
    "test_skill",
    "TEST_SKILL_DEF",
    "register_skill",
    "REGISTER_SKILL_DEF",
    "update_skill",
    "UPDATE_SKILL_DEF",
    "interactive_debugger",
    "INTERACTIVE_DEBUGGER_DEF",
    "speech_to_text",
    "text_to_speech",
    "send_voice_message",
    "SPEECH_TO_TEXT_DEF",
    "TEXT_TO_SPEECH_DEF",
    "SEND_VOICE_MESSAGE_DEF",
    "render_ui_component",
    "RENDER_UI_COMPONENT_DEF",
    "UI_RENDERING_INSTRUCTIONS",
    "db_query",
    "DB_QUERY_DEF",
    "git_clone",
    "git_status",
    "git_commit",
    "git_push",
    "git_pull",
    "git_branch_list",
    "git_branch_create",
    "git_checkout",
    "git_log",
    "GIT_CLONE_DEF",
    "GIT_STATUS_DEF",
    "GIT_COMMIT_DEF",
    "GIT_PUSH_DEF",
    "GIT_PULL_DEF",
    "GIT_BRANCH_LIST_DEF",
    "GIT_BRANCH_CREATE_DEF",
    "GIT_CHECKOUT_DEF",
    "GIT_LOG_DEF",
    "GitNotRepoError",
    "GitAuthError",
    "GitConflictError",
    "GitRemoteError",
    "GitInvalidOperationError",
    "pip_install",
    "pip_list",
    "PIP_INSTALL_DEF",
    "PIP_LIST_DEF",
    "PackageInstallError",
    "PackageInvalidError",
    "PackageTimeoutError",
    "get_secret",
    "GET_SECRET_DEF",
    "SecretNotFoundError",
    "SecretAccessError",
    "notify_user",
    "NOTIFY_USER_DEF",
    "NotificationRateLimitError",
    "NotificationDeliveryError",
    "discover_skills",
    "DISCOVER_SKILLS_DEF",
    "SKILL_TOOL_REGISTRY",
    "SKILL_CATEGORY_MAP",
    "normalize_skill_name",
    "fetch_dynamic_tools",
]


def normalize_skill_name(skill_name: str) -> str:
    """Normalize a Core skill name to a Python-identifier tool name."""
    return skill_name.replace("-", "_")


async def fetch_dynamic_tools(core_client) -> tuple[dict[str, tuple], dict[str, list[str]]]:
    """Fetch skills from Core and generate tool bindings for any not in the static registry.

    Returns a tuple of:
      - tool_name -> (invoker_function, definition_dict)
      - normalized_skill_name -> list of tool_names belonging to that skill
    """
    from typing import Callable

    try:
        resp = await core_client.client.get("/v1/skills", headers=core_client._get_headers())
        resp.raise_for_status()
    except Exception:
        return {}, {}

    skills = resp.json()
    dynamic: dict[str, tuple[Callable, dict]] = {}
    skill_tools_map: dict[str, list[str]] = {}

    for skill in skills:
        skill_name = skill.get("name", "")
        skill_type = skill.get("type", "external")
        if skill_type == "inline":
            continue

        tools = skill.get("tools", [])
        if not tools and skill.get("manifest"):
            tools = skill["manifest"].get("tools", [])

        normalized_skill = normalize_skill_name(skill_name)

        for tool in tools:
            tool_name = tool.get("name", "")
            if not tool_name or tool_name in SKILL_TOOL_REGISTRY:
                continue

            definition = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }

            endpoint = tool.get("endpoint", tool_name)
            _skill_name = skill_name
            _endpoint = endpoint

            def _make_invoker(sn: str, ep: str):
                async def _invoker(agent_id: str, core_client=None, **kwargs):
                    if core_client is None:
                        raise RuntimeError("core_client is required for dynamic skill invocation")
                    payload = {"agent_id": agent_id, **kwargs}
                    resp = await core_client.client.post(
                        f"/v1/skills/{sn}/{ep.lstrip('/')}",
                        json=payload,
                        headers=core_client._get_headers(),
                    )
                    resp.raise_for_status()
                    return resp.json()
                return _invoker

            invoker = _make_invoker(_skill_name, _endpoint)
            dynamic[tool_name] = (invoker, definition)
            skill_tools_map.setdefault(normalized_skill, []).append(tool_name)

    return dynamic, skill_tools_map


# Core hyphenated names (e.g. web-browse-navigate) normalize to keys that may
# differ from SDK registry keys.  This map resolves those mismatches.
SKILL_NAME_ALIASES: dict[str, str] = {
    "web_browse_navigate": "browser_navigate",
    "web_browse_snapshot": "browser_snapshot",
    "web_browse_click": "browser_click",
    "web_browse_type": "browser_type",
    "web_browse_press": "browser_press",
    "web_browse_scroll": "browser_scroll",
    "web_browse_back": "browser_back",
    "web_browse_console": "browser_console",
    "web_browse_vision": "browser_vision",
    "web_browse_images": "browser_get_images",
    "files_documents_manager": "generate_document",
    "file_search": "search_workspace_file",
    "file_describe": "describe_workspace_file",
}


SKILL_TOOL_REGISTRY: dict[str, tuple] = {
    "send_message": (send_message, SEND_MESSAGE_DEF),
    "stage_reply_attachment": (stage_reply_attachment, STAGE_REPLY_ATTACHMENT_DEF),
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
    "describe_workspace_file": (describe_workspace_file, DESCRIBE_WORKSPACE_FILE_DEF),
    "search_workspace_file": (search_workspace_file, SEARCH_WORKSPACE_FILE_DEF),
    "read_workspace_file": (read_workspace_file, READ_WORKSPACE_FILE_DEF),
    "attach_to_task": (attach_to_task, ATTACH_TO_TASK_DEF),
    "pull_task_attachment": (pull_task_attachment, PULL_TASK_ATTACHMENT_DEF),
    "promote_output": (promote_output, PROMOTE_OUTPUT_DEF),
    "shared_promote_file_workspace": (shared_promote_file_workspace, SHARED_PROMOTE_FILE_WORKSPACE_DEF),
    "shared_file_read": (shared_file_read, SHARED_FILE_READ_DEF),
    "shared_file_write": (shared_file_write, SHARED_FILE_WRITE_DEF),
    "shared_file_list": (shared_file_list, SHARED_FILE_LIST_DEF),
    "shared_file_delete": (shared_file_delete, SHARED_FILE_DELETE_DEF),
    "shared_file_move": (shared_file_move, SHARED_FILE_MOVE_DEF),
    "shared_workspace_info": (shared_workspace_info, SHARED_WORKSPACE_INFO_DEF),
    "shared_workspace_search": (shared_workspace_search, SHARED_WORKSPACE_SEARCH_DEF),
    "memory_save": (memory_save, MEMORY_SAVE_DEF),
    "memory_delete": (memory_delete, MEMORY_DELETE_DEF),
    "memory_search": (memory_search, MEMORY_SEARCH_DEF),
    "create_kanban_task": (create_kanban_task, CREATE_KANBAN_TASK_DEF),
    "list_kanban_tasks": (list_kanban_tasks, LIST_KANBAN_TASKS_DEF),
    "update_kanban_task": (update_kanban_task, UPDATE_KANBAN_TASK_DEF),
    "generate_document": (generate_document, GENERATE_DOCUMENT_DEF),
    "create_engineering_plan": (create_engineering_plan, PLAN_DEF),
    "test_skill": (test_skill, TEST_SKILL_DEF),
    "register_skill": (register_skill, REGISTER_SKILL_DEF),
    "update_skill": (update_skill, UPDATE_SKILL_DEF),
    "interactive_debugger": (interactive_debugger, INTERACTIVE_DEBUGGER_DEF),
    "speech_to_text": (speech_to_text, SPEECH_TO_TEXT_DEF),
    "text_to_speech": (text_to_speech, TEXT_TO_SPEECH_DEF),
    "send_voice_message": (send_voice_message, SEND_VOICE_MESSAGE_DEF),
    "ui_components": (render_ui_component, RENDER_UI_COMPONENT_DEF),
    "db_query": (db_query, DB_QUERY_DEF),
    "git_clone": (git_clone, GIT_CLONE_DEF),
    "git_status": (git_status, GIT_STATUS_DEF),
    "git_commit": (git_commit, GIT_COMMIT_DEF),
    "git_push": (git_push, GIT_PUSH_DEF),
    "git_pull": (git_pull, GIT_PULL_DEF),
    "git_branch_list": (git_branch_list, GIT_BRANCH_LIST_DEF),
    "git_branch_create": (git_branch_create, GIT_BRANCH_CREATE_DEF),
    "git_checkout": (git_checkout, GIT_CHECKOUT_DEF),
    "git_log": (git_log, GIT_LOG_DEF),
    "pip_install": (pip_install, PIP_INSTALL_DEF),
    "pip_list": (pip_list, PIP_LIST_DEF),
    "get_secret": (get_secret, GET_SECRET_DEF),
    "notify_user": (notify_user, NOTIFY_USER_DEF),
    "browser_navigate": (browser_navigate, BROWSER_NAVIGATE_DEF),
    "browser_snapshot": (browser_snapshot, BROWSER_SNAPSHOT_DEF),
    "browser_click": (browser_click, BROWSER_CLICK_DEF),
    "browser_type": (browser_type, BROWSER_TYPE_DEF),
    "browser_press": (browser_press, BROWSER_PRESS_DEF),
    "browser_scroll": (browser_scroll, BROWSER_SCROLL_DEF),
    "browser_back": (browser_back, BROWSER_BACK_DEF),
    "browser_console": (browser_console, BROWSER_CONSOLE_DEF),
    "browser_vision": (browser_vision, BROWSER_VISION_DEF),
    "browser_get_images": (browser_get_images, BROWSER_GET_IMAGES_DEF),
    "discover_skills": (discover_skills, DISCOVER_SKILLS_DEF),
}

SKILL_CATEGORY_MAP: dict[str, str] = {
    "send_message": "communication",
    "stage_reply_attachment": "communication",
    "shell_exec": "system",
    "web_fetch": "web",
    "web_search": "web",
    "summarize_text": "content",
    "embed_text": "content",
    "summarize": "content",
    "translate": "content",
    "file_read": "workspace",
    "file_write": "workspace",
    "file_list": "workspace",
    "file_delete": "workspace",
    "describe_workspace_file": "workspace",
    "search_workspace_file": "workspace",
    "read_workspace_file": "workspace",
    "attach_to_task": "workspace",
    "pull_task_attachment": "workspace",
    "promote_output": "workspace",
    "shared_promote_file_workspace": "workspace",
    "shared_file_read": "workspace",
    "shared_file_write": "workspace",
    "shared_file_list": "workspace",
    "shared_file_delete": "workspace",
    "shared_file_move": "workspace",
    "shared_workspace_info": "workspace",
    "shared_workspace_search": "workspace",
    "memory_save": "memory",
    "memory_delete": "memory",
    "memory_search": "memory",
    "create_kanban_task": "kanban",
    "list_kanban_tasks": "kanban",
    "update_kanban_task": "kanban",
    "generate_document": "workspace",
    "create_engineering_plan": "engineering",
    "test_skill": "engineering",
    "register_skill": "engineering",
    "update_skill": "engineering",
    "interactive_debugger": "engineering",
    "speech_to_text": "audio",
    "text_to_speech": "audio",
    "send_voice_message": "audio",
    "ui_components": "system",
    "db_query": "database",
    "git_clone": "git",
    "git_status": "git",
    "git_commit": "git",
    "git_push": "git",
    "git_pull": "git",
    "git_branch_list": "git",
    "git_branch_create": "git",
    "git_checkout": "git",
    "git_log": "git",
    "pip_install": "workspace",
    "pip_list": "workspace",
    "get_secret": "system",
    "get_current_datetime": "system",
    "notify_user": "communication",
    "browser_navigate": "web",
    "browser_snapshot": "web",
    "browser_click": "web",
    "browser_type": "web",
    "browser_press": "web",
    "browser_scroll": "web",
    "browser_back": "web",
    "browser_console": "web",
    "browser_vision": "web",
    "browser_get_images": "web",
}

from typing import Any, Union
from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def generate_document(
    agent_id: str,
    format: str,
    content: Union[str, list, dict],
    filename: str,
    core_client: CoreClient
) -> dict[str, Any]:
    """
    Generate a document (PDF, DOCX, XLSX) and save it to the agent's workspace.
    
    Args:
        agent_id: The ID of the agent requesting generation.
        format: The document format ('pdf', 'docx', 'xlsx').
        content: The content to include. Markdown/HTML for PDF/DOCX, list of dicts/lists for XLSX.
        filename: The target filename in the workspace (e.g., 'reports/summary.pdf').
        core_client: The ISLI Core client.
        
    Returns:
        A dictionary containing the status and the workspace path of the generated file.
    """
    resp = await core_client.client.post(
        "/v1/skills/files-documents-manager/generate",
        json={
            "agent_id": agent_id,
            "format": format,
            "content": content,
            "filename": filename
        },
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


GENERATE_DOCUMENT_DEF = {
    "type": "function",
    "function": {
        "name": "generate_document",
        "description": _get_tool_desc(
            "generate_document",
            "Generate a PDF, DOCX, or XLSX document and save it to the workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "xlsx"],
                    "description": "The target document format."
                },
                "content": {
                    "type": "string",
                    "description": "The content to include. Markdown/HTML for PDF/DOCX, JSON string for XLSX."
                },
                "filename": {
                    "type": "string",
                    "description": "The target filename in the workspace (e.g., 'reports/summary.pdf')."
                }
            },
            "required": ["format", "content", "filename"]
        },
    },
    "x_isli_skill": "files-documents-manager",
}

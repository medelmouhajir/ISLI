import json
from typing import Any

COMPONENT_TYPES = [
    "table",
    "card",
    "button_group",
    "comparison_table",
    "form",
    "json_viewer",
    "status_timeline",
    "metric_grid",
]

UI_RENDERING_INSTRUCTIONS = """
You have access to the render_ui_component tool. Use it to present structured data
inline in the conversation. The user can interact with these components, and their
interactions will be sent back to you as new messages.

Available component types and their props schemas:

1. table
   props: {
     "columns": [{"key": "name", "label": "Product Name"}, ...],
     "rows": [{"name": "Widget A", "price": "$99"}, ...]
   }
   Interaction: user clicks a row -> you receive row_selected with row_index and row data.

2. card
   props: {
     "title": "Product Details",
     "fields": [{"label": "Name", "value": "Widget A"}, ...],
     "buttons": [{"label": "Schedule Demo", "action_type": "schedule_demo", "payload": {...}}]
   }
   Interaction: user clicks a button -> you receive button_clicked with action_type and payload.

3. button_group
   props: {
     "buttons": [{"label": "Approve", "action_type": "approve", "payload": {...}}, ...]
   }
   Interaction: user clicks a button -> you receive button_clicked with action_type and payload.

4. comparison_table
   props: {
     "headers": ["Feature", "Plan A", "Plan B"],
     "rows": [["Price", "$10/mo", "$25/mo"], ...]
   }
   Interaction: read-only. No events fired.

5. form
   props: {
     "title": "Update Profile",
     "description": "Please confirm your details.",
     "fields": [
       {"name": "full_name", "label": "Full Name", "type": "text", "required": true, "default": "Alice"},
       {"name": "age", "label": "Age", "type": "number", "required": false},
       {"name": "plan", "label": "Plan", "type": "select", "options": ["Free", "Pro", "Enterprise"], "required": true, "default": "Pro"},
       {"name": "newsletter", "label": "Subscribe to newsletter", "type": "toggle", "default": true},
       {"name": "notes", "label": "Notes", "type": "textarea", "required": false}
     ],
     "submit_label": "Save Changes"
   }
   Supported field types: text, number, select, toggle, textarea.
   Interaction: user fills fields and clicks submit -> you receive form_submitted with {values: {...}}.

6. json_viewer
   props: {
     "title": "API Response",
     "data": {"status": "ok", "items": [...]},
     "collapsed": false
   }
   Interaction: read-only. No events fired.

7. status_timeline
   props: {
     "steps": [
       {"label": "Data ingestion", "status": "completed", "detail": "12,400 rows processed"},
       {"label": "Embedding", "status": "in_progress", "detail": "Batch 3/5"},
       {"label": "Index build", "status": "pending", "detail": "Waiting..."}
     ]
   }
   Status values: completed, in_progress, pending, failed.
   Interaction: read-only. No events fired.

8. metric_grid
   props: {
     "metrics": [
       {"label": "CPU", "value": "42%", "trend": "up", "color": "amber"},
       {"label": "Memory", "value": "1.2 GB", "trend": "down", "color": "cyan"}
     ]
   }
   Trend values: up, down, flat. Color values: cyan, amber, green, red, violet.
   Interaction: read-only. No events fired.

Rules:
- Always provide an action_id when you want to receive interactions.
- Provide text_fallback for channels that cannot render components (e.g., Telegram).
- Keep props under 8KB. Paginate large tables (max 50 rows). Keep forms short (<6 fields).
- Call render_ui_component as a tool during your turn. The runner will attach the result
  to your final reply automatically.
"""


def render_ui_component(
    component_type: str,
    props: dict[str, Any],
    action_id: str | None = None,
    text_fallback: str | None = None,
) -> dict[str, Any]:
    """Render a UI component in the chat stream.

    Use this to present structured data (tables, cards, comparisons, forms, JSON,
    timelines, metrics) or action buttons inline in the conversation. The user can
    interact with the component, and those interactions will be sent back to you
    as tool results.

    Args:
        component_type: One of "table", "card", "button_group", "comparison_table",
                        "form", "json_viewer", "status_timeline", "metric_grid".
        props: Component-specific properties (see UI_RENDERING_INSTRUCTIONS).
        action_id: Unique identifier for this component instance. Required if you
                   want to receive interaction events from it.
        text_fallback: Plain-text summary for channels that cannot render components.
    """
    if component_type not in COMPONENT_TYPES:
        return {"error": f"Unknown component_type: {component_type}. Must be one of {COMPONENT_TYPES}"}

    props_json = json.dumps(props)
    if len(props_json) > 8192:
        return {"error": "Component props exceed 8KB limit. Reduce data or paginate."}

    return {
        "component_type": component_type,
        "props": props,
        "action_id": action_id,
        "text_fallback": text_fallback,
    }


RENDER_UI_COMPONENT_DEF = {
    "type": "function",
    "function": {
        "name": "ui_components",
        "description": (
            "Render a structured UI component (table, card, button_group, comparison_table, "
            "form, json_viewer, status_timeline, metric_grid) inline in the chat stream. "
            "Provide an action_id to receive user interactions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "enum": COMPONENT_TYPES,
                    "description": "Type of UI component to render.",
                },
                "props": {
                    "type": "object",
                    "description": "Component-specific properties.",
                },
                "action_id": {
                    "type": "string",
                    "description": "Unique ID for this component. User interactions will reference this ID.",
                },
                "text_fallback": {
                    "type": "string",
                    "description": "Plain-text fallback for channels that cannot render components.",
                },
            },
            "required": ["component_type", "props"],
        },
    },
}

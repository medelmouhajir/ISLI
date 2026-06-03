"""Accessibility tree snapshot — Hermes-style compact text representation.

Returns a line-oriented text view of the page where interactive elements get
reference IDs like @e1, @e2 that the agent uses for clicking and typing.
"""

from typing import Any

INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "checkbox",
    "radio",
    "combobox",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "tab",
    "treeitem",
    "spinbutton",
    "slider",
}

INTERACTIVE_TAG_FALLBACK = {
    "input",
    "textarea",
    "select",
    "button",
    "a",
}


def _node_role(node: dict[str, Any]) -> str:
    """Extract the semantic role of an accessibility node."""
    role = node.get("role", "")
    if role:
        return role
    # Fallback to tag name if Playwright didn't assign a role
    tag = node.get("tag", "").lower()
    return tag if tag in INTERACTIVE_TAG_FALLBACK else ""


def _node_name(node: dict[str, Any]) -> str:
    """Extract the accessible name (label) of a node."""
    return node.get("name", "") or node.get("value", "") or ""


def _node_value(node: dict[str, Any]) -> str:
    """Extract the current value of an input-like node."""
    return node.get("value", "") or ""


def _is_interactive(node: dict[str, Any]) -> bool:
    """Return True if the node is interactive and should get a @ref ID."""
    role = _node_role(node)
    if role in INTERACTIVE_ROLES:
        return True
    tag = node.get("tag", "").lower()
    return tag in INTERACTIVE_TAG_FALLBACK


def _format_node(node: dict[str, Any], index: int, ref_id: str | None) -> str:
    """Format a single node as a compact text line."""
    role = _node_role(node)
    name = _node_name(node)
    tag = node.get("tag", "").lower()
    value = _node_value(node)

    parts = [f"[{index}]"]

    if role:
        parts.append(role)
    elif tag:
        parts.append(tag)

    if name:
        parts.append(f'"{name}"')
    elif value:
        parts.append(f'"{value}"')

    if ref_id:
        parts.append(f"@{ref_id}")

    # Add useful attributes
    attrs: list[str] = []
    if node.get("placeholder"):
        attrs.append(f'placeholder: "{node["placeholder"]}"')
    if node.get("href"):
        attrs.append(f'href="{node["href"]}"')
    if node.get("checked"):
        attrs.append("checked")
    if node.get("disabled"):
        attrs.append("disabled")

    if attrs:
        parts.append(f"({' '.join(attrs)})")

    return " ".join(parts)


def _flatten_tree(
    node: dict[str, Any],
    lines: list[str],
    ref_counter: list[int],
    ref_map: dict[str, Any],
    full: bool,
    max_chars: int,
    current_depth: int = 0,
) -> tuple[int, bool]:
    """Recursively walk the accessibility tree and append formatted lines.

    Returns (lines_appended, truncated).
    """
    children = node.get("children", [])
    if not children:
        return 0, False

    appended = 0
    for child in children:
        # In compact mode (full=False), skip non-interactive leaf nodes
        # but always keep structural containers (heading, paragraph, list, table, etc.)
        if not full and not _is_interactive(child):
            # Still recurse in case children are interactive
            sub_appended, truncated = _flatten_tree(
                child, lines, ref_counter, ref_map, full, max_chars, current_depth + 1
            )
            appended += sub_appended
            if truncated:
                return appended, True
            continue

        ref_id: str | None = None
        if _is_interactive(child):
            ref_counter[0] += 1
            ref_id = f"e{ref_counter[0]}"
            ref_map[ref_id] = child

        ref_counter[0] += 1  # Global index counter
        line = _format_node(child, ref_counter[0], ref_id)

        # Indent for visual hierarchy if full mode
        if full and current_depth > 0:
            line = "  " * current_depth + line

        # Node-boundary truncation check
        cumulative = sum(len(line_text) + 1 for line_text in lines) + len(line)
        if cumulative > max_chars and lines:
            remaining_nodes = _count_remaining_nodes(child) + sum(
                _count_remaining_nodes(sibling) for sibling in children[children.index(child) + 1:]
            )
            lines.append(f"\n[... {remaining_nodes} more nodes omitted ...]")
            return appended, True

        lines.append(line)
        appended += 1

        # Recurse into children
        sub_appended, truncated = _flatten_tree(
            child, lines, ref_counter, ref_map, full, max_chars, current_depth + 1
        )
        appended += sub_appended
        if truncated:
            return appended, True

    return appended, False


def _count_remaining_nodes(node: dict[str, Any]) -> int:
    """Count how many nodes remain in a subtree (rough estimate)."""
    count = 1
    for child in node.get("children", []):
        count += _count_remaining_nodes(child)
    return count


async def get_snapshot(
    page,
    ref_map: dict[str, Any],
    full: bool = False,
    max_chars: int = 8000,
) -> str:
    """Return a compact accessibility-tree snapshot of the current page.

    Args:
        page: Playwright Page object.
        ref_map: Mutable dict that will be populated with ref_id -> node mapping
                 for interactive elements.
        full: If True, include all semantic nodes. If False (default), only
              interactive elements + structural headings.
        max_chars: Hard cap on snapshot length. Truncation happens at node
                   boundaries, never mid-line.

    Returns:
        Multi-line string with numbered nodes and @ref IDs for interactive elements.
    """
    ref_map.clear()
    tree = await page.accessibility.snapshot()
    if not tree:
        return "[empty page — no accessibility tree available]"

    lines: list[str] = []
    ref_counter = [0]
    _flatten_tree(tree, lines, ref_counter, ref_map, full=full, max_chars=max_chars)

    if not lines:
        return "[empty page — no visible elements]"

    return "\n".join(lines)

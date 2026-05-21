# ISLI Core API

The **Core API** is the central nervous system of ISLI. It manages agent lifecycles, task delegation, event broadcasting, and acts as a secure proxy for internal services.

## Features
- **Agent Management**: Registration, heartbeat monitoring, and status tracking.
- **Task Bus**: Real-time Kanban task management via WebSockets.
- **Security Proxy**: Securely forwards requests to internal services like `isli-workspace` and `isli-keeper`.
- **Auth**: JWT-based authentication for agents and Admin API key for the Board UI.

## New Feature: Workspace Proxy
Core now includes endpoints to manage agent workspaces securely:
- `GET /v1/workspaces/{agent_id}/list`: Proxies to workspace service with path traversal protection.
- `GET /v1/workspaces/{agent_id}/read`: Reads workspace files.
- `POST /v1/workspaces/{agent_id}/write`: Writes to workspace files.
- `DELETE /v1/workspaces/{agent_id}/delete`: Deletes workspace files.

## Security
All workspace paths are validated using `PurePosixPath` to prevent directory traversal attacks (e.g., `..` sequences or absolute paths are rejected).

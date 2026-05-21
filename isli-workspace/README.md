# ISLI Workspace Manager

The **Workspace Manager** is an internal microservice responsible for managing sandboxed file systems for ISLI agents. Each agent has its own dedicated directory where it can read, write, and list files.

## Features
- **Sandboxed Execution**: Prevents agents from accessing files outside their assigned workspace.
- **Quota Management**: Enforces storage limits per agent (default 100MB).
- **File Size Limits**: Restricts individual file sizes (default 10MB) to prevent resource exhaustion.
- **Internal API**: Exposed only to the internal network; proxied via `isli-core` for the Board UI.

## API Endpoints (Internal)
All endpoints require `X-Internal-Auth` header.

- `POST /list`: List files and directories in a workspace.
- `POST /read`: Read the content of a file.
- `POST /write`: Write or update a file.
- `POST /delete`: Delete a file.

## Configuration
- `WORKSPACE_BASE_PATH`: Root directory where all workspaces are stored.
- `MAX_WORKSPACE_SIZE_BYTES`: Total size allowed per agent workspace.
- `MAX_FILE_SIZE_BYTES`: Max size per individual file.

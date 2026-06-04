"""Service discovery for ISLI Core.

Resolves downstream service URLs from environment variables.
When ISLI eventually adopts a service mesh, swap the internal
registry for Consul / Linkerd DNS lookups.
"""
import os


class ServiceDiscovery:
    """Resolves service URLs from env vars today; mesh DNS tomorrow."""

    def __init__(self) -> None:
        self._registry: dict[str, str] = {
            "skills": os.getenv("SKILLS_URL", "http://localhost:8100"),
            "workspace": os.getenv("WORKSPACE_URL", "http://localhost:8300"),
            "audio": os.getenv("AUDIO_URL", "http://localhost:8400"),
            "keeper": os.getenv("KEEPER_URL", "http://localhost:8001"),
            "channels": os.getenv("CHANNELS_URL", "http://localhost:8200"),
        }

    def resolve(self, name: str) -> str | None:
        """Return the base URL for a downstream service, or None if unknown."""
        return self._registry.get(name)

    def all(self) -> dict[str, str]:
        """Return a copy of the full registry."""
        return self._registry.copy()

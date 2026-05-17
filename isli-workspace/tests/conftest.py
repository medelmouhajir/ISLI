import pytest
from fastapi.testclient import TestClient
from isli_workspace.main import app


@pytest.fixture
def client():
    return TestClient(app)

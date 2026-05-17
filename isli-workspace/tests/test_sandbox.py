import os
import tempfile

import pytest

from isli_workspace.sandbox import (
    MAX_FILE_SIZE_BYTES,
    MAX_WORKSPACE_SIZE_BYTES,
    resolve_path,
    write_file,
    read_file,
    list_dir,
    delete_file,
    check_quota,
)


class TestSandboxSecurity:
    @pytest.fixture(autouse=True)
    def temp_workspace(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setattr("isli_workspace.sandbox.MAX_WORKSPACE_SIZE_BYTES", 900)
            monkeypatch.setattr("isli_workspace.sandbox.MAX_FILE_SIZE_BYTES", 512)
            yield tmp

    def test_resolve_path_within_workspace(self, temp_workspace):
        path = resolve_path("agent-1", temp_workspace, "docs/readme.md")
        assert path.exists() is False
        assert str(path).startswith(str(temp_workspace))

    def test_path_traversal_blocked(self, temp_workspace):
        with pytest.raises(PermissionError):
            resolve_path("agent-1", temp_workspace, "../../../etc/passwd")

    def test_path_traversal_with_dotdot_in_middle(self, temp_workspace):
        # create a legitimate subdir first
        sub = os.path.join(temp_workspace, "agent-1", "subdir")
        os.makedirs(sub, exist_ok=True)
        with pytest.raises(PermissionError):
            resolve_path("agent-1", temp_workspace, "subdir/../../secret.txt")

    def test_file_size_limit(self, temp_workspace):
        big = "x" * 513
        with pytest.raises(ValueError, match="max file size"):
            write_file("agent-1", temp_workspace, "big.txt", big)

    def test_quota_enforcement(self, temp_workspace):
        # write a 500-byte file (under max_file=512 but uses quota)
        write_file("agent-1", temp_workspace, "f1.txt", "x" * 500)
        # second 450-byte file should exceed workspace quota of 900
        with pytest.raises(ValueError, match="quota"):
            write_file("agent-1", temp_workspace, "f2.txt", "x" * 450)

    def test_check_quota(self, temp_workspace):
        assert check_quota("agent-2", temp_workspace, 500) is True
        assert check_quota("agent-2", temp_workspace, 2000) is False

    def test_write_nested_directory(self, temp_workspace):
        result = write_file("agent-1", temp_workspace, "deep/nested/file.txt", "nested")
        assert result["status"] == "written"
        assert resolve_path("agent-1", temp_workspace, "deep/nested/file.txt").exists()

    def test_read_binary_file(self, temp_workspace):
        import struct
        binary_content = struct.pack("<I", 0xDEADBEEF)
        path = os.path.join(temp_workspace, "agent-1", "bin.dat")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(binary_content)
        result = read_file("agent-1", temp_workspace, "bin.dat")
        assert result["encoding"] == "binary"

    def test_delete_directory_not_allowed(self, temp_workspace):
        os.makedirs(os.path.join(temp_workspace, "agent-1", "mydir"), exist_ok=True)
        with pytest.raises((IsADirectoryError, OSError)):
            delete_file("agent-1", temp_workspace, "mydir")

    def test_list_directory_not_a_directory(self, temp_workspace):
        write_file("agent-1", temp_workspace, "plain.txt", "hi")
        with pytest.raises((NotADirectoryError, OSError)):
            list_dir("agent-1", temp_workspace, "plain.txt")

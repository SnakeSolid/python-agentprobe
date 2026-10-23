
import pytest

from agentprobe.errors import SandboxViolation
from agentprobe.tools.sandbox import Sandbox


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    return tmp_path


def test_resolve_ok(workspace):
    sb = Sandbox(workspace)
    assert sb.resolve("a.txt") == (workspace / "a.txt").resolve()


def test_traversal_rejected(workspace):
    sb = Sandbox(workspace)
    with pytest.raises(SandboxViolation):
        sb.resolve("../etc/passwd")


def test_symlink_escape_rejected(workspace):
    outside = workspace.parent / "outside.txt"
    outside.write_text("x")
    (workspace / "link").symlink_to(outside)
    sb = Sandbox(workspace)
    with pytest.raises(SandboxViolation):
        sb.resolve("link")


def test_absolute_inside_ok(workspace):
    sb = Sandbox(workspace)
    target = (workspace / "a.txt").resolve()
    assert sb.resolve(str(target)) == target

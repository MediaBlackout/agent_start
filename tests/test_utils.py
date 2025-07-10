from agent_start.utils import atomic_write


def test_atomic_write(tmp_path):
    file = tmp_path / "file.txt"
    atomic_write(file, "hello")
    assert file.read_text() == "hello"

from agent_start.todo_cli import TodoList


def test_add_complete(tmp_path):
    file = tmp_path / "todo.json"
    todo = TodoList(path=file)
    todo.add("demo")
    assert todo.list()[0]["text"] == "demo"
    todo.complete(0)
    assert todo.list()[0]["done"] is True

from agent_start.weather import cli


def test_cli(monkeypatch, capsys):
    async def dummy_run(zipcode):
        print({"forecast": "ok"})
    monkeypatch.setattr(cli, "_run", dummy_run)
    cli.main(["12345"], prog_name="cli")
    out = capsys.readouterr().out
    assert "forecast" in out

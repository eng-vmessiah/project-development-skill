"""Lifecycle plugin contract and integration tests."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from pd import PD, ConfigError, PDConfig, PDState


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr("pd.HOME_CONFIG", str(tmp_path / "missing-home.yaml"))
    return tmp_path


def test_all_hooks_and_snapshots(project, capsys):
    (project / "sample_plugin.py").write_text('''\nseen = []\ndef record(name, context):\n    seen.append((name, context.phase, context.phase_name, context.feature,\n                 context.feature_dir, list(context.state["tasks"])))\n    context.state["tasks"].append("plugin mutation")\nfor name in ("before_advance", "after_advance", "before_checkpoint",\n             "after_checkpoint", "before_verify", "after_verify"):\n    globals()[name] = lambda context, name=name: record(name, context)\n''')
    (project / "pd.yaml").write_text("plugins: [sample_plugin]\n")
    cli = PD()
    cli.run(["init", "example"])
    cli.run(["advance"])
    cli.run(["checkpoint", "--note", "test"])
    cli.run(["verify"])
    import sample_plugin
    assert [item[0] for item in sample_plugin.seen] == [
        "before_advance", "after_advance", "before_checkpoint", "after_checkpoint",
        "before_verify", "after_verify",
    ]
    assert [item[1] for item in sample_plugin.seen] == [0, 1, 1, 1, 1, 1]
    assert sample_plugin.seen[0][2:5] == ("Setup", "example", project / ".spec/example")
    assert all(item[5] == [] for item in sample_plugin.seen)
    assert PDState(project / ".spec/example").state["tasks"] == []
    capsys.readouterr()
    cli.run(["config", "--json"])
    assert json.loads(capsys.readouterr().out)["plugins"] == ["sample_plugin"]


@pytest.mark.parametrize("value", ["bad", "[42]", "[../bad]", "[missing_pd_plugin]"])
def test_invalid_plugins_fail_closed(project, value):
    (project / "pd.yaml").write_text(f"plugins: {value}\n")
    with pytest.raises(ConfigError):
        PDConfig(project)


def test_non_callable_hook_fails_closed(project):
    (project / "bad_plugin.py").write_text("before_verify = None\n")
    (project / "pd.yaml").write_text("plugins: [bad_plugin]\n")
    with pytest.raises(ConfigError):
        PDConfig(project)


def test_runtime_failure_warns_and_shell_runs_first(project, capsys):
    (project / "failing_plugin.py").write_text('''\ndef before_checkpoint(context):\n    assert (context.feature_dir / "shell.txt").read_text() == "shell"\n    raise ValueError("plugin boom")\n''')
    (project / "pd.yaml").write_text('''\nplugins: [failing_plugin]\nhooks:\n  before_checkpoint: ["printf shell > shell.txt"]\n''')
    cli = PD()
    cli.run(["init", "example"])
    cli.run(["checkpoint", "--note", "saved"])
    assert "plugin boom" in capsys.readouterr().out
    assert PDState(project / ".spec/example").state["checkpoints"][0]["note"] == "saved"

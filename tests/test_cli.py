import pytest
from typer.testing import CliRunner
from pipelineguard.cli.main import app

runner = CliRunner()

V1_YAML = """\
contract_id: test_contract
version: 1.0.0
owner: test-owner
description: CLI test contract
schema:
  fields:
    - name: price
      type: float
      nullable: false
"""

V2_YAML = """\
contract_id: test_contract
version: 2.0.0
owner: test-owner
description: CLI test contract v2
schema:
  fields:
    - name: price
      type: float
      nullable: false
    - name: store
      type: string
      nullable: true
"""


@pytest.fixture
def yaml_files(tmp_path):
    v1 = tmp_path / "v1.yaml"
    v1.write_text(V1_YAML)
    v2 = tmp_path / "v2.yaml"
    v2.write_text(V2_YAML)
    return {"v1": str(v1), "v2": str(v2), "db": str(tmp_path / "test.db")}


def test_register_exits_zero(yaml_files):
    result = runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output


def test_register_duplicate_exits_nonzero(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    assert result.exit_code != 0


def test_list_shows_contract_id_and_version(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "list", "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output
    assert "1.0.0" in result.output


def test_list_empty_db_exits_zero(yaml_files):
    result = runner.invoke(app, ["contract", "list", "--db", yaml_files["db"]])
    assert result.exit_code == 0


def test_show_after_register(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "show", "test_contract", "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output
    assert "test-owner" in result.output


def test_show_missing_contract_exits_nonzero(yaml_files):
    result = runner.invoke(app, ["contract", "show", "nonexistent", "--db", yaml_files["db"]])
    assert result.exit_code != 0


def test_diff_shows_added_field(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    runner.invoke(app, ["contract", "register", yaml_files["v2"], "--db", yaml_files["db"]])
    result = runner.invoke(
        app,
        ["contract", "diff", "test_contract", "--from", "1.0.0", "--to", "2.0.0", "--db", yaml_files["db"]],
    )
    assert result.exit_code == 0
    assert "store" in result.output


def test_diff_shows_breaking_change(yaml_files, tmp_path):
    # Register v1, then v3 with a type change on 'price' (breaking)
    v3_content = """\
contract_id: test_contract
version: 3.0.0
owner: test-owner
description: breaking type change
schema:
  fields:
    - name: price
      type: string
      nullable: false
"""
    v3 = tmp_path / "v3.yaml"
    v3.write_text(v3_content)

    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    runner.invoke(app, ["contract", "register", str(v3), "--db", yaml_files["db"]])
    result = runner.invoke(
        app,
        ["contract", "diff", "test_contract", "--from", "1.0.0", "--to", "3.0.0", "--db", yaml_files["db"]],
    )
    assert result.exit_code == 0
    assert "BREAKING" in result.output
    assert "price" in result.output


def test_register_missing_file_exits_nonzero(yaml_files):
    result = runner.invoke(app, ["contract", "register", "/nonexistent/path.yaml", "--db", yaml_files["db"]])
    assert result.exit_code != 0


@pytest.mark.parametrize("cmd", ["validate", "drift", "quarantine", "tune", "dashboard"])
def test_stubs_exit_zero_and_print_not_implemented(cmd):
    result = runner.invoke(app, [cmd])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output

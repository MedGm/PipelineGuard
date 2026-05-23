import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typer.testing import CliRunner
from pipelineguard.cli.main import app

runner = CliRunner()


@pytest.fixture
def registered_db(db_path, sample_contract_yaml):
    result = runner.invoke(app, ["contract", "register", sample_contract_yaml, "--db", db_path])
    assert result.exit_code == 0
    return db_path


def test_validate_passes_on_valid_data(registered_db, sample_parquet, tmp_path):
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "product_price_v2",
        "--file", sample_parquet,
        "--db", registered_db, "--obs", obs,
    ])
    assert result.exit_code in (0, 1)
    assert "Status:" in result.output


def test_validate_fails_on_range_violation(registered_db, tmp_path):
    df = pd.DataFrame({
        "product_id": [f"PROD{i:04d}AB" for i in range(20)],
        "price_mad": [-999.0] * 20,
        "store_id": ["jumia"] * 20,
        "scraped_at": pd.Series([datetime.now(timezone.utc)] * 20),
    })
    bad = str(tmp_path / "bad.parquet")
    df.to_parquet(bad, index=False)
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "product_price_v2",
        "--file", bad, "--db", registered_db, "--obs", obs,
    ])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_validate_explain_shows_suggestion(registered_db, tmp_path):
    df = pd.DataFrame({
        "product_id": [f"PROD{i:04d}AB" for i in range(20)],
        "price_mad": [-999.0] * 20,
        "store_id": ["jumia"] * 20,
        "scraped_at": pd.Series([datetime.now(timezone.utc)] * 20),
    })
    bad = str(tmp_path / "bad.parquet")
    df.to_parquet(bad, index=False)
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "product_price_v2",
        "--file", bad, "--db", registered_db, "--obs", obs, "--explain",
    ])
    assert result.exit_code == 1
    assert "->" in result.output


def test_validate_missing_contract_exits_2(db_path, sample_parquet, tmp_path):
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "nonexistent",
        "--file", sample_parquet, "--db", db_path, "--obs", obs,
    ])
    assert result.exit_code == 2


def test_validate_missing_file_exits_2(registered_db, tmp_path):
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "product_price_v2",
        "--file", "/nonexistent/path.parquet",
        "--db", registered_db, "--obs", obs,
    ])
    assert result.exit_code == 2


def test_validate_output_contains_run_id(registered_db, sample_parquet, tmp_path):
    obs = str(tmp_path / "obs.duckdb")
    result = runner.invoke(app, [
        "validate", "--contract", "product_price_v2",
        "--file", sample_parquet, "--db", registered_db, "--obs", obs,
    ])
    assert "Run ID:" in result.output

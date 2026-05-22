import pytest

@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")

@pytest.fixture
def sample_contract_yaml(tmp_path) -> str:
    content = """\
contract_id: product_price_v2
version: 2.0.0
owner: el-gorrim-mohamed
description: Scraped product prices from Moroccan e-commerce stores
schema:
  fields:
    - name: product_id
      type: string
      nullable: false
      pattern: '^[A-Z0-9]{8,16}$'
    - name: price_mad
      type: float
      nullable: false
      min: 0.01
      max: 500000.0
    - name: store_id
      type: string
      nullable: false
      allowed_values: [jumia, hmizate, avito, marjane]
    - name: scraped_at
      type: timestamp
      nullable: false
statistics:
  price_mad:
    expected_distribution: lognormal
    drift_sensitivity: medium
    outlier_zscore: 4.0
  completeness:
    min_row_count: 100
    max_null_fraction: 0.02
freshness:
  max_delay_minutes: 60
remediation:
  on_schema_violation: quarantine
  on_drift_violation: alert_and_continue
  on_freshness_violation: alert
  alert_channels: [slack_webhook, email]
  suppression_window_minutes: 30
"""
    p = tmp_path / "product_price_v2.yaml"
    p.write_text(content)
    return str(p)


@pytest.fixture
def obs_db_path(tmp_path) -> str:
    return str(tmp_path / "test_obs.duckdb")


@pytest.fixture
def sample_parquet(tmp_path) -> str:
    import pandas as pd
    import numpy as np
    from datetime import datetime, timezone, timedelta

    rng = np.random.default_rng(42)
    n = 200
    now = datetime.now(timezone.utc)
    df = pd.DataFrame({
        "product_id": [f"PROD{i:04d}AB" for i in range(n)],
        "price_mad": rng.uniform(1.0, 9000.0, n),
        "store_id": rng.choice(["jumia", "hmizate", "avito", "marjane"], n).tolist(),
        "scraped_at": pd.Series([now - timedelta(minutes=i % 20) for i in range(n)]),
    })
    path = str(tmp_path / "sample.parquet")
    df.to_parquet(path, index=False)
    return path

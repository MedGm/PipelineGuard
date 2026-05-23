import typer
import yaml
import pandas as pd
from pydantic import ValidationError
from pipelineguard.contracts.registry import ContractRegistry
from pipelineguard.exceptions import ContractNotFound, ContractVersionExists
from pipelineguard.validators.engine import Validator
from pipelineguard.store.observations import ObservationsStore

app = typer.Typer(name="pg", help="PipelineGuard — ML pipeline data contract engine")
contract_app = typer.Typer(help="Manage data contracts")
app.add_typer(contract_app, name="contract")

_DB = typer.Option("./pipelineguard.db", "--db", help="Path to PipelineGuard database")


@contract_app.command("list")
def contract_list(db: str = _DB):
    """List all registered contracts."""
    registry = ContractRegistry(db_path=db)
    summaries = registry.list()
    if not summaries:
        typer.echo("No contracts registered.")
        return
    for s in summaries:
        typer.echo(f"{s.contract_id}  {s.version}  {s.owner}  {s.description}")


@contract_app.command("show")
def contract_show(
    contract_id: str,
    version: str = typer.Option(None, "--version", help="Specific version (default: latest)"),
    db: str = _DB,
):
    """Show a contract."""
    registry = ContractRegistry(db_path=db)
    try:
        contract = registry.load(contract_id, version)
    except ContractNotFound as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{contract.contract_id}  v{contract.version}")
    typer.echo(f"Owner: {contract.owner}")
    typer.echo(f"Description: {contract.description}")
    typer.echo(f"Fields ({len(contract.schema_spec.fields)}):")
    for field in contract.schema_spec.fields:
        typer.echo(f"  {field.name}  {field.type}  nullable={field.nullable}")


@contract_app.command("register")
def contract_register(path: str, db: str = _DB):
    """Register a contract from a YAML file."""
    registry = ContractRegistry(db_path=db)
    try:
        contract = registry.register(path)
        typer.echo(f"Registered {contract.contract_id} v{contract.version}")
    except ContractVersionExists as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except (FileNotFoundError, ValidationError, yaml.YAMLError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@contract_app.command("diff")
def contract_diff(
    contract_id: str,
    from_version: str = typer.Option(..., "--from"),
    to_version: str = typer.Option(..., "--to"),
    db: str = _DB,
):
    """Diff two versions of a contract."""
    registry = ContractRegistry(db_path=db)
    try:
        diff = registry.diff(contract_id, from_version, to_version)
    except ContractNotFound as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    if diff.breaking_changes:
        typer.echo(f"{len(diff.breaking_changes)} breaking change(s):")
        for bc in diff.breaking_changes:
            typer.echo(f"  BREAKING  {bc.field_name}: {bc.detail}")
    if diff.minor_changes:
        typer.echo(f"{len(diff.minor_changes)} non-breaking change(s):")
        for mc in diff.minor_changes:
            typer.echo(f"  +  {mc}")
    if not diff.breaking_changes and not diff.minor_changes:
        typer.echo("No changes detected.")


@app.command()
def validate(
    contract_id: str = typer.Option(..., "--contract", help="Contract ID to validate against"),
    file: str = typer.Option(..., "--file", help="Path to Parquet file"),
    explain: bool = typer.Option(False, "--explain", help="Show suggestions for violations"),
    batch_id: str = typer.Option(None, "--batch-id", help="Batch identifier"),
    db: str = typer.Option("./pipelineguard.db", "--db", help="Path to PipelineGuard database"),
    obs: str = typer.Option("./observations.duckdb", "--obs", help="Path to observations DuckDB"),
):
    """Validate a dataset against a contract."""
    registry = ContractRegistry(db_path=db)
    try:
        contract = registry.load(contract_id)
    except ContractNotFound as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2)
    except Exception as e:
        typer.echo(f"Error loading contract: {e}", err=True)
        raise typer.Exit(code=2)

    try:
        df = pd.read_parquet(file)
    except FileNotFoundError:
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=2)
    except Exception as e:
        typer.echo(f"Error reading file: {e}", err=True)
        raise typer.Exit(code=2)

    store = ObservationsStore(db_path=obs)
    validator = Validator(contract=contract, obs_store=store)
    result = validator.validate(df, batch_id=batch_id)

    typer.echo(f"Run ID: {result.run_id}")
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Rows: {result.row_count}")
    typer.echo(f"Duration: {result.duration_ms:.1f}ms")

    if result.violations:
        typer.echo(f"\nViolations ({len(result.violations)}):")
        for v in result.violations:
            field_label = v.field or "(batch)"
            typer.echo(f"  [{v.severity}] {field_label}: {v.message}")
            if explain and v.suggestion:
                typer.echo(f"         -> {v.suggestion}")

    if result.status == "FAIL":
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command()
def drift():
    """[Phase 2] Show drift history."""
    typer.echo("[Phase 2] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def quarantine():
    """[Phase 3] Manage quarantined batches."""
    typer.echo("[Phase 3] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def tune():
    """[Phase 2] Tune drift thresholds."""
    typer.echo("[Phase 2] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def dashboard():
    """[Phase 5] Launch Streamlit dashboard."""
    typer.echo("[Phase 5] not yet implemented")
    raise typer.Exit(code=0)

"""
part-cli: end-user CLI for decoding and validating part numbers.

Usage:
  part-cli decode --part-number P-1001
  part-cli decode --file parts.csv --output results.json
  part-cli validate --part-number P-1001
"""
import os
import csv
import json
import sys
import time
import click
from dotenv import load_dotenv


from registry.auth import validate
from registry.logger import log_call
from registry.parts import lookup_part

load_dotenv()


def _resolve_key(api_key: str) -> str:
    key = api_key or os.getenv("PART_API_KEY")
    if not key:
        raise click.ClickException(
            "API key required. Use --api-key or set PART_API_KEY env var."
        )
    return key


@click.group()
def cli():
    pass


@cli.command()
@click.option("--part-number", "-p", help="Single part number to decode")
@click.option("--file", "-f", "input_file", type=click.Path(exists=True),
              help="CSV file of part numbers (one per line or column 'part_number')")
@click.option("--output", "-o", "output_file", help="Write results to JSON file")
@click.option("--api-key", envvar="PART_API_KEY", help="API key (or set PART_API_KEY)")
def decode(part_number, input_file, output_file, api_key):
    """Decode part number(s) — returns make, model, category, compatibility."""
    key = _resolve_key(api_key)

    try:
        team_info = validate(key, required_scope="read:parts")
    except ValueError as e:
        raise click.ClickException(str(e))

    team = team_info["team"]

    if input_file:
        _decode_batch(input_file, output_file, team)
    elif part_number:
        _decode_single(part_number, team)
    else:
        raise click.ClickException("Provide --part-number or --file.")


def _decode_single(part_number: str, team: str):
    start = time.monotonic()
    part = lookup_part(part_number)

    if not part:
        log_call(team, "cli:decode", {"part_number": part_number},
                 success=False,
                 response_ms=elapsed_ms(start),
                 error_message="Not found")
        raise click.ClickException(f"Part '{part_number}' not found in registry.")

    log_call(team, "cli:decode", {"part_number": part_number},
             success=True,
             response_ms=elapsed_ms(start))

    click.echo(json.dumps({
        "part_number": part["part_number"],
        "make":        part["make"],
        "model":       part["model"],
        "category":    part["category"],
        "compatibility": part["compatibility"],
    }, indent=2))


def _decode_batch(input_file: str, output_file: str | None, team: str):
    part_numbers = _read_part_numbers(input_file)
    total = len(part_numbers)
    results = []
    errors = []

    click.echo(f"Processing {total} part numbers...")

    batch_start = time.monotonic()

    for i, pn in enumerate(part_numbers, 1):
        part = lookup_part(pn)

        if part:
            results.append({
                "part_number":   part["part_number"],
                "make":          part["make"],
                "model":         part["model"],
                "category":      part["category"],
                "compatibility": part["compatibility"],
            })
        else:
            errors.append(pn)

        if i % 1000 == 0:
            click.echo(f"  {i}/{total} processed...")

    # Single audit log entry for the whole batch — avoids N individual INSERTs
    # that would compete with concurrent MCP and REST API connections.
    log_call(
        team=team,
        tool="batchDecode",
        input_data={"file": input_file, "total": total},
        success=True,
        response_ms=elapsed_ms(batch_start),
        error_message=f"{len(errors)} not found" if errors else None,
    )

    output = {"processed": len(results), "errors": len(errors),
              "results": results, "not_found": errors}

    if output_file:
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        click.echo(f"Done. {len(results)} decoded, {len(errors)} not found. Output: {output_file}")
    else:
        click.echo(json.dumps(output, indent=2))


def _read_part_numbers(path: str) -> list[str]:
    with open(path) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "part_number" in reader.fieldnames:
            return [row["part_number"].strip() for row in reader if row["part_number"].strip()]
    # fallback: one part number per line
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


@cli.command()
@click.option("--part-number", "-p", required=True, help="Part number to validate")
@click.option("--api-key", envvar="PART_API_KEY", help="API key (or set PART_API_KEY)")
def validate_part(part_number, api_key):
    """Validate whether a part number exists and is active."""
    key = _resolve_key(api_key)

    try:
        team_info = validate(key, required_scope="validate:parts")
    except ValueError as e:
        raise click.ClickException(str(e))

    team = team_info["team"]
    start = time.monotonic()
    part = lookup_part(part_number)
    ms = elapsed_ms(start)

    is_valid = part is not None and part["is_valid"]
    log_call(team, "cli:validate", {"part_number": part_number},
             success=True, response_ms=ms)

    click.echo(json.dumps({"part_number": part_number, "valid": is_valid}, indent=2))


if __name__ == "__main__":
    cli()

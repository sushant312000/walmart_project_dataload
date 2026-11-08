import argparse
import csv
import sys
from pathlib import Path

import psycopg
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = PROJECT_ROOT / "dataset" / "data"
SCHEMA = "walmart_schema"
TABLE_FILES = (
    ("customers", "customers.csv"),
    ("stores", "stores.csv"),
    ("products", "products.csv"),
    ("employees", "employees.csv"),
    ("orders", "orders.csv"),
    ("order_items", "order_items.csv"),
)


def load_database_url() -> str:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().removeprefix("export ").strip() == "DATABASE_URL":
            database_url = value.strip().strip("\"'")
            if database_url:
                return database_url

    raise ValueError(f"DATABASE_URL was not found in {env_file}")


def inspect_csv(path: Path) -> tuple[list[str], int]:
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        headers = next(reader, None)
        if not headers:
            raise ValueError(f"{path.name} is empty or has no header")
        if len(headers) != len(set(headers)):
            raise ValueError(f"{path.name} contains duplicate column names")

        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(headers):
                raise ValueError(
                    f"{path.name} row {row_number} has {len(row)} fields; "
                    f"expected {len(headers)}"
                )
            row_count += 1

    return headers, row_count


def table_count(cursor: psycopg.Cursor, table: str) -> int:
    query = sql.SQL("SELECT count(*) FROM {}.{}").format(
        sql.Identifier(SCHEMA), sql.Identifier(table)
    )
    return cursor.execute(query).fetchone()[0]


def validate_table(
    cursor: psycopg.Cursor, table: str, headers: list[str]
) -> None:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (SCHEMA, table),
    )
    table_columns = {row[0] for row in cursor.fetchall()}
    if not table_columns:
        raise ValueError(f"Target table {SCHEMA}.{table} does not exist")

    unknown_columns = set(headers) - table_columns
    if unknown_columns:
        raise ValueError(
            f"{SCHEMA}.{table} has no column(s): {', '.join(sorted(unknown_columns))}"
        )

    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          USING (constraint_catalog, constraint_schema, constraint_name,
                 table_schema, table_name)
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        """,
        (SCHEMA, table),
    )
    primary_key_columns = {row[0] for row in cursor.fetchall()}
    missing_key_columns = primary_key_columns - set(headers)
    if missing_key_columns:
        raise ValueError(
            f"{table}.csv is missing primary key column(s): "
            f"{', '.join(sorted(missing_key_columns))}"
        )


def copy_csv(
    cursor: psycopg.Cursor, table: str, path: Path, headers: list[str]
) -> None:
    copy_statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    ).format(
        sql.Identifier(SCHEMA),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(header) for header in headers),
    )
    with path.open("rb") as csv_file:
        with cursor.copy(copy_statement) as copy:
            while chunk := csv_file.read(1024 * 1024):
                copy.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load project CSV files into existing walmart_schema tables."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm that the CSV rows should be inserted into Neon",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("No data was inserted. Rerun with --confirm to approve the import.")

    try:
        csv_inputs = []
        for table, filename in TABLE_FILES:
            path = DATA_DIRECTORY / filename
            if not path.is_file():
                raise FileNotFoundError(f"CSV file not found: {path}")
            headers, row_count = inspect_csv(path)
            csv_inputs.append((table, path, headers, row_count))

        database_url = load_database_url()
        totals = []
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                before_counts = {}
                for table, _, headers, _ in csv_inputs:
                    validate_table(cursor, table, headers)
                    before_counts[table] = table_count(cursor, table)

                for table, path, headers, _ in csv_inputs:
                    copy_csv(cursor, table, path, headers)

                for table, _, _, expected_count in csv_inputs:
                    after_count = table_count(cursor, table)
                    loaded_count = after_count - before_counts[table]
                    if loaded_count != expected_count:
                        raise RuntimeError(
                            f"Expected to load {expected_count} rows into "
                            f"{SCHEMA}.{table}, but the table count increased by "
                            f"{loaded_count}"
                        )
                    totals.append((table, loaded_count, after_count))

        print("Import committed successfully:")
        for table, loaded_count, total_count in totals:
            print(
                f"  {SCHEMA}.{table}: loaded {loaded_count} rows; "
                f"{total_count} total rows"
            )
        return 0
    except psycopg.Error as error:
        sqlstate = error.sqlstate or "unavailable"
        message = (
            error.diag.message_primary
            if error.diag is not None
            else "connection or driver error"
        )
        print(
            f"Database import failed and was rolled back "
            f"(PostgreSQL SQLSTATE: {sqlstate}): {message}",
            file=sys.stderr,
        )
        return 1
    except (OSError, UnicodeError, csv.Error, ValueError, RuntimeError) as error:
        print(f"Import failed; no data was committed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

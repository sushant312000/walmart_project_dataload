# Walmart Data Loader

A small Python utility for loading the project's CSV datasets into existing
PostgreSQL tables, including databases hosted on Neon. The loader validates the
input files and target tables, then inserts all six datasets in one transaction.

## What it loads

| Table | CSV file | Rows |
|---|---|---:|
| `customers` | `customers.csv` | 2,000 |
| `stores` | `stores.csv` | 25 |
| `products` | `products.csv` | 500 |
| `employees` | `employees.csv` | 250 |
| `orders` | `orders.csv` | 10,000 |
| `order_items` | `order_items.csv` | 30,021 |

The target schema is `walmart_schema`. Tables are loaded in dependency order:
customers, stores, products, employees, orders, and order items.

## Project layout

```text
.
├── dataset/
│   ├── data/                 # CSV input files
│   └── ddl/
│       └── walmart_schema.sql
├── src/
│   └── de_project_1/
│       └── import_csvs.py    # Import command
├── .env                      # Local database connection; do not commit
├── pyproject.toml
└── uv.lock
```

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A reachable PostgreSQL database and a role with permission to read the
  target tables and insert rows (NEON DB)

## Set up

From the project directory:

```powershell
uv sync
```

Create a `.env` file in the project root and set your database connection URL:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Use the connection string provided by your database host. Keep `.env` private:
it is excluded from Git by `.gitignore`.

## Prepare the database

The loader expects these tables to **already exist** in the PostgreSQL schema
`walmart_schema`; it does not create or alter schemas or tables.

The supplied `dataset/ddl/walmart_schema.sql` defines the six tables, but its
`CREATE TABLE` statements are currently unqualified and it does not create the
`walmart_schema` schema. Before loading, ensure the tables have been created in
the expected schema. For example, when applying the DDL in a PostgreSQL session,
create the schema and set the search path in that same session before running
the file:

```sql
CREATE SCHEMA IF NOT EXISTS walmart_schema;
SET search_path TO walmart_schema;
```

Alternatively, qualify each DDL table name with `walmart_schema.`. The loader
also expects CSV column names to match target table columns and each CSV to
include its table's primary-key column.

## Run the import

Review the CSV files and target database first. The import requires an explicit
confirmation flag:

```powershell
uv run --locked python -m de_project_1.import_csvs --confirm
```

To see command options without connecting to the database:

```powershell
uv run --locked python -m de_project_1.import_csvs --help
```

The loader checks that all CSV files exist, validates their headers and row
shapes, verifies the target tables and primary-key columns, and then inserts
the data using PostgreSQL `COPY`. It prints the number of rows loaded and the
total row count for each table on success.

All six table loads run in a single transaction. If a database, constraint, or
row-count check fails, the transaction is rolled back. Existing rows are not
updated or replaced; a primary-key conflict fails the import. Resolve conflicts
before rerunning rather than expecting the loader to skip duplicates.

## Troubleshooting

- **`DATABASE_URL was not found`**: check that `.env` is in the project root
  and that it contains a non-empty `DATABASE_URL=...` line.
- **Target table does not exist**: confirm the tables were created in
  `walmart_schema`, not only in the database's default schema.
- **Missing or unknown columns**: compare the CSV headers with the target table
  definitions; the loader reports columns that are not present and missing
  primary-key columns.
- **Duplicate key or other PostgreSQL error**: the transaction is rolled back.
  Check existing table data and constraints before trying again.

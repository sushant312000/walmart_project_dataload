# Loading CSV data into Neon

The importer loads the six CSV files in `dataset/data` into existing tables in
the `walmart_schema` PostgreSQL schema. It inserts rows in dependency order and
uses one transaction; a primary-key, foreign-key, type, or other database error
rolls back the entire import. It does not create or alter schemas or tables.

1. Put the Neon connection string in `.env` as `DATABASE_URL=...`.
2. Install project dependencies with `uv sync`.
3. Review the CSVs and target database, then explicitly approve the insert:

   ```powershell
   uv run python -m de_project_1.import_csvs --confirm
   ```

The importer checks the target tables and CSV headers before loading, then
prints the loaded row count and resulting table count for each table. If the
CSV rows already exist, primary-key conflicts will fail and roll back the
transaction; the importer does not overwrite existing rows.
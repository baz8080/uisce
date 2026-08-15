from uisce import pipeline


def _permissive(name, declared):
    """The real declaration includes `REAL NOT NULL` on the coordinates, which a
    throwaway record of Nones would trip. These fixtures exercise the upsert's
    stamping logic, not its geometry, so every column is relaxed to TEXT — but
    the column set and order still come from pipeline.CASE_COLUMNS, which is the
    whole point: adding a column to the schema must not mean remembering to add
    it here too."""
    return "INTEGER PRIMARY KEY" if name == "id" else "TEXT"


def make_cases_table(conn):
    """A `cases` table with the declared columns and no constraints to satisfy."""
    conn.execute(f"CREATE TABLE cases ({pipeline.cases_ddl(_permissive)})")
    return conn


def case_record(**overrides):
    """A mapped case as load_cases expects one: every fed column, all None."""
    return dict.fromkeys(pipeline.DB_CASE_COLUMNS) | overrides

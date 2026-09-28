"""Koneksi Postgres dan runner migration sederhana.

uv run python -m pipeline.db migrate
"""

import sys

import psycopg

from pipeline.config import REPO_ROOT, settings

MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def connect() -> psycopg.Connection:
    if not settings.database_url:
        sys.exit("DATABASE_URL belum diisi di .env")
    # autocommit: setiap `with conn.transaction()` = satu transaksi nyata yang langsung commit,
    # jadi data chunk + checkpoint-nya tersimpan bersama walau proses dimatikan paksa.
    return psycopg.connect(settings.database_url, connect_timeout=15, autocommit=True)


def get_checkpoint(conn: psycopg.Connection, job: str) -> int | None:
    row = conn.execute(
        "select last_block from indexer_checkpoints where job_name = %s", (job,)
    ).fetchone()
    return row[0] if row else None


def set_checkpoint(conn: psycopg.Connection, job: str, block: int) -> None:
    conn.execute(
        "insert into indexer_checkpoints (job_name, last_block) values (%s, %s)"
        " on conflict (job_name)"
        " do update set last_block = excluded.last_block, updated_at = now()",
        (job, block),
    )


def migrate() -> None:
    """Jalankan file .sql yang belum pernah dijalankan, urut nama file, satu transaksi per file."""
    with connect() as conn:
        conn.execute(
            "create table if not exists schema_migrations"
            " (version text primary key, applied_at timestamptz default now())"
        )
        conn.execute("alter table schema_migrations enable row level security")
        done = {r[0] for r in conn.execute("select version from schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("insert into schema_migrations (version) values (%s)", (path.name,))
            print(f"applied {path.name}")
    print("migrations up to date")


if __name__ == "__main__":
    if sys.argv[1:] != ["migrate"]:
        sys.exit("usage: python -m pipeline.db migrate")
    migrate()

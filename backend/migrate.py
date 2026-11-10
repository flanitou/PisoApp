"""Apply additive schema changes to existing MariaDB volumes on startup."""

from pathlib import Path

from silence.db.connector import get_conn


def main():
    statements = Path("/app/db/schema.sql").read_text(encoding="utf-8").split(";")
    connection = get_conn()
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
            # CREATE TABLE IF NOT EXISTS does not change the default in an old volume.
            # Keep existing residents as hosts; only future registrations are guests.
            cursor.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'guest'")
            # Existing volumes already have actividades; CREATE TABLE IF NOT EXISTS
            # cannot add a column to them.
            cursor.execute("ALTER TABLE actividades ADD COLUMN IF NOT EXISTS generada_por_comida TINYINT(1) NOT NULL DEFAULT 0")
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    main()

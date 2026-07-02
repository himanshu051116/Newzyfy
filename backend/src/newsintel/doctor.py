import asyncio
import socket
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url

from newsintel.core.config import Settings, get_settings
from newsintel.infrastructure.db.session import Database


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    host: str
    port: int
    redacted_url: str


def database_target(settings: Settings) -> DatabaseTarget:
    url = make_url(settings.database_url)
    return DatabaseTarget(
        host=url.host or "localhost",
        port=url.port or 5432,
        redacted_url=url.render_as_string(hide_password=True),
    )


def tcp_reachable(host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


async def inspect_database(settings: Settings) -> tuple[bool, list[str]]:
    target = database_target(settings)
    messages = [f"Database target: {target.redacted_url}"]
    if not tcp_reachable(target.host, target.port):
        messages.extend(
            [
                f"[FAIL] PostgreSQL is not reachable at {target.host}:{target.port}.",
                "Start PostgreSQL before starting the API or poller.",
            ]
        )
        return False, messages

    database = Database(settings)
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
            version_table = await session.scalar(
                text("SELECT to_regclass('public.alembic_version')")
            )
            revision = (
                await session.scalar(
                    text(
                        "SELECT version_num FROM alembic_version "
                        "ORDER BY version_num DESC LIMIT 1"
                    )
                )
                if version_table
                else None
            )
            channels_table = await session.scalar(
                text("SELECT to_regclass('public.discovery_channels')")
            )
            article_versions_table = await session.scalar(
                text("SELECT to_regclass('public.article_versions')")
            )
            article_fetch_runs_table = await session.scalar(
                text("SELECT to_regclass('public.article_fetch_runs')")
            )
            article_claims_table = await session.scalar(
                text("SELECT to_regclass('public.article_claims')")
            )
            fetch_jobs_table = await session.scalar(
                text("SELECT to_regclass('public.fetch_jobs')")
            )
    except Exception as exc:
        messages.append(f"[FAIL] PostgreSQL connection failed: {type(exc).__name__}")
        return False, messages
    finally:
        await database.dispose()

    if not revision or not channels_table:
        messages.extend(
            [
                "[FAIL] PostgreSQL is reachable, but application migrations are missing.",
                "Run: .\\.venv\\Scripts\\alembic.exe -c backend\\alembic.ini upgrade head",
            ]
        )
        return False, messages

    messages.extend(
        [
            "[OK] PostgreSQL connection succeeded.",
            f"[OK] Database migration revision: {revision}",
            "[OK] Acquisition tables are available.",
            (
                "[OK] Article processing tables are available."
                if article_versions_table and article_fetch_runs_table
                else "[WARN] Article processing tables are not available yet."
            ),
            (
                "[OK] Claim/evidence lineage tables are available."
                if article_claims_table
                else "[WARN] Claim/evidence lineage tables are not available yet."
            ),
            (
                "[OK] Source dashboard/fetch job tables are available."
                if fetch_jobs_table
                else "[WARN] Source dashboard/fetch job tables are not available yet."
            ),
        ]
    )
    return True, messages


async def doctor(settings: Settings | None = None) -> bool:
    healthy, messages = await inspect_database(settings or get_settings())
    print("\n".join(messages))
    if not healthy:
        print(
            "\nFree local options:\n"
            "1. Install Docker Desktop, then run: docker compose up -d postgres\n"
            "2. Install PostgreSQL 17 locally and create the configured database/user."
        )
    return healthy


def run() -> None:
    raise SystemExit(0 if asyncio.run(doctor()) else 1)


if __name__ == "__main__":
    run()

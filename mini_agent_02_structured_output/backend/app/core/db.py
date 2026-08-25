from contextlib import contextmanager
from collections.abc import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from app.config import settings


@contextmanager
def get_conn() -> Iterator[Connection]:
    """요청 단위 PostgreSQL 연결을 열고 성공한 작업만 commit한다."""
    if not settings.parking_dsn:
        raise RuntimeError("PARKING_DSN이 설정되지 않았습니다.")
    conn = psycopg.connect(settings.parking_dsn, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping_db() -> bool:
    with get_conn() as conn:
        return conn.execute("select 1 as ok").fetchone()["ok"] == 1

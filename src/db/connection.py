import logging

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

logger = logging.getLogger(__name__)

_pool: MySQLConnectionPool | None = None


def create_pool(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    pool_size: int = 10,
) -> MySQLConnectionPool:
    global _pool
    _pool = MySQLConnectionPool(
        pool_name="fraud_pool",
        pool_size=pool_size,
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    logger.info("MySQL connection pool created: %s@%s:%d/%s", user, host, port, database)
    return _pool


def get_pool() -> MySQLConnectionPool:
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call create_pool() first.")
    return _pool

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite_pragmas(sender, connection, **kwargs):
    """
    Apply high-performance SQLite PRAGMAs:
    - WAL journal mode: Enables non-blocking concurrent reads and writes
    - synchronous=NORMAL: Safe against corruption while maximizing write throughput
    - cache_size=-64000: Allocates 64MB memory page cache
    - temp_store=MEMORY: Keeps temp tables & indexes in RAM instead of disk
    - busy_timeout=10000: Prevents 'database is locked' errors under concurrency
    - foreign_keys=ON: Enforces referential integrity
    """
    if connection.vendor == 'sqlite':
        try:
            cursor = connection.cursor()
            cursor.execute('PRAGMA journal_mode = WAL;')
            cursor.execute('PRAGMA synchronous = NORMAL;')
            cursor.execute('PRAGMA cache_size = -64000;')
            cursor.execute('PRAGMA temp_store = MEMORY;')
            cursor.execute('PRAGMA busy_timeout = 10000;')
            cursor.execute('PRAGMA foreign_keys = ON;')
        except Exception:
            pass


class MyAppConfig(AppConfig):
    name = 'MyApp'
    label = 'core'

    def ready(self):
        connection_created.connect(configure_sqlite_pragmas)
        try:
            import MyApp.signals  # noqa: F401
        except Exception as exc:
            import logging
            logging.getLogger('MyApp').error("Failed to connect cache invalidation signals: %s", exc)

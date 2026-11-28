import os
import shutil
import subprocess
import zipfile
import json
import time
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime
from django.apps import apps
from django.conf import settings
from django.db import connection, connections

_IN_PROCESS_BACKUP_LOCK = threading.Lock()
_SECRET_SUMMARY_KEYS = {
    'whatsapp_meta_access_token',
    'whatsapp_meta_webhook_token',
    'whatsapp_meta_app_secret',
    'whatsapp_bridge_token',
}
MAX_ZIP_ENTRY_BYTES = 250 * 1024 * 1024


def _sanitize_summary_settings(raw_settings: dict) -> dict:
    """Strip OTP entries and private tokens from plain-text backup summary metadata."""
    clean = {}
    for k, v in (raw_settings or {}).items():
        ks = str(k)
        if ks.startswith('dev_otp_') or ks in _SECRET_SUMMARY_KEYS:
            clean[ks] = '***REDACTED***' if v else ''
        else:
            clean[ks] = v
    return clean


@contextmanager
def _exclusive_backup_lock(backups_dir: str):
    """Cross-process + in-process exclusive lock for destructive backup/restore operations."""
    os.makedirs(backups_dir, exist_ok=True)
    lock_path = os.path.join(backups_dir, '.backup_restore.lock')
    with _IN_PROCESS_BACKUP_LOCK:
        with open(lock_path, 'a+b') as lock_f:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock_f.seek(0)
                    msvcrt.locking(lock_f.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            try:
                yield
            finally:
                try:
                    if os.name == 'nt':
                        import msvcrt
                        lock_f.seek(0)
                        msvcrt.locking(lock_f.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass


def _is_postgres():
    """Return True when Django's default database backend is PostgreSQL."""
    engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
    return 'postgresql' in engine or connection.vendor == 'postgresql'


def _get_pg_conn_details():
    """Return (db_name, cli_args, env) for pg_dump / pg_restore subprocess calls."""
    db_conf = settings.DATABASES['default']
    db_name = str(db_conf.get('NAME') or '')
    host = str(db_conf.get('HOST') or '127.0.0.1')
    port = str(db_conf.get('PORT') or '5432')
    user = str(db_conf.get('USER') or '')
    password = str(db_conf.get('PASSWORD') or '')

    args = ['-h', host, '-p', port]
    if user:
        args.extend(['-U', user])

    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password
    return db_name, args, env


def _get_db_size_bytes(db_path):
    """Return active database size in bytes for either PostgreSQL or SQLite."""
    if _is_postgres():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_database_size(current_database());")
                row = cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception:
            return 0
    return os.path.getsize(db_path) if os.path.exists(db_path) else 0


def _atomic_replace_sqlite(staging_path, target_path, max_attempts=4):
    """
    Safely closes all thread connections and atomically replaces SQLite database file on Windows.
    Dual-Mode Resilience:
    1. Mode A: Direct atomic file swap via os.replace with connection cleanup and retries.
    2. Mode B (Windows File Lock Fallback): If background Waitress worker threads hold open
       read locks preventing file deletion/replacement on Windows ([WinError 32]), falls back
       to SQLite's native in-engine online backup API (staging_conn.backup(target_conn)) which
       writes directly through SQLite's internal lock protocol without file-handle collision.
    """
    connections.close_all()
    for suffix in ('-wal', '-shm'):
        wal_p = target_path + suffix
        if os.path.exists(wal_p):
            try:
                os.remove(wal_p)
            except Exception:
                pass

    last_perm_error = None
    for attempt in range(max_attempts):
        try:
            if os.path.exists(target_path):
                os.replace(staging_path, target_path)
            else:
                shutil.move(staging_path, target_path)
            return
        except PermissionError as pe:
            last_perm_error = pe
            connections.close_all()
            time.sleep(0.15)

    # Mode B: Fallback to SQLite native in-engine overwrite if Windows locks the file
    try:
        with closing(sqlite3.connect(staging_path)) as src_conn:
            with closing(sqlite3.connect(target_path, timeout=30.0)) as dst_conn:
                src_conn.backup(dst_conn)
        # Staging file is no longer needed after successful in-engine backup
        try:
            if os.path.exists(staging_path):
                os.remove(staging_path)
        except Exception:
            pass
        return
    except Exception as fallback_err:
        if last_perm_error:
            raise last_perm_error
        raise fallback_err


def _create_online_db_snapshot(db_path, dest_path):
    """
    Creates an atomic, consistent point-in-time SQLite snapshot of the active database.
    Uses sqlite3.backup to flush all WAL pages and guarantee zero data corruption.
    """
    # 1. Flush SQLite WAL checkpoint in Django
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA wal_checkpoint(FULL);")
    except Exception:
        pass

    # 2. Use native SQLite online backup API into dest_path
    if os.path.exists(dest_path):
        try:
            os.remove(dest_path)
        except Exception:
            pass

    with closing(sqlite3.connect(db_path)) as src:
        with closing(sqlite3.connect(dest_path)) as dst:
            src.backup(dst)


def _gather_system_summary(db_path=None):
    """
    Collects a human-readable text summary of all models and key system configurations.
    Enables instant plain-text verification and inspection of the backup contents.
    """
    is_pg = _is_postgres()
    summary = {
        'generatedAt': datetime.now().isoformat(),
        'appName': 'Sutawane Classes Management Software',
        'databaseEngine': 'PostgreSQL (Django ORM)' if is_pg else 'SQLite 3 Local Persistent (Django ORM)',
        'modelCounts': {},
        'settings': {},
        'branches': [],
        'sessions': [],
        'courses': [],
    }

    if is_pg:
        try:
            core_models = apps.get_app_config('core').get_models()
            for model in core_models:
                try:
                    summary['modelCounts'][model._meta.db_table] = model._default_manager.count()
                except Exception:
                    pass
            SystemSetting = apps.get_model('core', 'SystemSetting')
            Branch = apps.get_model('core', 'Branch')
            AcademicSession = apps.get_model('core', 'AcademicSession')
            Course = apps.get_model('core', 'Course')
            summary['settings'] = _sanitize_summary_settings(dict(SystemSetting.objects.values_list('key', 'value')))
            summary['branches'] = list(Branch.objects.values('id', 'name', 'code', 'is_active'))
            summary['sessions'] = list(AcademicSession.objects.values('id', 'name', 'is_current', 'isActive'))
            summary['courses'] = list(Course.objects.values('id', 'name', 'is_active'))
        except Exception as e:
            summary['error'] = str(e)
        return summary

    if not db_path or not os.path.exists(db_path):
        return summary

    try:
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Discover all application tables
            tables = [
                r[0] for r in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]

            # Model row counts
            for tbl in tables:
                try:
                    c = cur.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    summary['modelCounts'][tbl] = c
                except Exception:
                    pass

            # Key System Settings (secrets redacted)
            if 'SystemSetting' in tables:
                try:
                    settings_rows = cur.execute('SELECT key, value FROM SystemSetting').fetchall()
                    summary['settings'] = _sanitize_summary_settings({r['key']: r['value'] for r in settings_rows})
                except Exception:
                    pass

            # Branches
            if 'Branch' in tables:
                try:
                    branches_rows = cur.execute('SELECT * FROM Branch').fetchall()
                    summary['branches'] = [dict(r) for r in branches_rows]
                except Exception:
                    pass

            # Academic Sessions
            if 'AcademicSession' in tables:
                try:
                    session_rows = cur.execute('SELECT * FROM AcademicSession').fetchall()
                    summary['sessions'] = [dict(r) for r in session_rows]
                except Exception:
                    pass

            # Courses
            if 'Course' in tables:
                try:
                    course_rows = cur.execute('SELECT * FROM Course').fetchall()
                    summary['courses'] = [dict(r) for r in course_rows]
                except Exception:
                    pass

    except Exception as e:
        summary['error'] = str(e)

    return summary


def get_storage_paths():
    """
    Returns exact storage path locations on local machine:
    - base_dir: Project root directory
    - database_path: Path to active SQLite database or PostgreSQL DSN summary
    - media_root: Root directory for all media assets
    - photos_dir: Media directory for student & branch photos
    - attachments_dir: Media directory for expense receipts & bills
    - backups_dir: Dedicated directory for persistent backup archives
    """
    base_dir = str(settings.BASE_DIR)
    if _is_postgres():
        db_conf = settings.DATABASES['default']
        db_path = (
            f"postgresql://{db_conf.get('USER', '')}@"
            f"{db_conf.get('HOST', '127.0.0.1')}:{db_conf.get('PORT', '5432')}/{db_conf.get('NAME', '')}"
        )
    else:
        db_path = str(settings.DATABASES['default']['NAME'])

    # Media directories (configured in settings.MEDIA_ROOT, defaults to /home/sutawane/media on production)
    media_root = str(getattr(settings, 'MEDIA_ROOT', os.path.join(base_dir, 'media')))
    photos_dir = os.path.join(media_root, 'photos')
    attachments_dir = os.path.join(media_root, 'attachments')

    # Backups directory (configured in settings.BACKUPS_DIR, defaults to /home/sutawane/backup_zip on production)
    if hasattr(settings, 'BACKUPS_DIR'):
        backups_dir = str(settings.BACKUPS_DIR)
    elif os.path.exists('/home/sutawane/backup_zip') or (os.name != 'nt' and os.path.exists('/home/sutawane')):
        backups_dir = '/home/sutawane/backup_zip'
    else:
        backups_dir = os.path.join(base_dir, 'data', 'backups')

    # Ensure directories exist
    try:
        os.makedirs(media_root, exist_ok=True)
        os.makedirs(photos_dir, exist_ok=True)
        os.makedirs(attachments_dir, exist_ok=True)
        os.makedirs(backups_dir, exist_ok=True)
    except Exception:
        pass

    return {
        'base_dir': base_dir,
        'database_path': db_path,
        'media_root': media_root,
        'photos_dir': photos_dir,
        'attachments_dir': attachments_dir,
        'backups_dir': backups_dir,
    }


def get_dir_stats(dir_path):
    """Safely calculates recursive total file count and byte size of a directory."""
    if not os.path.exists(dir_path):
        return {'count': 0, 'total_bytes': 0}
    count = 0
    total_bytes = 0
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                p = os.path.join(root, f)
                try:
                    total_bytes += os.path.getsize(p)
                    count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return {'count': count, 'total_bytes': total_bytes}


def format_bytes(bytes_num):
    """Converts raw byte count into human-readable string (e.g., 2.45 MB)."""
    try:
        bytes_num = float(bytes_num or 0)
        if bytes_num <= 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while bytes_num >= 1024 and i < len(units) - 1:
            bytes_num /= 1024.0
            i += 1
        return f"{bytes_num:.2f} {units[i]}"
    except Exception:
        return "0 B"


def create_full_backup_snapshot(label_prefix='sutawane-full-backup'):
    """
    Creates a complete portable system archive (.zip) containing:
    1. Online atomic SQLite database snapshot (with flushed WAL pages & zero corruption)
    2. Complete media directory tree (all student & institute photos, expense vouchers, bills, docs)
    3. Metadata manifest (backup-meta.json) with comprehensive audit statistics
    4. Plain human-readable system summary (system-summary.json) covering settings, branches & counts
    """
    paths = get_storage_paths()
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%dT%H-%M-%S')
    file_name = f"{label_prefix}-{timestamp}.zip"
    file_path = os.path.join(paths['backups_dir'], file_name)

    db_path = paths['database_path']
    media_root = paths['media_root']
    is_pg = _is_postgres()

    # 1. Take safe online point-in-time database snapshot to staging file
    staging_snapshot = file_path + ('.pgdump' if is_pg else '.dbsnapshot')
    try:
        if is_pg:
            pg_dump_bin = shutil.which('pg_dump')
            if not pg_dump_bin:
                raise RuntimeError("pg_dump binary not found on system PATH. Install postgresql-client on the server.")
            db_name, conn_args, pg_env = _get_pg_conn_details()
            proc = subprocess.run(
                [pg_dump_bin, *conn_args, '-F', 'c', '-f', staging_snapshot, db_name],
                env=pg_env,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"pg_dump failed: {proc.stderr.strip() or proc.stdout.strip()}")
            db_arcname = 'sutawane.dump'
        else:
            _create_online_db_snapshot(db_path, staging_snapshot)
            db_arcname = 'sutawane.db'

        db_size = os.path.getsize(staging_snapshot) if os.path.exists(staging_snapshot) else 0

        # 2. Gather human-readable system summary text and counts
        summary = _gather_system_summary(staging_snapshot if not is_pg else None)

        photos_count = 0
        attachments_count = 0
        other_media_count = 0
        total_media_count = 0
        total_media_bytes = 0

        with zipfile.ZipFile(file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Add Database dump/snapshot
            if os.path.exists(staging_snapshot):
                zf.write(staging_snapshot, arcname=db_arcname)

            # Add All Media Files recursively from media_root
            if os.path.exists(media_root):
                for root, _, files in os.walk(media_root):
                    for f in files:
                        full_p = os.path.join(root, f)
                        if not os.path.isfile(full_p):
                            continue
                        rel_p = os.path.relpath(full_p, media_root).replace('\\', '/')
                        zf.write(full_p, arcname=rel_p)

                        f_size = os.path.getsize(full_p)
                        total_media_bytes += f_size
                        total_media_count += 1

                        if rel_p.startswith('photos/'):
                            photos_count += 1
                        elif rel_p.startswith('attachments/'):
                            attachments_count += 1
                        else:
                            other_media_count += 1

            # Add Manifest Metadata
            manifest = {
                'version': '2.0',
                'appName': 'Sutawane Classes Management Software',
                'createdAt': now.isoformat(),
                'dbSize': db_size,
                'photosCount': photos_count,
                'attachmentsCount': attachments_count,
                'otherMediaCount': other_media_count,
                'totalMediaCount': total_media_count,
                'totalMediaBytes': total_media_bytes,
                'databaseEngine': 'PostgreSQL (Django ORM)' if is_pg else 'SQLite 3 Local Persistent (Django ORM)',
                'modelCounts': summary.get('modelCounts', {}),
            }
            zf.writestr('backup-meta.json', json.dumps(manifest, indent=2))

            # Add Plain-Text System Summary
            zf.writestr('system-summary.json', json.dumps(summary, indent=2))
    finally:
        # Clean up staging snapshot regardless of success or error
        if os.path.exists(staging_snapshot):
            try:
                os.remove(staging_snapshot)
            except Exception:
                pass

    size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    return {
        'fileName': file_name,
        'filePath': file_path,
        'sizeBytes': size_bytes,
        'photosCount': photos_count,
        'attachmentsCount': attachments_count,
        'otherMediaCount': other_media_count,
        'totalMediaCount': total_media_count,
        'totalMediaBytes': total_media_bytes,
        'createdAt': now.isoformat(),
    }



def _validate_pg_dump(dump_path):
    """Validate PostgreSQL custom archive TOC before touching the live database."""
    pg_restore_bin = shutil.which('pg_restore')
    if not pg_restore_bin:
        raise RuntimeError("pg_restore binary not found on system PATH. Install postgresql-client on the server.")
    proc = subprocess.run(
        [pg_restore_bin, '--list', dump_path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"Invalid or corrupted PostgreSQL dump archive: {proc.stderr.strip() or proc.stdout.strip()}")


def _restore_pg_dump(dump_path):
    """Validate and atomically restore a PostgreSQL custom-format dump file via pg_restore."""
    _validate_pg_dump(dump_path)
    pg_restore_bin = shutil.which('pg_restore')
    db_name, conn_args, pg_env = _get_pg_conn_details()
    connections.close_all()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid();"
            )
    except Exception:
        pass
    connections.close_all()
    proc = subprocess.run(
        [
            pg_restore_bin, *conn_args,
            '--clean', '--if-exists', '--no-owner', '--no-acl',
            '--single-transaction', '--exit-on-error',
            '-d', db_name, dump_path,
        ],
        env=pg_env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore failed: {proc.stderr.strip() or proc.stdout.strip()}")


def _validate_sqlite_staging_file(db_file_path):
    """Verify SQLite format header and integrity before replacing the active database."""
    with open(db_file_path, 'rb') as f:
        header = f.read(16)
    if not header.startswith(b'SQLite format 3'):
        raise ValueError("Invalid database file: header does not match SQLite format 3.")
    conn = sqlite3.connect(db_file_path)
    try:
        res = conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0] != 'ok':
            raise ValueError(f"Corrupted SQLite backup archive failed integrity_check: {res}")
    finally:
        conn.close()


def _extract_media_from_zip(zf, media_root):
    """Safely extract media entries from a backup zip archive using streaming + canonical path checks."""
    restored_photos = 0
    restored_attachments = 0
    restored_other = 0
    restored_total = 0
    special_entries = {'sutawane.db', 'db.sqlite3', 'sutawane.dump', 'backup-meta.json', 'system-summary.json'}
    os.makedirs(media_root, exist_ok=True)
    real_media_root = os.path.realpath(media_root)

    for info in zf.infolist():
        name = info.filename
        if info.is_dir() or name.endswith('/') or name.endswith('\\'):
            continue
        base_only = name.replace('\\', '/')
        if base_only in special_entries or base_only.endswith('.db') or base_only.endswith('.dump'):
            continue
        if info.file_size > MAX_ZIP_ENTRY_BYTES:
            raise ValueError(f"Media entry '{name}' exceeds safety size limit.")

        rel_norm = base_only
        if rel_norm.startswith('media/'):
            rel_norm = rel_norm[6:]
        parts = [p for p in rel_norm.split('/') if p and p != '.']
        if not parts or rel_norm.startswith('/') or '..' in parts:
            continue

        safe_rel = os.path.join(*parts)
        dest_file = os.path.realpath(os.path.join(real_media_root, safe_rel))
        try:
            if os.path.commonpath([dest_file, real_media_root]) != real_media_root or dest_file == real_media_root:
                continue
        except Exception:
            continue

        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        with zf.open(info, 'r') as src_f, open(dest_file, 'wb') as f_out:
            shutil.copyfileobj(src_f, f_out, length=65536)

        restored_total += 1
        if parts[0] == 'photos':
            restored_photos += 1
        elif parts[0] == 'attachments':
            restored_attachments += 1
        else:
            restored_other += 1

    return restored_photos, restored_attachments, restored_other, restored_total


def _finalize_restore():
    """Verify DB connectivity/integrity, sync pending migrations, ensure cache table, and clear all caches."""
    connections.close_all()
    connection.connect()
    with connection.cursor() as cursor:
        if _is_postgres():
            cursor.execute("SELECT 1;")
            res = cursor.fetchone()
            if not res or res[0] != 1:
                raise ValueError(f"Restored PostgreSQL database failed health check: {res}")
        else:
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != 'ok':
                raise ValueError(f"Restored database failed integrity check: {res}")

    from django.core.management import call_command
    call_command('migrate', interactive=False)
    try:
        call_command('createcachetable', verbosity=0)
    except Exception:
        pass

    try:
        from .cache_utils import invalidate_all_app_cache
        from .auth_utils import invalidate_license_cache, invalidate_permissions_cache
        invalidate_all_app_cache()
        invalidate_license_cache()
        invalidate_permissions_cache()
    except Exception:
        pass
    try:
        from .context_processors import invalidate_global_context_cache
        invalidate_global_context_cache()
    except Exception:
        pass


def execute_restore_from_file(target_file_path, original_filename):
    """
    Core Restore Engine with archive pre-validation, cross-process restore lock,
    automatic pre-restore safety snapshot, atomic DB replacement, and cache flush.
    """
    if not os.path.exists(target_file_path):
        raise FileNotFoundError(f"Target backup file '{target_file_path}' does not exist on disk.")

    paths = get_storage_paths()
    media_root = paths['media_root']
    ext = os.path.splitext(target_file_path)[1].lower() or os.path.splitext(original_filename)[1].lower()
    is_pg = _is_postgres()

    with _exclusive_backup_lock(paths['backups_dir']):
        restored_photos = 0
        restored_attachments = 0
        restored_other = 0
        restored_total = 0

        if ext == '.zip':
            if not zipfile.is_zipfile(target_file_path):
                raise ValueError("Corrupted or invalid zip backup archive.")

            with zipfile.ZipFile(target_file_path, 'r') as zf:
                name_list = zf.namelist()
                if is_pg:
                    dump_entry = next(
                        (name for name in name_list if name == 'sutawane.dump' or (name.endswith('.dump') and '/' not in name and '\\' not in name)),
                        None
                    )
                    if not dump_entry:
                        raise ValueError("Corrupted or invalid backup archive: No PostgreSQL dump (.dump) file found inside the zip.")
                    dump_info = zf.getinfo(dump_entry)
                    if dump_info.file_size > 2 * 1024 * 1024 * 1024:
                        raise ValueError("Backup dump inside archive exceeds size safety limit.")
                    staging_dump = os.path.join(paths['backups_dir'], f".restore_staging_{int(time.time())}.dump")
                    try:
                        with zf.open(dump_info, 'r') as src_d, open(staging_dump, 'wb') as dump_out:
                            shutil.copyfileobj(src_d, dump_out, length=65536)
                        _validate_pg_dump(staging_dump)
                        safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')
                        _restore_pg_dump(staging_dump)
                    finally:
                        if os.path.exists(staging_dump):
                            try:
                                os.remove(staging_dump)
                            except Exception:
                                pass
                else:
                    db_entry = next(
                        (name for name in name_list if name in ('sutawane.db', 'db.sqlite3') or (name.endswith('.db') and '/' not in name and '\\' not in name)),
                        None
                    )
                    if not db_entry:
                        raise ValueError("Corrupted or invalid backup archive: No SQLite database file found inside the zip.")
                    db_info = zf.getinfo(db_entry)
                    staging_db = paths['database_path'] + f'.staging.{int(time.time())}'
                    try:
                        with zf.open(db_info, 'r') as src_db, open(staging_db, 'wb') as db_out:
                            shutil.copyfileobj(src_db, db_out, length=65536)
                        _validate_sqlite_staging_file(staging_db)
                        safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')
                        _atomic_replace_sqlite(staging_db, paths['database_path'])
                    finally:
                        if os.path.exists(staging_db):
                            try:
                                os.remove(staging_db)
                            except Exception:
                                pass

                restored_photos, restored_attachments, restored_other, restored_total = _extract_media_from_zip(zf, media_root)

            _finalize_restore()
            new_db_size = _get_db_size_bytes(paths['database_path'])

            breakdown_msg = f"{restored_photos} photos & {restored_attachments} vouchers"
            if restored_other > 0:
                breakdown_msg += f" & {restored_other} other media"

            return {
                'safetySnapshot': safety['fileName'],
                'restoredPhotos': restored_photos,
                'restoredAttachments': restored_attachments,
                'restoredOther': restored_other,
                'restoredTotalMedia': restored_total,
                'dbSizeBytes': new_db_size,
                'message': f"Full system restore complete: Database restored ({format_bytes(new_db_size)}), {restored_total} total media files ({breakdown_msg}) recovered successfully.",
            }

        elif ext == '.dump' and is_pg:
            _validate_pg_dump(target_file_path)
            safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')
            _restore_pg_dump(target_file_path)
            _finalize_restore()
            new_db_size = _get_db_size_bytes(paths['database_path'])
            return {
                'safetySnapshot': safety['fileName'],
                'restoredPhotos': 0,
                'restoredAttachments': 0,
                'restoredOther': 0,
                'restoredTotalMedia': 0,
                'dbSizeBytes': new_db_size,
                'message': f"PostgreSQL database snapshot restore complete ({format_bytes(new_db_size)}). All records, tables, and settings restored.",
            }

        elif ext == '.db' and not is_pg:
            _validate_sqlite_staging_file(target_file_path)
            safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')
            staging_db = paths['database_path'] + f'.staging.{int(time.time())}'
            try:
                shutil.copyfile(target_file_path, staging_db)
                _atomic_replace_sqlite(staging_db, paths['database_path'])
            finally:
                if os.path.exists(staging_db):
                    try:
                        os.remove(staging_db)
                    except Exception:
                        pass

            _finalize_restore()
            new_db_size = _get_db_size_bytes(paths['database_path'])

            return {
                'safetySnapshot': safety['fileName'],
                'restoredPhotos': 0,
                'restoredAttachments': 0,
                'restoredOther': 0,
                'restoredTotalMedia': 0,
                'dbSizeBytes': new_db_size,
                'message': f"Database snapshot restore complete ({format_bytes(new_db_size)}). All records, tables, and settings restored.",
            }

        else:
            supported = ".zip and .dump" if is_pg else ".zip and .db"
            raise ValueError(f"Unsupported backup file format for the active database engine. Only {supported} files are supported.")


def list_backups():
    """
    Scans the backups directory and returns sorted list of snapshot metadata
    together with comprehensive system storage telemetry.
    """
    paths = get_storage_paths()
    backups_dir = paths['backups_dir']

    files = []
    if os.path.exists(backups_dir):
        try:
            files = os.listdir(backups_dir)
        except Exception:
            files = []

    backups_list = []
    for f in files:
        full_p = os.path.join(backups_dir, f)
        if not os.path.isfile(full_p):
            continue

        ext = os.path.splitext(f)[1].lower()
        if ext not in ('.zip', '.db', '.dump'):
            continue

        st = os.stat(full_p)
        b_type = 'FULL_ZIP' if ext == '.zip' else 'DB_ONLY'
        is_safety = 'pre-restore-safety' in f
        photos_count = None
        attachments_count = None
        other_media_count = None
        total_media_count = None

        if ext == '.zip':
            try:
                with zipfile.ZipFile(full_p, 'r') as zf:
                    if 'backup-meta.json' in zf.namelist():
                        meta = json.loads(zf.read('backup-meta.json').decode('utf-8')) or {}
                        if not isinstance(meta, dict):
                            meta = {}
                        photos_count = int(meta.get('photosCount') or 0)
                        attachments_count = int(meta.get('attachmentsCount') or 0)
                        other_media_count = int(meta.get('otherMediaCount') or 0)
                        total_media_count = int(meta.get('totalMediaCount') or (photos_count + attachments_count))
                    else:
                        names = [n for n in zf.namelist() if not n.endswith('/') and not n.endswith('\\')]
                        photos_count = len([n for n in names if 'photos/' in n])
                        attachments_count = len([n for n in names if 'attachments/' in n])
                        media_files = [n for n in names if n not in ('sutawane.db', 'db.sqlite3', 'sutawane.dump', 'backup-meta.json', 'system-summary.json') and not n.endswith('.db') and not n.endswith('.dump')]
                        total_media_count = len(media_files)
                        other_media_count = max(0, total_media_count - photos_count - attachments_count)
            except Exception:
                pass

        backups_list.append({
            'fileName': f,
            'sizeBytes': st.st_size,
            'sizeFormatted': format_bytes(st.st_size),
            'createdAt': datetime.fromtimestamp(st.st_mtime).isoformat(),
            'createdFormatted': datetime.fromtimestamp(st.st_mtime).strftime('%d %b %Y, %I:%M %p'),
            'type': b_type,
            'photosCount': photos_count,
            'attachmentsCount': attachments_count,
            'otherMediaCount': other_media_count,
            'totalMediaCount': total_media_count,
            'isSafetySnapshot': is_safety,
        })

    # Sort newest first
    backups_list.sort(key=lambda b: b['createdAt'], reverse=True)

    db_path = paths['database_path']
    db_size = _get_db_size_bytes(db_path)
    photos_stats = get_dir_stats(paths['photos_dir'])
    attachments_stats = get_dir_stats(paths['attachments_dir'])
    total_media_stats = get_dir_stats(paths['media_root'])

    stats = {
        'dbSize': db_size,
        'dbSizeFormatted': format_bytes(db_size),
        'databaseEngineLabel': 'PostgreSQL' if _is_postgres() else 'SQLite 3',
        'photosCount': photos_stats['count'],
        'photosSizeBytes': photos_stats['total_bytes'],
        'photosSizeFormatted': format_bytes(photos_stats['total_bytes']),
        'attachmentsCount': attachments_stats['count'],
        'attachmentsSizeBytes': attachments_stats['total_bytes'],
        'attachmentsSizeFormatted': format_bytes(attachments_stats['total_bytes']),
        'totalMediaCount': total_media_stats['count'],
        'totalMediaSizeBytes': total_media_stats['total_bytes'],
        'totalMediaSizeFormatted': format_bytes(total_media_stats['total_bytes']),
        'backupsCount': len(backups_list),
        'storageLocation': {
            'baseDir': paths['base_dir'],
            'databasePath': paths['database_path'],
            'mediaRoot': paths['media_root'],
            'photosDir': paths['photos_dir'],
            'attachmentsDir': paths['attachments_dir'],
            'backupsDir': paths['backups_dir'],
        },
    }

    return {
        'stats': stats,
        'backups': backups_list,
    }


def delete_backup(file_name):
    """Safely deletes a backup file from backups directory preventing path traversal."""
    safe_name = os.path.basename(file_name)
    paths = get_storage_paths()
    target_path = os.path.join(paths['backups_dir'], safe_name)
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Backup file '{safe_name}' not found.")
    os.remove(target_path)
    return safe_name


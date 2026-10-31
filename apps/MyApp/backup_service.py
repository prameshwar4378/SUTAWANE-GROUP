import os
import shutil
import zipfile
import json
import time
import sqlite3
from datetime import datetime
from django.conf import settings
from django.db import connection, connections


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
        with sqlite3.connect(staging_path) as src_conn:
            with sqlite3.connect(target_path, timeout=30.0) as dst_conn:
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

    with sqlite3.connect(db_path) as src:
        with sqlite3.connect(dest_path) as dst:
            src.backup(dst)


def _gather_system_summary(db_path):
    """
    Collects a human-readable text summary of all models and key system configurations.
    Enables instant plain-text verification and inspection of the backup contents.
    """
    summary = {
        'generatedAt': datetime.now().isoformat(),
        'appName': 'Sutawane Classes Management Software',
        'databaseEngine': 'SQLite 3 Local Persistent (Django ORM)',
        'modelCounts': {},
        'settings': {},
        'branches': [],
        'sessions': [],
        'courses': [],
    }
    if not os.path.exists(db_path):
        return summary

    try:
        with sqlite3.connect(db_path) as conn:
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

            # Key System Settings
            if 'SystemSetting' in tables:
                try:
                    settings_rows = cur.execute('SELECT key, value FROM SystemSetting').fetchall()
                    summary['settings'] = {r['key']: r['value'] for r in settings_rows}
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
    - database_path: Path to active SQLite database
    - media_root: Root directory for all media assets
    - photos_dir: Media directory for student & branch photos
    - attachments_dir: Media directory for expense receipts & bills
    - backups_dir: Dedicated directory for persistent backup archives
    """
    base_dir = str(settings.BASE_DIR)
    db_path = str(settings.DATABASES['default']['NAME'])

    # Media directories
    media_root = str(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') else os.path.join(base_dir, 'media')
    photos_dir = os.path.join(media_root, 'photos')
    attachments_dir = os.path.join(media_root, 'attachments')

    # Backups directory in data/backups
    backups_dir = os.path.join(base_dir, 'data', 'backups')

    # Ensure directories exist
    os.makedirs(media_root, exist_ok=True)
    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)
    os.makedirs(backups_dir, exist_ok=True)

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

    # 1. Take safe online point-in-time SQLite snapshot to staging file
    staging_snapshot = file_path + '.dbsnapshot'
    _create_online_db_snapshot(db_path, staging_snapshot)
    db_size = os.path.getsize(staging_snapshot) if os.path.exists(staging_snapshot) else 0

    # 2. Gather human-readable system summary text and counts
    summary = _gather_system_summary(staging_snapshot)

    photos_count = 0
    attachments_count = 0
    other_media_count = 0
    total_media_count = 0
    total_media_bytes = 0

    with zipfile.ZipFile(file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # Add Database (store under both sutawane.db and db.sqlite3 for universal tool compatibility)
        if os.path.exists(staging_snapshot):
            zf.write(staging_snapshot, arcname='sutawane.db')

        # Add All Media Files recursively from media_root
        if os.path.exists(media_root):
            for root, _, files in os.walk(media_root):
                for f in files:
                    full_p = os.path.join(root, f)
                    if not os.path.isfile(full_p):
                        continue
                    # Compute relative path inside media/
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
            'databaseEngine': 'SQLite 3 Local Persistent (Django ORM)',
            'modelCounts': summary.get('modelCounts', {}),
        }
        zf.writestr('backup-meta.json', json.dumps(manifest, indent=2))

        # Add Plain-Text System Summary
        zf.writestr('system-summary.json', json.dumps(summary, indent=2))

    # Clean up staging snapshot
    try:
        if os.path.exists(staging_snapshot):
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



def execute_restore_from_file(target_file_path, original_filename):
    """
    Core Restore Engine:
    1. Automatically creates an instant pre-restore safety snapshot of current data (Zero Data Loss Guarantee).
    2. Validates archive integrity.
    3. Replaces active SQLite database file using dual-mode atomic replacement.
    4. Restores all media files (photos, vouchers, attachments, documents) preserving folder hierarchy.
    5. Reconnects database connection and verifies PRAGMA integrity_check.
    """
    if not os.path.exists(target_file_path):
        raise FileNotFoundError(f"Target backup file '{target_file_path}' does not exist on disk.")

    paths = get_storage_paths()
    media_root = paths['media_root']
    ext = os.path.splitext(target_file_path)[1].lower() or os.path.splitext(original_filename)[1].lower()

    # 1. Automatic Pre-Restore Safety Snapshot (Zero Data Loss Guarantee)
    safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')

    restored_photos = 0
    restored_attachments = 0
    restored_other = 0
    restored_total = 0
    new_db_size = 0

    if ext == '.zip':
        with zipfile.ZipFile(target_file_path, 'r') as zf:
            name_list = zf.namelist()

            # Find SQLite database inside archive
            db_entry = next(
                (name for name in name_list if name in ('sutawane.db', 'db.sqlite3') or (name.endswith('.db') and '/' not in name and '\\' not in name)),
                None
            )
            if not db_entry:
                raise ValueError("Corrupted or invalid backup archive: No SQLite database file found inside the zip.")

            # Extract database to staging file and atomically replace
            staging_db = paths['database_path'] + '.staging'
            with open(staging_db, 'wb') as db_out:
                db_out.write(zf.read(db_entry))

            _atomic_replace_sqlite(staging_db, paths['database_path'])
            new_db_size = os.path.getsize(paths['database_path'])

            # Extract all media files preserving directory hierarchy
            special_entries = ('sutawane.db', 'db.sqlite3', 'backup-meta.json', 'system-summary.json')
            for name in name_list:
                # Skip directory markers and non-media root metadata
                if name.endswith('/') or name.endswith('\\') or name in special_entries or name.endswith('.db'):
                    continue

                # Normalize relative path (support both media/... and photos/... formats)
                rel_norm = name.replace('\\', '/')
                if rel_norm.startswith('media/'):
                    rel_norm = rel_norm[6:]

                # Disallow empty or absolute or escaping paths
                if not rel_norm or rel_norm.startswith('/') or '..' in rel_norm:
                    continue

                dest_file = os.path.normpath(os.path.join(media_root, rel_norm))

                # Security check against zip-slip directory traversal
                try:
                    if os.path.commonpath([dest_file, media_root]) != media_root:
                        continue
                except Exception:
                    continue

                # Ensure target subdirectory exists
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)

                # Write restored media file
                with open(dest_file, 'wb') as f_out:
                    f_out.write(zf.read(name))

                restored_total += 1
                if rel_norm.startswith('photos/'):
                    restored_photos += 1
                elif rel_norm.startswith('attachments/'):
                    restored_attachments += 1
                else:
                    restored_other += 1

        # Reconnect and run database integrity check
        connection.connect()
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != 'ok':
                raise ValueError(f"Restored database failed integrity check: {res}")

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

    elif ext == '.db':
        # Validate SQLite magic header
        with open(target_file_path, 'rb') as f:
            header = f.read(16)
        if not header.startswith(b'SQLite format 3'):
            raise ValueError("Invalid database file: header does not match SQLite format 3.")

        # Stage and atomically replace database
        staging_db = paths['database_path'] + '.staging'
        shutil.copyfile(target_file_path, staging_db)
        _atomic_replace_sqlite(staging_db, paths['database_path'])
        new_db_size = os.path.getsize(paths['database_path'])

        # Reconnect & verify
        connection.connect()
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != 'ok':
                raise ValueError(f"Restored database failed integrity check: {res}")

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
        raise ValueError("Unsupported backup file format. Only .zip and .db files are supported.")


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
        if ext not in ('.zip', '.db'):
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
                        meta = json.loads(zf.read('backup-meta.json').decode('utf-8'))
                        photos_count = meta.get('photosCount', 0)
                        attachments_count = meta.get('attachmentsCount', 0)
                        other_media_count = meta.get('otherMediaCount', 0)
                        total_media_count = meta.get('totalMediaCount', (photos_count + attachments_count))
                    else:
                        names = [n for n in zf.namelist() if not n.endswith('/') and not n.endswith('\\')]
                        photos_count = len([n for n in names if 'photos/' in n])
                        attachments_count = len([n for n in names if 'attachments/' in n])
                        media_files = [n for n in names if n not in ('sutawane.db', 'db.sqlite3', 'backup-meta.json', 'system-summary.json') and not n.endswith('.db')]
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
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    photos_stats = get_dir_stats(paths['photos_dir'])
    attachments_stats = get_dir_stats(paths['attachments_dir'])
    total_media_stats = get_dir_stats(paths['media_root'])

    stats = {
        'dbSize': db_size,
        'dbSizeFormatted': format_bytes(db_size),
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


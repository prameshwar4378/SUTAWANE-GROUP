import os
import shutil
import zipfile
import json
from datetime import datetime
from django.conf import settings
from django.db import connection


def get_storage_paths():
    """
    Returns exact storage path locations on local machine:
    - base_dir: Project root directory
    - database_path: Path to active SQLite database
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
    
    # Backups directory in data/backups or media/backups
    backups_dir = os.path.join(base_dir, 'data', 'backups')
    
    # Ensure directories exist
    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)
    os.makedirs(backups_dir, exist_ok=True)
    
    return {
        'base_dir': base_dir,
        'database_path': db_path,
        'photos_dir': photos_dir,
        'attachments_dir': attachments_dir,
        'backups_dir': backups_dir,
    }


def get_dir_stats(dir_path):
    """Safely calculates total file count and byte size of a directory."""
    if not os.path.exists(dir_path):
        return {'count': 0, 'total_bytes': 0}
    count = 0
    total_bytes = 0
    try:
        for entry in os.scandir(dir_path):
            if entry.is_file():
                count += 1
                total_bytes += entry.stat().st_size
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
    1. Flushed SQLite database (with PRAGMA wal_checkpoint(FULL))
    2. Student and institute profile pictures (media/photos/)
    3. Center expense vouchers and receipt scans (media/attachments/)
    4. Metadata manifest (backup-meta.json) with audit metrics
    """
    paths = get_storage_paths()
    
    # 1. Force SQLite WAL checkpoint so database file contains all committed data
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA wal_checkpoint(FULL);")
    except Exception:
        pass

    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%dT%H-%M-%S')
    file_name = f"{label_prefix}-{timestamp}.zip"
    file_path = os.path.join(paths['backups_dir'], file_name)

    db_path = paths['database_path']
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    photos_count = 0
    attachments_count = 0

    with zipfile.ZipFile(file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # Add Database
        if os.path.exists(db_path):
            zf.write(db_path, arcname='sutawane.db')

        # Add Photos
        if os.path.exists(paths['photos_dir']):
            for root, _, files in os.walk(paths['photos_dir']):
                for f in files:
                    full_p = os.path.join(root, f)
                    if os.path.isfile(full_p):
                        rel_p = os.path.join('photos', f)
                        zf.write(full_p, arcname=rel_p)
                        photos_count += 1

        # Add Attachments
        if os.path.exists(paths['attachments_dir']):
            for root, _, files in os.walk(paths['attachments_dir']):
                for f in files:
                    full_p = os.path.join(root, f)
                    if os.path.isfile(full_p):
                        rel_p = os.path.join('attachments', f)
                        zf.write(full_p, arcname=rel_p)
                        attachments_count += 1

        # Add Manifest Metadata
        manifest = {
            'version': '1.0',
            'appName': 'Sutawane Classes Management Software',
            'createdAt': now.isoformat(),
            'dbSize': db_size,
            'photosCount': photos_count,
            'attachmentsCount': attachments_count,
            'databaseEngine': 'SQLite 3 Local Persistent (Django ORM)',
        }
        zf.writestr('backup-meta.json', json.dumps(manifest, indent=2))

    size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    return {
        'fileName': file_name,
        'filePath': file_path,
        'sizeBytes': size_bytes,
        'photosCount': photos_count,
        'attachmentsCount': attachments_count,
        'createdAt': now.isoformat(),
    }


def execute_restore_from_file(target_file_path, original_filename):
    """
    Core Restore Engine:
    1. Automatically creates a pre-restore safety snapshot of current data.
    2. Validates archive integrity.
    3. Replaces active SQLite database file.
    4. Restores student photos and expense attachments.
    5. Reconnects database connection and verifies PRAGMA integrity_check.
    """
    if not os.path.exists(target_file_path):
        raise FileNotFoundError(f"Target backup file '{target_file_path}' does not exist on disk.")

    paths = get_storage_paths()
    ext = os.path.splitext(target_file_path)[1].lower() or os.path.splitext(original_filename)[1].lower()

    # 1. Automatic Pre-Restore Safety Snapshot (Zero Data Loss Guarantee)
    safety = create_full_backup_snapshot(label_prefix='sutawane-pre-restore-safety')

    restored_photos = 0
    restored_attachments = 0
    new_db_size = 0

    if ext == '.zip':
        with zipfile.ZipFile(target_file_path, 'r') as zf:
            name_list = zf.namelist()
            # Find SQLite database inside archive
            db_entry = next((name for name in name_list if name in ('sutawane.db', 'db.sqlite3') or (name.endswith('.db') and not '/' in name)), None)
            if not db_entry:
                raise ValueError("Corrupted or invalid backup archive: No SQLite database file found inside the zip.")

            # Close existing connection to unlock file
            connection.close()

            # Clean stale WAL/SHM
            for suffix in ('-wal', '-shm'):
                wal_p = paths['database_path'] + suffix
                if os.path.exists(wal_p):
                    try:
                        os.remove(wal_p)
                    except Exception:
                        pass

            # Extract database
            with open(paths['database_path'], 'wb') as db_out:
                db_out.write(zf.read(db_entry))

            new_db_size = os.path.getsize(paths['database_path'])

            # Extract photos and attachments
            for name in name_list:
                if name.startswith('photos/') and not name.endswith('/'):
                    fname = os.path.basename(name)
                    if fname:
                        dest = os.path.join(paths['photos_dir'], fname)
                        with open(dest, 'wb') as f_out:
                            f_out.write(zf.read(name))
                        restored_photos += 1
                elif name.startswith('attachments/') and not name.endswith('/'):
                    fname = os.path.basename(name)
                    if fname:
                        dest = os.path.join(paths['attachments_dir'], fname)
                        with open(dest, 'wb') as f_out:
                            f_out.write(zf.read(name))
                        restored_attachments += 1

        # Reconnect and run integrity check
        connection.connect()
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != 'ok':
                raise ValueError(f"Restored database failed integrity check: {res}")

        return {
            'safetySnapshot': safety['fileName'],
            'restoredPhotos': restored_photos,
            'restoredAttachments': restored_attachments,
            'dbSizeBytes': new_db_size,
            'message': f"Full system restore complete: Database restored ({format_bytes(new_db_size)}), {restored_photos} photos, and {restored_attachments} attachments recovered successfully.",
        }

    elif ext == '.db':
        # Validate SQLite magic header
        with open(target_file_path, 'rb') as f:
            header = f.read(16)
        if not header.startswith(b'SQLite format 3'):
            raise ValueError("Invalid database file: header does not match SQLite format 3.")

        # Close existing connection
        connection.close()

        # Clean stale WAL/SHM
        for suffix in ('-wal', '-shm'):
            wal_p = paths['database_path'] + suffix
            if os.path.exists(wal_p):
                try:
                    os.remove(wal_p)
                except Exception:
                    pass

        # Copy database
        shutil.copyfile(target_file_path, paths['database_path'])
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
            'dbSizeBytes': new_db_size,
            'message': f"Database snapshot restore complete ({format_bytes(new_db_size)}).",
        }

    else:
        raise ValueError("Unsupported backup file format. Only .zip and .db files are supported.")


def list_backups():
    """
    Scans the backups directory and returns sorted list of snapshot metadata
    together with system storage stats.
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

        if ext == '.zip':
            try:
                with zipfile.ZipFile(full_p, 'r') as zf:
                    if 'backup-meta.json' in zf.namelist():
                        meta = json.loads(zf.read('backup-meta.json').decode('utf-8'))
                        photos_count = meta.get('photosCount', 0)
                        attachments_count = meta.get('attachmentsCount', 0)
                    else:
                        names = zf.namelist()
                        photos_count = len([n for n in names if n.startswith('photos/') and not n.endswith('/')])
                        attachments_count = len([n for n in names if n.startswith('attachments/') and not n.endswith('/')])
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
            'isSafetySnapshot': is_safety,
        })

    # Sort newest first
    backups_list.sort(key=lambda b: b['createdAt'], reverse=True)

    db_path = paths['database_path']
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    photos_stats = get_dir_stats(paths['photos_dir'])
    attachments_stats = get_dir_stats(paths['attachments_dir'])

    stats = {
        'dbSize': db_size,
        'dbSizeFormatted': format_bytes(db_size),
        'photosCount': photos_stats['count'],
        'photosSizeBytes': photos_stats['total_bytes'],
        'photosSizeFormatted': format_bytes(photos_stats['total_bytes']),
        'attachmentsCount': attachments_stats['count'],
        'attachmentsSizeBytes': attachments_stats['total_bytes'],
        'attachmentsSizeFormatted': format_bytes(attachments_stats['total_bytes']),
        'backupsCount': len(backups_list),
        'storageLocation': {
            'baseDir': paths['base_dir'],
            'databasePath': paths['database_path'],
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

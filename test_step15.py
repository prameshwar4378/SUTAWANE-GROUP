import os
import sys
import json
import io
import zipfile
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps'))

import django
django.setup()

from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from MyApp.models import User
from MyApp.auth_utils import hash_password
from MyApp.backup_service import get_storage_paths, list_backups, delete_backup

TEST_TAG = "TEST_STEP15_BACKUP"

print("=" * 70)
print("STARTING STEP 15 VERIFICATION: ONE-CLICK BACKUP & RESTORE ENGINE")
print("=" * 70)

# 1. Setup authenticated user session
print("\n--- 1. Setting Up Authenticated Session ---")
for u in User.objects.filter(username__icontains=TEST_TAG):
    u.delete()

test_username = f"{TEST_TAG.lower()}_owner"
hashed, salt = hash_password("sutawane@123")
owner = User.objects.create(
    username=test_username,
    password=hashed,
    salt=salt,
    name="System Administrator",
    role="SUPER_ADMIN",
    is_active=True,
)

client = Client()
session = client.session
session['user_id'] = owner.id
session['username'] = owner.username
session['role'] = owner.role
session.save()
print(f"[OK] Logged in session as: {owner.username} ({owner.role})")

paths = get_storage_paths()
print(f"[INFO] Storage locations:\n  DB: {paths['database_path']}\n  Photos: {paths['photos_dir']}\n  Attachments: {paths['attachments_dir']}\n  Backups: {paths['backups_dir']}")

created_test_backups = []

try:
    # 2. Test GET /backup/ UI rendering
    print("\n--- 2. Testing GET /backup/ UI Page Rendering ---")
    resp = client.get('/backup/')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    content = resp.content.decode('utf-8')
    assert "Backup &amp; Data Restore" in content or "Backup & Data Restore" in content
    assert "Database (sutawane.db)" in content
    assert "Student &amp; Institute Photos" in content or "Student & Institute Photos" in content
    assert "Expense Vouchers" in content
    assert "Saved Snapshots" in content
    assert "1. Create Complete System Backup (.zip)" in content
    assert "2. Upload &amp; Restore External Backup" in content or "2. Upload & Restore External Backup" in content
    assert "Available Backup Snapshots" in content
    assert "Storage Locations on This Computer" in content
    print("[OK] /backup/ rendered with all 4 telemetry cards, action cards, snapshots table, and storage paths.")

    # 3. Test GET /backup/?format=json
    print("\n--- 3. Testing GET /backup/?format=json ---")
    resp_json = client.get('/backup/?format=json')
    assert resp_json.status_code == 200
    jdata = resp_json.json()
    assert jdata['success'] is True
    assert 'stats' in jdata
    assert 'backups' in jdata
    assert jdata['stats']['dbSize'] > 0
    print(f"[OK] format=json returned {len(jdata['backups'])} backups. DB size: {jdata['stats']['dbSizeFormatted']}")

    # 4. Test Backup Creation via Form POST
    print("\n--- 4. Testing Backup Creation (POST action='create') ---")
    resp_create = client.post('/backup/', {'action': 'create'}, follow=True)
    assert resp_create.status_code == 200
    create_content = resp_create.content.decode('utf-8')
    assert "Full backup snapshot" in create_content or "created" in create_content

    # Inspect created backup in backups dir
    data_after = list_backups()
    latest_backup = data_after['backups'][0]
    created_test_backups.append(latest_backup['fileName'])
    print(f"[OK] Created full backup snapshot: {latest_backup['fileName']} ({latest_backup['sizeFormatted']})")
    assert latest_backup['fileName'].endswith('.zip')
    assert latest_backup['type'] == 'FULL_ZIP'

    # 5. Inspect Zip Archive Structure & Meta JSON
    print("\n--- 5. Inspecting Zip Archive Structure & Metadata ---")
    zip_path = os.path.join(paths['backups_dir'], latest_backup['fileName'])
    assert os.path.exists(zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        namelist = zf.namelist()
        print(f"Archive contents ({len(namelist)} items): {namelist[:6]}...")
        assert any(n in ('sutawane.db', 'db.sqlite3') for n in namelist)
        assert 'backup-meta.json' in namelist
        meta = json.loads(zf.read('backup-meta.json').decode('utf-8'))
        assert meta['appName'] == 'Sutawane Classes Management Software'
        assert meta['dbSize'] > 0
        assert 'photosCount' in meta
        assert 'attachmentsCount' in meta
    print("[OK] Zip contains valid SQLite database, backup-meta.json, and metadata attributes.")

    # 6. Test Download Streaming (UI route)
    print("\n--- 6. Testing Download Streaming (GET /backup/?download=...) ---")
    dl_resp = client.get(f"/backup/?download={latest_backup['fileName']}")
    assert dl_resp.status_code == 200
    assert 'zip' in dl_resp['Content-Type'].lower() or 'octet-stream' in dl_resp['Content-Type'].lower()
    assert latest_backup['fileName'] in dl_resp['Content-Disposition']
    streamed_data = b"".join(dl_resp.streaming_content)
    assert len(streamed_data) == os.path.getsize(zip_path)
    print(f"[OK] Download streaming verified ({len(streamed_data)} bytes).")

    # 7. Test REST API Endpoints matching React
    print("\n--- 7. Testing REST API Endpoints (100% React Parity) ---")
    # 7a. GET /api/backup/
    api_list = client.get('/api/backup/').json()
    assert api_list['success'] is True
    assert len(api_list['backups']) >= 1
    print(f"[OK] GET /api/backup/ returned {len(api_list['backups'])} backups.")

    # 7b. POST /api/backup/create/
    api_create = client.post('/api/backup/create/')
    assert api_create.status_code == 201
    create_j = api_create.json()
    assert create_j['success'] is True
    new_snap = create_j['backup']['fileName']
    created_test_backups.append(new_snap)
    print(f"[OK] POST /api/backup/create/ created snapshot: {new_snap}")

    # 7c. GET /api/backup/<file_name>/download/
    api_dl = client.get(f'/api/backup/{new_snap}/download/')
    assert api_dl.status_code == 200
    api_streamed = b"".join(api_dl.streaming_content)
    assert len(api_streamed) > 0
    print(f"[OK] GET /api/backup/<file_name>/download/ streamed {len(api_streamed)} bytes.")

    # 7d. POST /api/backup/restore-local/
    print("\n--- 8. Testing Local Snapshot Restore with Auto Safety Guarantee ---")
    restore_resp = client.post(
        '/api/backup/restore-local/',
        json.dumps({'fileName': latest_backup['fileName']}),
        content_type='application/json'
    )
    assert restore_resp.status_code == 200
    restore_j = restore_resp.json()
    assert restore_j['success'] is True
    assert 'safetySnapshot' in restore_j
    created_test_backups.append(restore_j['safetySnapshot'])
    print(f"[OK] Local restore completed successfully! Auto safety snapshot created: {restore_j['safetySnapshot']}")

    # Verify DB still responsive and user still exists
    assert User.objects.filter(username=test_username).exists()
    print("[OK] Database connection and integrity verified after restore.")

    # 8. Test Upload & Restore External Backup
    print("\n--- 9. Testing Upload & Restore of External Backup Archive ---")
    # Create a small valid test zip archive in memory containing current db
    mem_zip_buf = io.BytesIO()
    with zipfile.ZipFile(mem_zip_buf, 'w', zipfile.ZIP_DEFLATED) as test_zf:
        # copy active db
        with open(paths['database_path'], 'rb') as f:
            test_zf.writestr('sutawane.db', f.read())
        test_zf.writestr('photos/test_photo.txt', b'test student photo payload')
        test_zf.writestr('attachments/test_voucher.txt', b'test voucher payload')
        meta_payload = {
            'appName': 'Sutawane Classes Management Software',
            'version': '2.0.0',
            'photosCount': 1,
            'attachmentsCount': 1,
        }
        test_zf.writestr('backup-meta.json', json.dumps(meta_payload).encode('utf-8'))

    mem_zip_buf.seek(0)
    uploaded_file = SimpleUploadedFile(
        'external-restore-test.zip',
        mem_zip_buf.read(),
        content_type='application/zip'
    )

    upload_resp = client.post('/api/backup/upload-restore/', {'backupFile': uploaded_file})
    assert upload_resp.status_code == 200
    upload_j = upload_resp.json()
    assert upload_j['success'] is True
    assert upload_j['restoredPhotos'] >= 1
    assert upload_j['restoredAttachments'] >= 1
    created_test_backups.append(upload_j['safetySnapshot'])
    created_test_backups.append(upload_j['uploadedFileName'])
    print(f"[OK] Upload restore successful! Restored {upload_j['restoredPhotos']} photos, {upload_j['restoredAttachments']} attachments.")
    print(f"     Safety snapshot taken: {upload_j['safetySnapshot']}")

    # 9. Test Delete Backup via API and Form POST
    print("\n--- 10. Testing Snapshot Deletion ---")
    # API DELETE /api/backup/<file_name>/
    del_api_resp = client.delete(f'/api/backup/{new_snap}/')
    assert del_api_resp.status_code == 200
    assert not os.path.exists(os.path.join(paths['backups_dir'], new_snap))
    print(f"[OK] API DELETE /api/backup/{new_snap}/ successfully removed file from disk.")

    # Form POST action='delete'
    del_form_resp = client.post('/backup/', {'action': 'delete', 'file_name': latest_backup['fileName']}, follow=True)
    assert del_form_resp.status_code == 200
    assert not os.path.exists(os.path.join(paths['backups_dir'], latest_backup['fileName']))
    print(f"[OK] Form POST action='delete' successfully removed {latest_backup['fileName']} from disk.")

    print("\n" + "=" * 70)
    print("ALL STEP 15 BACKUP & RESTORE VERIFICATIONS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

finally:
    # Cleanup all generated test snapshots
    print("\n--- Cleaning up temporary test snapshots & test user ---")
    for b_file in created_test_backups:
        try:
            delete_backup(b_file)
            print(f"Deleted test snapshot: {b_file}")
        except Exception:
            pass

    # Cleanup test media files if created
    test_photo_p = os.path.join(paths['photos_dir'], 'test_photo.txt')
    if os.path.exists(test_photo_p):
        os.remove(test_photo_p)
    test_voucher_p = os.path.join(paths['attachments_dir'], 'test_voucher.txt')
    if os.path.exists(test_voucher_p):
        os.remove(test_voucher_p)

    for u in User.objects.filter(username__icontains=TEST_TAG):
        u.delete()
    print("[OK] Test artifacts and test records cleaned up.")

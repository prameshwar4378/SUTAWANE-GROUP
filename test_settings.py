import os
import sys
import json
import io

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
from django.conf import settings
from MyApp.models import User, SystemSetting
from MyApp.auth_utils import hash_password

TEST_TAG = "TEST_SETTINGS"

print("=" * 70)
print("STARTING SETTINGS & MASTER BRANDING VERIFICATION SUITE")
print("=" * 70)

# 1. Setup session
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
    role="CLASS_OWNER",
    is_active=True,
)

client = Client()
session = client.session
session['user_id'] = owner.id
session['username'] = owner.username
session['role'] = owner.role
session.save()
print(f"[OK] Logged in session as: {owner.username} ({owner.role})")

# Backup original settings
original_settings = {s.key: s.value for s in SystemSetting.objects.all()}

created_logos = []

try:
    # 2. Test GET /settings/ UI Rendering
    print("\n--- 2. Testing GET /settings/ UI Page Rendering ---")
    resp = client.get('/settings/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert "<h1 class=\"text-2xl font-bold tracking-tight text-foreground\">Settings</h1>" in content or "Settings" in content
    assert "Common Master Institute Logo" in content or "Class / Institute Identity" in content
    assert "Institute Profile" in content
    assert "name=\"institute_name\"" in content
    assert "name=\"tagline\"" in content
    assert "name=\"receipt_footer\"" in content
    print("[OK] /settings/ rendered with both cards, inputs, and logo management.")

    # 3. Test GET /settings/?format=json
    print("\n--- 3. Testing GET /settings/?format=json ---")
    resp_json = client.get('/settings/?format=json')
    assert resp_json.status_code == 200
    jdata = resp_json.json()
    assert 'institute_name' in jdata
    assert 'tagline' in jdata
    assert 'phone' in jdata
    assert 'email' in jdata
    assert 'receipt_footer' in jdata
    print(f"[OK] format=json returned settings: {jdata['institute_name']} ({jdata['tagline']})")

    # 4. Test POST /settings/ Update Profile
    print("\n--- 4. Testing Form POST Profile Update ---")
    update_data = {
        'action': 'save_profile',
        'institute_name': 'Sutawane IIT-JEE & NEET Academy',
        'tagline': 'Building Future Rankers with Concept Mastery',
        'phone': '+91 94221 55667',
        'email': 'director@sutawaneacademy.com',
        'address': 'Main Administrative Complex, Civil Lines, Nagpur',
        'website': 'https://www.sutawaneacademy.com',
        'receipt_footer': 'Strictly non-refundable. Preserving this receipt is mandatory.',
    }
    resp_post = client.post('/settings/', update_data, follow=True)
    assert resp_post.status_code == 200
    post_content = resp_post.content.decode('utf-8')
    assert "Institute settings saved successfully" in post_content or "Settings updated successfully" in post_content
    assert "Sutawane IIT-JEE &amp; NEET Academy" in post_content or "Sutawane IIT-JEE & NEET Academy" in post_content

    # Verify DB
    inst_name = SystemSetting.objects.get(key='institute_name').value
    assert inst_name == 'Sutawane IIT-JEE & NEET Academy'
    print("[OK] Institute profile successfully saved and verified in DB.")

    # 5. Test Master Logo Upload via Form POST
    print("\n--- 5. Testing Master Logo Upload via Form POST ---")
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    logo_file = SimpleUploadedFile("master_logo_test.png", dummy_png, content_type="image/png")
    
    resp_logo = client.post('/settings/', {'action': 'upload_logo', 'logo': logo_file}, follow=True)
    assert resp_logo.status_code == 200
    logo_content = resp_logo.content.decode('utf-8')
    assert "Master institute logo uploaded successfully" in logo_content or "logo uploaded successfully" in logo_content
    
    logo_setting = SystemSetting.objects.get(key='logo_url').value
    assert logo_setting.startswith('/media/photos/logo-master-')
    created_logos.append(logo_setting)
    print(f"[OK] Master logo uploaded to: {logo_setting}")

    # 6. Test Master Logo Remove via Form POST
    print("\n--- 6. Testing Master Logo Removal ---")
    resp_rm = client.post('/settings/', {'action': 'remove_logo'}, follow=True)
    assert resp_rm.status_code == 200
    rm_content = resp_rm.content.decode('utf-8')
    assert "Master institute logo removed" in rm_content or "logo removed" in rm_content
    assert SystemSetting.objects.get(key='logo_url').value == ''
    print("[OK] Master logo removed successfully.")

    # 7. Test REST API Endpoints (100% React Parity)
    print("\n--- 7. Testing Settings REST API Endpoints ---")
    # GET /api/settings/
    api_get = client.get('/api/settings/')
    assert api_get.status_code == 200
    assert api_get.json()['institute_name'] == 'Sutawane IIT-JEE & NEET Academy'
    print("[OK] GET /api/settings/ returned accurate config.")

    # POST /api/settings/
    api_post = client.post(
        '/api/settings/',
        json.dumps({'institute_name': 'Sutawane Premier Classes'}),
        content_type='application/json'
    )
    assert api_post.status_code == 200
    assert api_post.json()['success'] is True
    assert SystemSetting.objects.get(key='institute_name').value == 'Sutawane Premier Classes'
    print("[OK] POST /api/settings/ updated institute name via JSON body.")

    # POST /api/settings/logo/
    logo_file2 = SimpleUploadedFile("api_logo.png", dummy_png, content_type="image/png")
    api_logo = client.post('/api/settings/logo/', {'logo': logo_file2})
    assert api_logo.status_code == 200
    api_logo_j = api_logo.json()
    assert api_logo_j['success'] is True
    assert 'logoUrl' in api_logo_j
    created_logos.append(api_logo_j['logoUrl'])
    print(f"[OK] POST /api/settings/logo/ uploaded logo via API: {api_logo_j['logoUrl']}")

    # DELETE /api/settings/logo/
    api_del = client.delete('/api/settings/logo/')
    assert api_del.status_code == 200
    assert api_del.json()['success'] is True
    assert SystemSetting.objects.get(key='logo_url').value == ''
    print("[OK] DELETE /api/settings/logo/ cleared master logo via API.")

    print("\n" + "=" * 70)
    print("ALL SETTINGS & MASTER BRANDING TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

finally:
    # Cleanup created logos from disk
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    for l_url in created_logos:
        f_name = os.path.basename(l_url)
        f_path = os.path.join(photos_dir, f_name)
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass

    # Restore original settings
    for k, v in original_settings.items():
        SystemSetting.objects.update_or_create(key=k, defaults={'value': v})

    for u in User.objects.filter(username__icontains=TEST_TAG):
        u.delete()
    print("[OK] Settings test environment cleanly restored.")

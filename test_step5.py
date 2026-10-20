import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from django.test import Client
from MyApp.models import User, Branch, AcademicSession

# Cleanup any leftover test branches/sessions from previous runs
Branch.objects.filter(code='NGP').delete()
AcademicSession.objects.filter(name='2028-29').delete()

client = Client()

# Log in as Class Owner
login_res = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
print("Logged in as Owner successfully!")

print("\n--- 1. Testing GET /branches/ ---")
res_branches = client.get('/branches/')
print("Status Code:", res_branches.status_code)
assert res_branches.status_code == 200
content_branches = res_branches.content.decode('utf-8')
assert 'Branch & Center Management' in content_branches or 'Branch &amp; Center Management' in content_branches
assert 'Vaijapur' in content_branches
assert 'VAI' in content_branches
print("Branches directory loaded with existing branch 'Vaijapur'!")

print("\n--- 2. Testing POST /branches/ (Create Branch) ---")
res_create_branch = client.post('/branches/', {
    'action': 'create',
    'name': 'Nagpur Central Complex',
    'code': 'NGP',
    'contact_person': 'Director Sir',
    'phone': '9876543210',
    'address': 'Sitabuldi Square, Nagpur',
})
assert res_create_branch.status_code == 302
ngp = Branch.objects.filter(code='NGP').first()
assert ngp is not None, "Nagpur branch not found in DB!"
assert ngp.name == 'Nagpur Central Complex'
print(f"Branch '{ngp.name}' ({ngp.code}) created successfully!")

print("\n--- 3. Testing POST /branches/ (Update Branch) ---")
res_update_branch = client.post('/branches/', {
    'action': 'update',
    'branch_id': ngp.id,
    'name': 'Nagpur Sitabuldi Main Branch',
    'code': 'NGP',
    'contact_person': 'Director Sutawane Sir',
    'phone': '9876543219',
    'address': 'Main Metro Complex, Nagpur',
})
assert res_update_branch.status_code == 302
ngp.refresh_from_db()
assert ngp.name == 'Nagpur Sitabuldi Main Branch'
print(f"Branch updated to '{ngp.name}' successfully!")

print("\n--- 4. Testing POST /branches/ (Toggle Status) ---")
res_toggle_branch = client.post('/branches/', {
    'action': 'toggle_status',
    'branch_id': ngp.id,
})
assert res_toggle_branch.status_code == 302
ngp.refresh_from_db()
assert ngp.is_active is False
print("Branch status toggle verified (set to Inactive)!")
# Toggle back to active
client.post('/branches/', {'action': 'toggle_status', 'branch_id': ngp.id})
ngp.refresh_from_db()
assert ngp.is_active is True

print("\n--- 5. Testing GET /sessions/ ---")
res_sessions = client.get('/sessions/')
print("Status Code:", res_sessions.status_code)
assert res_sessions.status_code == 200
content_sessions = res_sessions.content.decode('utf-8')
assert 'Academic Sessions' in content_sessions
assert '2026-27' in content_sessions
assert '2027-28' in content_sessions
print("Academic sessions list loaded successfully!")

print("\n--- 6. Testing POST /sessions/ (Set Current Session) ---")
s2026 = AcademicSession.objects.get(name='2026-27')
res_set_current = client.post('/sessions/', {
    'action': 'set_current',
    'session_id': s2026.id,
})
assert res_set_current.status_code == 302
s2026.refresh_from_db()
assert s2026.is_current is True
s2027 = AcademicSession.objects.get(name='2027-28')
assert s2027.is_current is False
print(f"Session '{s2026.name}' set as current session!")

print("\n--- 7. Testing POST /sessions/ (Create New Session) ---")
res_create_sess = client.post('/sessions/', {
    'action': 'create',
    'name': '2028-29',
    'display_name': 'Academic Year 2028–29',
    'start_date': '2028-06-01',
    'end_date': '2029-05-31',
})
assert res_create_sess.status_code == 302
s2028 = AcademicSession.objects.filter(name='2028-29').first()
assert s2028 is not None
print(f"Session '{s2028.display_name}' created successfully!")

print("\nALL STEP 5 DELIVERABLES TESTED & VERIFIED WITH 100% SUCCESS!")

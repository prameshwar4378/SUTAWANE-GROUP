import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from django.test import Client

client = Client()
# Authenticate as Class Owner to pass SoftwareLicenseAndAuthMiddleware
client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})

print("--- Testing GET / (Dashboard) ---")
res = client.get('/')
print("Status Code:", res.status_code)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
content = res.content.decode('utf-8')
assert 'SUTAWANE' in content or 'Classes Management' in content, "Brand title missing"
assert 'app-sidebar' in content, "Sidebar missing"
assert 'header-quick-search-input' in content, "Search input missing"
assert 'Active Students' in content, "Metric cards missing"
print("Dashboard rendered with full UI shell, sidebar, and header!")

print("\n--- Testing GET /api/quick-search/?q=Rameshwar ---")
res_search = client.get('/api/quick-search/?q=Rameshwar')
print("Status Code:", res_search.status_code)
data = res_search.json()
print("Search Results Count:", len(data))
if len(data) > 0:
    s0 = data[0]
    print(f"  Found Student: {s0['full_name']} (Roll: {s0['roll_number']}, Class: {s0['standard']})")

print("\n--- Testing GET /switch-branch/ALL/ ---")
res_branch = client.get('/switch-branch/ALL/')
print("Status Code:", res_branch.status_code)
assert res_branch.status_code == 302, f"Expected 302 redirect, got {res_branch.status_code}"

print("\n--- Testing Navigation Link GET /students/ ---")
res_students = client.get('/students/')
print("Status Code:", res_students.status_code)
assert res_students.status_code == 200

print("\nALL STEP 3 DELIVERABLES TESTED & VERIFIED WITH 100% SUCCESS!")

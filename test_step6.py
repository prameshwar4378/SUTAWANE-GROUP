import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from django.test import Client
from MyApp.models import Course, StudentAdmission

# Pre-cleanup test artifacts if any
Course.objects.filter(code='CET-CRASH').delete()

client = Client()

# Log in as Class Owner
login_res = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
print("Logged in as Owner successfully!")

print("\n--- 1. Testing GET /courses/ (Catalog Display) ---")
res = client.get('/courses/')
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
content = res.content.decode('utf-8')

assert 'Classes & Courses Management' in content or 'Classes &amp; Courses Management' in content
assert 'Class 10' in content
assert 'Class 11 Science' in content
assert 'Class 12 Science' in content
assert 'Total Courses' in content
assert 'Active Offerings' in content
assert 'Enrolled Students' in content
print("Courses catalog loaded successfully with KPI statistics and courses!")

print("\n--- 2. Testing POST /courses/ (Create Course) ---")
res_create = client.post('/courses/', {
    'action': 'create',
    'name': 'MHT-CET Crash Course 2026',
    'code': 'CET-CRASH',
    'default_fee': '12000',
    'sort_order': '9',
    'is_active': 'on',
    'description': 'Intensive 60-day physics, chemistry, and mathematics revision program.',
})
assert res_create.status_code == 302
created_c = Course.objects.filter(code='CET-CRASH').first()
assert created_c is not None, "Created course not found in database!"
assert created_c.name == 'MHT-CET Crash Course 2026'
assert created_c.default_fee == 12000.0
assert created_c.sort_order == 9
assert created_c.is_active is True
print(f"Course '{created_c.name}' ({created_c.code}) created successfully!")

print("\n--- 3. Testing POST /courses/ (Duplicate Name Protection) ---")
res_dup = client.post('/courses/', {
    'action': 'create',
    'name': 'MHT-CET Crash Course 2026',
    'code': 'CET-NEW',
})
assert res_dup.status_code == 302
# Confirm duplicate wasn't created
assert Course.objects.filter(code='CET-NEW').count() == 0
print("Duplicate course name prevention verified!")

print("\n--- 4. Testing POST /courses/ (Update Course) ---")
res_update = client.post('/courses/', {
    'action': 'update',
    'course_id': created_c.id,
    'name': 'MHT-CET Advanced Crash Course',
    'code': 'CET-CRASH',
    'default_fee': '14500',
    'sort_order': '15',
    'is_active': 'on',
    'description': 'Updated syllabus with full mock tests.',
})
assert res_update.status_code == 302
created_c.refresh_from_db()
assert created_c.name == 'MHT-CET Advanced Crash Course'
assert created_c.default_fee == 14500.0
assert created_c.sort_order == 15
print(f"Course updated to '{created_c.name}' with fee Rs.{created_c.default_fee} successfully!")

print("\n--- 5. Testing POST /courses/ (Toggle Active Status) ---")
res_toggle = client.post('/courses/', {
    'action': 'toggle_status',
    'course_id': created_c.id,
})
assert res_toggle.status_code == 302
created_c.refresh_from_db()
assert created_c.is_active is False
print("Course status toggled to Inactive!")

res_toggle_back = client.post('/courses/', {
    'action': 'toggle_status',
    'course_id': created_c.id,
})
assert res_toggle_back.status_code == 302
created_c.refresh_from_db()
assert created_c.is_active is True
print("Course status toggled back to Active!")

print("\n--- 6. Testing Course Deletion Protection with Enrollments ---")
sci_c = Course.objects.filter(name='Class 11 Science').first()
assert sci_c is not None
enrolled_sci = StudentAdmission.objects.filter(standard=sci_c.name).count()
print(f"Class 11 Science has {enrolled_sci} student enrollment(s).")
if enrolled_sci > 0:
    res_del_protected = client.post('/courses/', {
        'action': 'delete',
        'course_id': sci_c.id,
    })
    assert res_del_protected.status_code == 302
    assert Course.objects.filter(id=sci_c.id).exists(), "Course with active enrollments was incorrectly deleted!"
    print("Course deletion was safely blocked due to active enrollments!")

print("\n--- 7. Testing POST /courses/ (Delete Course with 0 Enrollments) ---")
res_del = client.post('/courses/', {
    'action': 'delete',
    'course_id': created_c.id,
})
assert res_del.status_code == 302
assert not Course.objects.filter(id=created_c.id).exists()
print("Course with 0 enrollments safely deleted!")

print("\n--- 8. Testing GET /courses/?q=Science (Search Filter) ---")
res_search = client.get('/courses/?q=Science')
assert res_search.status_code == 200
search_content = res_search.content.decode('utf-8')
assert 'Class 11 Science' in search_content
assert 'Class 12 Science' in search_content
print("Search filter query verified successfully!")

print("\nALL STEP 6 DELIVERABLES TESTED & VERIFIED WITH 100% SUCCESS!")

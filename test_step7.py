import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from django.test import Client
from django.utils import timezone
from MyApp.models import Student, StudentAdmission, FeePlan, Installment, Branch, AcademicSession

# Pre-cleanup test artifacts if any
for s in Student.objects.filter(full_name='Aarav Anil Deshmukh'):
    for adm in s.admissions.all():
        if hasattr(adm, 'fee_plan'):
            adm.fee_plan.installments.all().delete()
            adm.fee_plan.delete()
        adm.payments.all().delete()
    s.previous_dues.all().delete()
    s.admissions.all().delete()
    s.delete()

client = Client()

# Log in as Class Owner
login_res = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
client.get('/switch-session/ALL/')
print("Logged in as Owner successfully!")

print("\n--- 1. Testing GET /students/ (Students Directory & KPIs) ---")
res = client.get('/students/')
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
content = res.content.decode('utf-8')
assert 'Student Master Management' in content
assert 'Enrolled Students' in content
assert 'Session Total Fees' in content
assert 'Session Paid Fees' in content
assert 'Session Pending Fees' in content
assert 'Overall Pending Amount' in content
assert 'Rameshwar Pawar' in content
assert 'SC-6437-264' in content
print("Students directory and KPI ribbon loaded successfully with existing student!")

print("\n--- 2. Testing Filters on GET /students/ ---")
res_search = client.get('/students/?q=Rameshwar')
assert res_search.status_code == 200
assert 'Rameshwar Pawar' in res_search.content.decode('utf-8')

res_course = client.get('/students/?standard=Class+11+Science')
assert res_course.status_code == 200
assert 'Rameshwar Pawar' in res_course.content.decode('utf-8')
print("Search and course filter queries verified successfully!")

print("\n--- 3. Testing POST /students/ (New Student Admission) ---")
vai_branch = Branch.objects.filter(code='VAI').first() or Branch.objects.first()
sess = AcademicSession.objects.filter(is_current=True).first() or AcademicSession.objects.first()

res_admit = client.post('/students/', {
    'action': 'create',
    'full_name': 'Aarav Anil Deshmukh',
    'roll_number': 'TEST-ROLL-101',
    'standard': 'Class 10',
    'branch_id': vai_branch.id,
    'session_id': sess.id,
    'parent_phone': '9822012345',
    'student_phone': '9822054321',
    'address': 'Tilak Road, Vaijapur',
    'total_fees': '22000',
    'due_date': '2026-12-15',
})
assert res_admit.status_code == 302, f"Expected 302 redirect, got {res_admit.status_code}"

aarav = Student.objects.filter(full_name='Aarav Anil Deshmukh').first()
assert aarav is not None, "Admitted student Aarav Deshmukh not found in database!"
assert aarav.student_code.startswith('SC-')
assert aarav.parent_phone == '9822012345'
assert aarav.student_phone == '9822054321'
assert aarav.address == 'Tilak Road, Vaijapur'

admission = aarav.admissions.first()
assert admission is not None, "Admission record not found!"
assert admission.roll_number == 'TEST-ROLL-101'
assert admission.standard == 'Class 10'
assert admission.branch == vai_branch

fee_plan = admission.fee_plan
assert fee_plan is not None, "Fee plan not found!"
assert fee_plan.net_payable == 22000.0

installment = fee_plan.installments.first()
assert installment is not None, "Installment milestone not found!"
assert installment.amount_due == 22000.0
assert timezone.localtime(installment.due_date).strftime('%Y-%m-%d') == '2026-12-15'
print(f"Student '{aarav.full_name}' ({aarav.student_code}) admitted with FeePlan Rs. {fee_plan.net_payable}!")

print("\n--- 4. Testing GET /students/<student_id>/ (Student Profile View) ---")
res_profile = client.get(f'/students/{aarav.id}/')
assert res_profile.status_code == 200
profile_content = res_profile.content.decode('utf-8')
assert 'Aarav Anil Deshmukh' in profile_content
assert aarav.student_code in profile_content
assert 'TEST-ROLL-101' in profile_content
assert 'Class 10' in profile_content
assert 'Installment Schedule' in profile_content
assert '22000' in profile_content
print("Student detailed profile and installment ledger verified successfully!")

print("\n--- 5. Testing POST /students/<student_id>/ (Update Profile) ---")
res_update_prof = client.post(f'/students/{aarav.id}/', {
    'action': 'update_profile',
    'admission_id': admission.id,
    'full_name': 'Aarav Anil Deshmukh',
    'roll_number': 'TEST-ROLL-102',
    'standard': 'Class 10',
    'parent_phone': '9822012345',
    'student_phone': '9822099999',
    'address': 'Main Market Road, Vaijapur',
})
assert res_update_prof.status_code == 302
aarav.refresh_from_db()
admission.refresh_from_db()
assert admission.roll_number == 'TEST-ROLL-102'
assert aarav.address == 'Main Market Road, Vaijapur'
assert aarav.student_phone == '9822099999'
print(f"Profile updated: Roll number changed to '{admission.roll_number}' and address to '{aarav.address}'!")

print("\n--- 6. Testing POST /students/<student_id>/ (Update Due Date) ---")
res_due = client.post(f'/students/{aarav.id}/', {
    'action': 'update_due_date',
    'installment_id': installment.id,
    'due_date': '2026-12-30',
})
assert res_due.status_code == 302
installment.refresh_from_db()
assert timezone.localtime(installment.due_date).strftime('%Y-%m-%d') == '2026-12-30'
print(f"Installment due date updated successfully to: {installment.due_date}!")

print("\n--- 7. Testing POST /students/<student_id>/ (Toggle Archive) ---")
res_arch = client.post(f'/students/{aarav.id}/', {
    'action': 'toggle_archive',
})
assert res_arch.status_code == 302
admission.refresh_from_db()
assert admission.is_active is False
print("Student enrollment archived successfully (isActive = False)!")

# Reactivate
client.post(f'/students/{aarav.id}/', {'action': 'toggle_archive'})
admission.refresh_from_db()
assert admission.is_active is True
print("Student enrollment reactivated successfully (isActive = True)!")

print("\n--- 8. Testing POST /students/<student_id>/ (Permanent Cascade Delete) ---")
res_del = client.post(f'/students/{aarav.id}/', {
    'action': 'delete',
})
assert res_del.status_code == 302
assert not Student.objects.filter(id=aarav.id).exists(), "Student was not deleted!"
assert not StudentAdmission.objects.filter(id=admission.id).exists(), "Admission was not cascade deleted!"
assert not FeePlan.objects.filter(id=fee_plan.id).exists(), "FeePlan was not cascade deleted!"
assert not Installment.objects.filter(id=installment.id).exists(), "Installment was not cascade deleted!"
print("Student and all cascaded admissions/plans/installments permanently deleted!")

# Confirm Rameshwar Pawar is intact
assert Student.objects.filter(full_name='Rameshwar Pawar').exists()
print("Original student record 'Rameshwar Pawar' remains completely intact!")

print("\nALL STEP 7 DELIVERABLES TESTED & VERIFIED WITH 100% SUCCESS!")

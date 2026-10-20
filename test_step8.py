import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
# Add apps to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps'))
django.setup()

from django.test import Client
from django.utils import timezone
from MyApp.models import (
    Student, StudentAdmission, FeePlan, Installment, Branch,
    AcademicSession, PreviousSessionDue, Payment
)

def cleanup_student(name):
    for s in Student.objects.filter(full_name=name):
        for adm in s.admissions.all():
            if hasattr(adm, 'fee_plan'):
                adm.fee_plan.installments.all().delete()
                adm.fee_plan.delete()
            adm.payments.all().delete()
        s.previous_dues.all().delete()
        s.payments.all().delete()
        s.admissions.all().delete()
        s.delete()

# Pre-cleanup test students
cleanup_student('Ananya Rajesh Kulkarni')
cleanup_student('Batch Student Alpha')
cleanup_student('Batch Student Beta')

client = Client()

print("=" * 70)
print("RUNNING STEP 8 AUTOMATED VERIFICATION SUITE")
print("STUDENT PROMOTION ENGINE (INDIVIDUAL & BATCH WITH PREVIOUS DUES)")
print("=" * 70)

# 1. Login
print("\n--- 1. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302, f"Expected 302, got {login_res.status_code}"
print("Owner authenticated successfully!")

# 2. Check academic sessions
sessions = list(AcademicSession.objects.filter(isActive=True).order_by('name'))
assert len(sessions) >= 2, f"Expected at least 2 active academic sessions for promotion testing, found {len(sessions)}"
session_1 = sessions[0]  # e.g. 2026-27
session_2 = sessions[1]  # e.g. 2027-28
branch = Branch.objects.filter(is_active=True).first()
print(f"Testing with Sessions: Session 1 = '{session_1.name}', Target Session 2 = '{session_2.name}', Branch = '{branch.name}'")

# 3. Create test student in Session 1 with unpaid dues
print("\n--- 2. Setting Up Test Student in Session 1 ---")
student = Student.objects.create(
    student_code='SC-STEP8-001',
    full_name='Ananya Rajesh Kulkarni',
    parent_phone='9811122233',
    student_phone='9811122244',
    address='MG Road, Vaijapur',
)
adm1 = StudentAdmission.objects.create(
    student=student,
    branch=branch,
    session=session_1,
    roll_number='ARK-101',
    standard='Class 10',
    admission_date=timezone.now(),
    is_active=True,
)
fp1 = FeePlan.objects.create(
    admission=adm1,
    session=session_1,
    total_fees=25000.0,
    total_discount=0.0,
    net_payable=25000.0,
)
Installment.objects.create(
    fee_plan=fp1,
    installment_no=1,
    label='Term 1',
    due_date=timezone.now(),
    amount_due=25000.0,
)
# Make partial payment of 10,000 (leaves 15,000 pending due)
Payment.objects.create(
    student=student,
    branch=branch,
    admission=adm1,
    session=session_1,
    receipt_number='REC-STEP8-001',
    total_amount=10000.0,
    payment_mode='CASH',
)
print(f"Student '{student.full_name}' admitted in '{session_1.name}' ({adm1.standard}). Fees: 25,000, Paid: 10,000, Pending Due: 15,000.")

# 4. Test Single Student Promotion Preview
print("\n--- 3. Testing GET /students/<id>/promote-preview/ ---")
res_preview = client.get(f'/students/{student.id}/promote-preview/?target_session_id={session_2.id}', HTTP_HX_REQUEST='true')
assert res_preview.status_code == 200, f"Expected 200, got {res_preview.status_code}"
preview_html = res_preview.content.decode('utf-8')
assert 'Promote Student to Next Academic Session' in preview_html
assert 'Ananya Rajesh Kulkarni' in preview_html
assert 'ARK-101' in preview_html
assert '15000' in preview_html
assert 'Class 11 Science' in preview_html  # Auto-suggested from Class 10
assert 'ARK-101-N' in preview_html        # Auto-suggested roll
print("Individual promotion preview rendered correctly with dues and suggested standard 'Class 11 Science'!")

# Also test JSON preview
res_json = client.get(f'/students/{student.id}/promote-preview/?target_session_id={session_2.id}', HTTP_ACCEPT='application/json')
assert res_json.status_code == 200
data = res_json.json()
assert data['suggestedStandard'] == 'Class 11 Science'
assert data['currentPendingDue'] == 15000.0
assert data['isAlreadyPromoted'] is False
print("JSON preview response verified successfully!")

# 5. Execute Individual Promotion to Target Session 2
print("\n--- 4. Testing POST /students/<id>/promote/ (Execution) ---")
res_promote = client.post(
    f'/students/{student.id}/promote/',
    {
        'target_session_id': session_2.id,
        'target_branch_id': branch.id,
        'target_standard': 'Class 11 Science',
        'new_roll_number': 'ARK-101-N',
        'new_total_fees': '35000',
        'carry_forward_due': 'true',
        'due_notes': 'Carryover from Class 10 due balance',
    },
    HTTP_HX_REQUEST='true'
)
assert res_promote.status_code == 200, f"Expected 200, got {res_promote.status_code}"
promote_html = res_promote.content.decode('utf-8')
assert 'Student Promoted Successfully!' in promote_html
assert 'Class 11 Science' in promote_html
assert 'ARK-101-N' in promote_html

# Verify in database
admissions = student.admissions.all().order_by('-created_at')
assert admissions.count() == 2, f"Expected 2 admissions for student, found {admissions.count()}"
new_adm = admissions.first()
assert new_adm.session == session_2, f"Expected session {session_2.name}, got {new_adm.session.name}"
assert new_adm.standard == 'Class 11 Science'
assert new_adm.roll_number == 'ARK-101-N'

# Verify fresh FeePlan
assert hasattr(new_adm, 'fee_plan'), "New admission has no fee plan!"
new_fp = new_adm.fee_plan
assert new_fp.net_payable == 35000.0, f"Expected 35000.0, got {new_fp.net_payable}"
assert new_fp.installments.count() == 1
assert new_fp.installments.first().amount_due == 35000.0

# Verify PreviousSessionDue record
due = PreviousSessionDue.objects.filter(student=student, current_session=session_2).first()
assert due is not None, "PreviousSessionDue record not found!"
assert due.original_session == session_1
assert due.outstanding_amount == 15000.0
assert due.collected_amount == 0.0
print(f"Verified promotion: New Admission created in '{session_2.name}' (Class 11 Science, Net: 35,000) and PreviousSessionDue recorded for Rs. 15,000!")

# 6. Test Duplicate Promotion Guard
print("\n--- 5. Testing Duplicate Promotion Guard ---")
res_dup = client.post(
    f'/students/{student.id}/promote/',
    {
        'target_session_id': session_2.id,
        'target_branch_id': branch.id,
        'target_standard': 'Class 11 Science',
        'new_roll_number': 'ARK-101-DIFF',
        'new_total_fees': '35000',
    },
    HTTP_HX_REQUEST='true'
)
assert res_dup.status_code == 200
assert 'already admitted' in res_dup.content.decode('utf-8').lower()
print("Duplicate admission in same target session was successfully blocked!")

# 7. Test Batch Promotion Modal & Execution
print("\n--- 6. Testing Batch Promotion Engine ---")
# Create 2 batch test students in Session 1
student_a = Student.objects.create(
    student_code='SC-STEP8-002',
    full_name='Batch Student Alpha',
    parent_phone='9822233344',
)
StudentAdmission.objects.create(
    student=student_a,
    branch=branch,
    session=session_1,
    roll_number='BAT-01',
    standard='Class 9',
    admission_date=timezone.now(),
    is_active=True,
)
student_b = Student.objects.create(
    student_code='SC-STEP8-003',
    full_name='Batch Student Beta',
    parent_phone='9833344455',
)
StudentAdmission.objects.create(
    student=student_b,
    branch=branch,
    session=session_1,
    roll_number='BAT-02',
    standard='Class 9',
    admission_date=timezone.now(),
    is_active=True,
)

# Open Batch Modal
res_batch_modal = client.post(
    '/students/batch-promote/modal/',
    {'student_ids': [student_a.id, student_b.id]},
    HTTP_HX_REQUEST='true'
)
assert res_batch_modal.status_code == 200
batch_modal_html = res_batch_modal.content.decode('utf-8')
assert 'Batch Promote Students (2 Selected)' in batch_modal_html
assert 'Batch Student Alpha' in batch_modal_html
assert 'Batch Student Beta' in batch_modal_html
print("Batch promote modal rendered successfully with both selected students!")

# Execute Batch Promotion
res_batch_exec = client.post(
    '/students/batch-promote/',
    {
        'student_ids': [student_a.id, student_b.id],
        'target_session_id': session_2.id,
        'target_branch_id': 'KEEP',
        'target_standard': 'Class 10',
        'default_total_fees': '30000',
        'carry_forward_dues': 'true',
    },
    HTTP_HX_REQUEST='true'
)
assert res_batch_exec.status_code == 200
batch_exec_html = res_batch_exec.content.decode('utf-8')
assert 'Batch Promotion Completed!' in batch_exec_html
assert 'Successfully promoted <strong>2</strong> out of <strong>2</strong>' in batch_exec_html

# Verify both admitted in session 2
adm_a = student_a.admissions.filter(session=session_2).first()
adm_b = student_b.admissions.filter(session=session_2).first()
assert adm_a is not None and adm_a.standard == 'Class 10'
assert adm_b is not None and adm_b.standard == 'Class 10'
assert adm_a.fee_plan.net_payable == 30000.0
assert adm_b.fee_plan.net_payable == 30000.0
print(f"Batch promotion verified! Both students promoted to '{session_2.name}' (Class 10) with FeePlan Rs. 30,000.")

# Test Batch Duplicate Skip Handling
res_batch_repeat = client.post(
    '/students/batch-promote/',
    {
        'student_ids': [student_a.id, student_b.id],
        'target_session_id': session_2.id,
        'target_branch_id': 'KEEP',
        'target_standard': 'Class 10',
        'default_total_fees': '30000',
    },
    HTTP_HX_REQUEST='true'
)
assert res_batch_repeat.status_code == 200
repeat_html = res_batch_repeat.content.decode('utf-8')
assert 'Skipped 2 student(s)' in repeat_html
print("Batch re-promotion guard verified: accurately skipped already-promoted students!")

# 8. Post-cleanup
print("\n--- 7. Cleanup Test Artifacts ---")
cleanup_student('Ananya Rajesh Kulkarni')
cleanup_student('Batch Student Alpha')
cleanup_student('Batch Student Beta')
print("Test students cleaned up cleanly.")

print("\n" + "=" * 70)
print("ALL STEP 8 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

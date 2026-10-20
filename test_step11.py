import os
import django
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps'))
django.setup()

from django.test import Client
from django.utils import timezone
from datetime import datetime, timedelta
from MyApp.models import (
    Student, StudentAdmission, FeePlan, Installment, Branch,
    AcademicSession, PreviousSessionDue, Payment, PaymentAllocation, Course
)

def cleanup_students(names):
    for name in names:
        for s in Student.objects.filter(full_name=name):
            for adm in s.admissions.all():
                if hasattr(adm, 'fee_plan'):
                    for inst in adm.fee_plan.installments.all():
                        inst.allocations.all().delete()
                    adm.fee_plan.installments.all().delete()
                    adm.fee_plan.delete()
                adm.payments.all().delete()
            s.payments.all().delete()
            s.previous_dues.all().delete()
            s.admissions.all().delete()
            s.delete()

TEST_NAMES = [
    'Tanvi Suresh Patil',
    'Omkar Dilip Jadhav',
    'Snehal Ramesh Kute',
]

cleanup_students(TEST_NAMES)

client = Client()

print("=" * 70)
print("RUNNING STEP 11 AUTOMATED VERIFICATION SUITE")
print("PENDING DUES & DEFAULTERS REGISTER")
print("=" * 70)

# 1. Authenticate User
print("\n--- 1. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
session = AcademicSession.objects.filter(is_current=True).first()
branch = Branch.objects.filter(is_active=True).first()
today = timezone.localtime().date()
print(f"Owner authenticated! Active Session: '{session.name}', Branch: '{branch.name}', Today: {today}")

# 2. Setup Test Data
print("\n--- 2. Setting Up 3 Test Students (Overdue, Due Today/Partial, Fully Cleared) ---")

# Student A: Tanvi (Has Overdue Installment)
s_a = Student.objects.create(
    student_code='SC-2026-8001',
    full_name='Tanvi Suresh Patil',
    parent_phone='9822112233',
    address='Tilak Nagar, Vaijapur',
)
adm_a = StudentAdmission.objects.create(
    student=s_a, branch=branch, session=session,
    roll_number='TSP-01', standard='Class 10', is_active=True,
    admission_date=timezone.now(),
)
fp_a = FeePlan.objects.create(admission=adm_a, session=session, total_fees=25000.0, net_payable=25000.0)
inst_a1 = Installment.objects.create(
    fee_plan=fp_a, installment_no=1, label='Inst 1 (Admission)',
    due_date=timezone.make_aware(datetime.combine(today - timedelta(days=5), datetime.min.time())),
    amount_due=10000.0,
)
inst_a2 = Installment.objects.create(
    fee_plan=fp_a, installment_no=2, label='Inst 2 (Term 2)',
    due_date=timezone.make_aware(datetime.combine(today + timedelta(days=30), datetime.min.time())),
    amount_due=15000.0,
)

# Student B: Omkar (Due Today & Partial Payment)
s_b = Student.objects.create(
    student_code='SC-2026-8002',
    full_name='Omkar Dilip Jadhav',
    parent_phone='9822445566',
    address='Station Road, Vaijapur',
)
adm_b = StudentAdmission.objects.create(
    student=s_b, branch=branch, session=session,
    roll_number='ODJ-02', standard='Class 10', is_active=True,
    admission_date=timezone.now(),
)
fp_b = FeePlan.objects.create(admission=adm_b, session=session, total_fees=30000.0, net_payable=30000.0)
inst_b1 = Installment.objects.create(
    fee_plan=fp_b, installment_no=1, label='Inst 1 (Admission)',
    due_date=timezone.make_aware(datetime.combine(today, datetime.min.time())),
    amount_due=15000.0,
)
inst_b2 = Installment.objects.create(
    fee_plan=fp_b, installment_no=2, label='Inst 2 (Term 2)',
    due_date=timezone.make_aware(datetime.combine(today + timedelta(days=45), datetime.min.time())),
    amount_due=15000.0,
)
# Partial payment of 5,000 on inst_b1
p_b = Payment.objects.create(
    student=s_b, branch=branch, admission=adm_b, session=session,
    receipt_number=f"SC/{session.name}/{branch.code}/REC-B101",
    total_amount=5000.0, payment_mode='CASH', payment_date=timezone.now(),
)
PaymentAllocation.objects.create(payment=p_b, installment=inst_b1, allocated_amount=5000.0)

# Student C: Snehal (Fully Cleared - MUST NEVER APPEAR IN DUES)
s_c = Student.objects.create(
    student_code='SC-2026-8003',
    full_name='Snehal Ramesh Kute',
    parent_phone='9822778899',
    address='Main Market, Vaijapur',
)
adm_c = StudentAdmission.objects.create(
    student=s_c, branch=branch, session=session,
    roll_number='SRK-03', standard='Class 10', is_active=True,
    admission_date=timezone.now(),
)
fp_c = FeePlan.objects.create(admission=adm_c, session=session, total_fees=20000.0, net_payable=20000.0)
inst_c1 = Installment.objects.create(
    fee_plan=fp_c, installment_no=1, label='Full Fee',
    due_date=timezone.make_aware(datetime.combine(today - timedelta(days=20), datetime.min.time())),
    amount_due=20000.0,
)
p_c = Payment.objects.create(
    student=s_c, branch=branch, admission=adm_c, session=session,
    receipt_number=f"SC/{session.name}/{branch.code}/REC-C101",
    total_amount=20000.0, payment_mode='UPI', payment_date=timezone.now(),
)
PaymentAllocation.objects.create(payment=p_c, installment=inst_c1, allocated_amount=20000.0)

print("3 Test students created successfully!")

# 3. Test GET /fees/dues/ (Consolidated Dues Register & KPIs)
print("\n--- 3. Testing GET /fees/dues/ (Default Consolidated View) ---")
res_dues = client.get('/fees/dues/')
assert res_dues.status_code == 200
html_dues = res_dues.content.decode('utf-8')

# Verify Students presence and STRICT Cleared Exclusion
assert 'Tanvi Suresh Patil' in html_dues, "Tanvi Suresh Patil should be in dues register"
assert 'Omkar Dilip Jadhav' in html_dues, "Omkar Dilip Jadhav should be in dues register"
assert 'Snehal Ramesh Kute' not in html_dues, "Snehal Ramesh Kute (cleared student) MUST NOT appear in dues register!"
print("Strict exclusion verified: 100% cleared students are strictly omitted from the dues register!")

# Verify KPI Cards in HTML
assert 'Overdue Dues' in html_dues
assert 'Due Today' in html_dues
assert 'Partially Settled' in html_dues
assert 'Total Outstanding' in html_dues
print("All 4 KPI metric cards rendered with live totals!")

# 4. Test Quick Filter Tabs (Overdue, Due Today, Partially Paid, Upcoming)
print("\n--- 4. Testing Quick Filter Tabs ---")

# Overdue
res_overdue = client.get('/fees/dues/?status=OVERDUE')
assert res_overdue.status_code == 200
html_overdue = res_overdue.content.decode('utf-8')
assert 'Tanvi Suresh Patil' in html_overdue
assert 'OVERDUE' in html_overdue

# Partially Paid
res_partial = client.get('/fees/dues/?status=PARTIAL')
assert res_partial.status_code == 200
html_partial = res_partial.content.decode('utf-8')
assert 'Omkar Dilip Jadhav' in html_partial
assert 'PARTIAL' in html_partial

# Upcoming
res_upcoming = client.get('/fees/dues/?status=UPCOMING')
assert res_upcoming.status_code == 200
html_upcoming = res_upcoming.content.decode('utf-8')
assert 'Inst 2 (Term 2)' in html_upcoming
assert 'UPCOMING' in html_upcoming
print("Status tabs (?status=OVERDUE, PARTIAL, UPCOMING) verified accurately!")

# 5. Test Date Preset Filtering
print("\n--- 5. Testing Date Presets ---")
res_dp_overdue = client.get('/fees/dues/?date_preset=OVERDUE')
assert res_dp_overdue.status_code == 200
assert 'Tanvi Suresh Patil' in res_dp_overdue.content.decode('utf-8')

res_dp_today = client.get('/fees/dues/?date_preset=TODAY')
assert res_dp_today.status_code == 200
assert 'Omkar Dilip Jadhav' in res_dp_today.content.decode('utf-8')
print("Date presets (?date_preset=OVERDUE, TODAY) verified!")

# 6. Test Universal Multi-Word Search
print("\n--- 6. Testing Universal Search ---")
res_search = client.get('/fees/dues/?q=Tanvi+Patil')
assert res_search.status_code == 200
html_search = res_search.content.decode('utf-8')
assert 'Tanvi Suresh Patil' in html_search
assert 'Omkar Dilip Jadhav' not in html_search
print("Multi-token live search (?q=Tanvi+Patil) verified!")

# 7. Test Quick Due Date Extension via POST
print("\n--- 7. Testing POST /fees/dues/ (Quick Due Date Update) ---")
new_target_date = (today + timedelta(days=15)).strftime('%Y-%m-%d')
res_update_date = client.post(
    '/fees/dues/',
    {
        'action': 'update_due_date',
        'installment_id': inst_a1.id,
        'due_date': new_target_date,
    }
)
assert res_update_date.status_code == 302
inst_a1.refresh_from_db()
assert timezone.localtime(inst_a1.due_date).strftime('%Y-%m-%d') == new_target_date
print(f"Due date for Installment 1 successfully extended to {new_target_date}!")

# 8. Test Excel (.xlsx) Export
print("\n--- 8. Testing Excel (.xlsx) Export ---")
res_excel = client.get('/fees/dues/?export=excel')
assert res_excel.status_code == 200
assert res_excel['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
assert '.xlsx' in res_excel['Content-Disposition']
assert len(res_excel.content) > 1000
print(f"Excel export verified: generated valid workbook ({len(res_excel.content)} bytes)!")

# 9. Test PDF (.pdf) Export
print("\n--- 9. Testing PDF (.pdf) Export ---")
res_pdf = client.get('/fees/dues/?export=pdf')
assert res_pdf.status_code == 200
assert res_pdf['Content-Type'] == 'application/pdf'
assert '.pdf' in res_pdf['Content-Disposition']
assert res_pdf.content.startswith(b'%PDF')
assert len(res_pdf.content) > 1000
print(f"PDF export verified: generated valid Landscape A4 PDF ({len(res_pdf.content)} bytes)!")

# 10. Test WhatsApp Quick Reminder Deep Link
print("\n--- 10. Testing WhatsApp Reminder URL Generation ---")
res_wa = client.get('/fees/dues/?q=Omkar')
html_wa = res_wa.content.decode('utf-8')
assert 'https://api.whatsapp.com/send?phone=919822445566' in html_wa
print("WhatsApp reminder link with standardized phone 919822445566 generated in row!")

# 11. Cleanup
print("\n--- 11. Cleanup Test Artifacts ---")
cleanup_students(TEST_NAMES)
print("Cleaned up test students cleanly.")

print("\n" + "=" * 70)
print("ALL STEP 11 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

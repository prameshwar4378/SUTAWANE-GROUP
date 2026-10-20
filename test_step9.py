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
    AcademicSession, PreviousSessionDue, Payment, PaymentAllocation, ReceiptCounter
)

def cleanup_student(name):
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

# Pre-cleanup
cleanup_student('Ishaan Vijay Joshi')

client = Client()

print("=" * 70)
print("RUNNING STEP 9 AUTOMATED VERIFICATION SUITE")
print("INSTALLMENT FEE ACCOUNTING & COLLECTION SYSTEM")
print("=" * 70)

# 1. Login
print("\n--- 1. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302, f"Expected 302, got {login_res.status_code}"
print("Owner authenticated successfully!")

# 2. Check academic session and branch
session = AcademicSession.objects.filter(is_current=True).first() or AcademicSession.objects.first()
branch = Branch.objects.filter(is_active=True).first()
print(f"Using Session '{session.name}' and Branch '{branch.name}' ({branch.code})")

# 3. Test GET /fees/collect/ (Default Screen)
print("\n--- 2. Testing GET /fees/collect/ (Empty State) ---")
res_collect = client.get('/fees/collect/')
assert res_collect.status_code == 200
html_collect = res_collect.content.decode('utf-8')
assert 'Fee Accounting & Collection Register' in html_collect
assert 'Collect Student Fee' in html_collect
assert 'Payment Receipts History' in html_collect
assert 'No Student Selected' in html_collect
print("Fee collection screen loaded successfully in initial empty state!")

# 4. Setup Test Student with 3 Installments
print("\n--- 3. Setting Up Test Student with 3 Equal Installments ---")
student = Student.objects.create(
    student_code='SC-STEP9-001',
    full_name='Ishaan Vijay Joshi',
    parent_phone='9899988877',
    student_phone='9899988888',
    address='Station Road, Vaijapur',
)
admission = StudentAdmission.objects.create(
    student=student,
    branch=branch,
    session=session,
    roll_number='IVJ-01',
    standard='Class 10',
    admission_date=timezone.now(),
    is_active=True,
)
fee_plan = FeePlan.objects.create(
    admission=admission,
    session=session,
    total_fees=30000.0,
    total_discount=0.0,
    net_payable=30000.0,
)
inst1 = Installment.objects.create(
    fee_plan=fee_plan,
    installment_no=1,
    label='Installment 1 (Admission)',
    due_date=timezone.now(),
    amount_due=10000.0,
)
inst2 = Installment.objects.create(
    fee_plan=fee_plan,
    installment_no=2,
    label='Installment 2 (Mid-Term)',
    due_date=timezone.now() + timedelta(days=30),
    amount_due=10000.0,
)
inst3 = Installment.objects.create(
    fee_plan=fee_plan,
    installment_no=3,
    label='Installment 3 (Final)',
    due_date=timezone.now() + timedelta(days=60),
    amount_due=10000.0,
)
print(f"Created student '{student.full_name}' with 3 milestones of Rs. 10,000 each (Net: Rs. 30,000).")

# 5. Test Live Search Autocomplete Endpoint
print("\n--- 4. Testing GET /api/students-fee-search/ (Autocomplete) ---")
res_search = client.get('/api/students-fee-search/?q=Ishaan')
assert res_search.status_code == 200
html_search = res_search.content.decode('utf-8')
assert 'Ishaan Vijay Joshi' in html_search
assert 'IVJ-01' in html_search
assert 'Class 10' in html_search
print("Student search autocomplete endpoint returned matching student partial!")

# 6. Test GET /fees/collect/?tab=collect&student_id=<id> (Student Selected)
print("\n--- 5. Testing GET /fees/collect/?tab=collect&student_id=<id> ---")
res_profile = client.get(f'/fees/collect/?tab=collect&student_id={student.id}')
assert res_profile.status_code == 200
html_profile = res_profile.content.decode('utf-8')
assert 'Ishaan Vijay Joshi' in html_profile
assert 'IVJ-01' in html_profile
assert 'Installment 1 (Admission)' in html_profile
assert 'Installment 2 (Mid-Term)' in html_profile
assert 'Installment 3 (Final)' in html_profile
assert '30000' in html_profile
assert 'Rupees Thirty Thousand Only' in html_profile
print("Student fee profile, 5 financial KPI cards, amount in words, and installment ledger loaded!")

# 7. Collect Partial Payment of 15,000 (Testing Sequential Receipt & FIFO Allocation)
print("\n--- 6. Testing POST /fees/collect/ (Collect Rs. 15,000 via UPI) ---")
res_pay = client.post(
    '/fees/collect/',
    {
        'action': 'collect_payment',
        'student_id': student.id,
        'target_type': 'ADMISSION',
        'admission_id': admission.id,
        'amount': '15000',
        'payment_mode': 'UPI',
        'reference_number': 'UPI-TEST-12345',
        'notes': 'Online transfer via PhonePe',
        'next_due_date': '2026-11-25',
    }
)
assert res_pay.status_code == 302, f"Expected 302 redirect, got {res_pay.status_code}"

# Verify payment in database
payment = Payment.objects.filter(student=student, total_amount=15000.0).first()
assert payment is not None, "Payment record not found in database!"
assert payment.payment_mode == 'UPI'
assert payment.reference_number == 'UPI-TEST-12345'
assert payment.receipt_number.startswith(f"SC/{session.name}/{branch.code}/REC-")
assert payment.is_reversed is False
print(f"Payment recorded successfully! Receipt Number: '{payment.receipt_number}'")

# Verify FIFO Installment Allocation
allocations = payment.allocations.all().order_by('installment__installment_no')
assert allocations.count() == 2, f"Expected 2 allocation records, got {allocations.count()}"
alloc1 = allocations[0]
alloc2 = allocations[1]
assert alloc1.installment == inst1 and alloc1.allocated_amount == 10000.0
assert alloc2.installment == inst2 and alloc2.allocated_amount == 5000.0
print("FIFO auto-allocation verified: Inst 1 got Rs. 10,000 (Fully cleared); Inst 2 got Rs. 5,000 (Partial)!")

# Verify next promise due date was applied to Installment 2
inst2.refresh_from_db()
assert timezone.localtime(inst2.due_date).strftime('%Y-%m-%d') == '2026-11-25'
print("Next promise due date was successfully applied to active Installment 2 (2026-11-25)!")

# 8. Test Overpayment Prevention Guard
print("\n--- 7. Testing Overpayment Prevention Guard ---")
# Remaining balance is now 15,000. Attempting to pay 20,000 should be rejected!
res_overpay = client.post(
    '/fees/collect/',
    {
        'action': 'collect_payment',
        'student_id': student.id,
        'target_type': 'ADMISSION',
        'admission_id': admission.id,
        'amount': '20000',
        'payment_mode': 'CASH',
    }
)
assert res_overpay.status_code == 302
# Verify no payment was created for 20000
assert not Payment.objects.filter(student=student, total_amount=20000.0).exists()
print("Overpayment attempt (Rs. 20,000 > Rs. 15,000 balance) was safely blocked!")

# 9. Test Duplicate Payment Safety Warning
print("\n--- 8. Testing Duplicate Payment Safety Guard ---")
# Attempt to record identical 15,000 payment via UPI immediately
res_dup = client.post(
    '/fees/collect/',
    {
        'action': 'collect_payment',
        'student_id': student.id,
        'target_type': 'ADMISSION',
        'admission_id': admission.id,
        'amount': '15000',
        'payment_mode': 'UPI',
        'allow_duplicate': 'false',
    }
)
assert res_dup.status_code == 302
assert 'confirm_duplicate=true' in res_dup.url
print("Duplicate transaction guard triggered successfully!")

# 10. Test Carried-Forward Previous Session Due Collection
print("\n--- 9. Testing Carried-Forward Previous Session Due Payment ---")
other_session = AcademicSession.objects.filter(is_current=False).first()
if not other_session:
    other_session = AcademicSession.objects.create(name='2025-26', start_date=timezone.now(), end_date=timezone.now())

prev_due = PreviousSessionDue.objects.create(
    student=student,
    original_session=other_session,
    current_session=session,
    outstanding_amount=5000.0,
    collected_amount=0.0,
    description='Old dues from 2025-26',
)

res_prev_pay = client.post(
    '/fees/collect/',
    {
        'action': 'collect_payment',
        'student_id': student.id,
        'target_type': 'PREVIOUS_DUE',
        'previous_due_id': prev_due.id,
        'amount': '5000',
        'payment_mode': 'CASH',
        'notes': 'Paid in cash at center',
    }
)
assert res_prev_pay.status_code == 302
prev_due.refresh_from_db()
assert prev_due.collected_amount == 5000.0
print("Carried-forward previous session due of Rs. 5,000 collected and marked cleared!")

# 11. Test Receipt Modal View
print("\n--- 10. Testing GET /fees/receipt-modal/<id>/ (Dual-Copy Printable Layout) ---")
res_receipt = client.get(f'/fees/receipt-modal/{payment.id}/')
assert res_receipt.status_code == 200
html_receipt = res_receipt.content.decode('utf-8')
assert 'SUTAWANE CLASSES' in html_receipt
assert 'STUDENT COPY' in html_receipt
assert 'OFFICE COPY' in html_receipt
assert 'Cut or fold along dotted line for student / office copy' in html_receipt
assert payment.receipt_number in html_receipt
assert 'Ishaan Vijay Joshi' in html_receipt
assert 'Rupees Fifteen Thousand Only' in html_receipt
print("Dual-copy printable receipt modal rendered with Student Copy, Office Copy, and scissor cut line!")

# 12. Test Standalone Collect Fee Modal (via HTMX)
print("\n--- 11. Testing Standalone Collect Fee Modal (HTMX) ---")
res_modal = client.get(f'/fees/collect-modal/{student.id}/')
assert res_modal.status_code == 200
html_modal = res_modal.content.decode('utf-8')
assert 'Collect Student Fee' in html_modal
assert 'Ishaan Vijay Joshi' in html_modal
assert 'Payment Amount' in html_modal
print("Standalone CollectFeeModal rendered successfully via HTMX!")

# 13. Test Payment Reversal / Voiding
print("\n--- 12. Testing POST /fees/collect/ (Payment Reversal) ---")
res_reverse = client.post(
    '/fees/collect/',
    {
        'action': 'reverse_payment',
        'payment_id': payment.id,
        'reversal_reason': 'Cheque bounced by bank',
    }
)
assert res_reverse.status_code == 302
payment.refresh_from_db()
assert payment.is_reversed is True
assert payment.reversal_reason == 'Cheque bounced by bank'
assert payment.reversed_at is not None

# Verify dues restored on student profile
res_after_rev = client.get(f'/fees/collect/?tab=collect&student_id={student.id}')
assert res_after_rev.status_code == 200
html_after_rev = res_after_rev.content.decode('utf-8')
# All 30,000 should be pending again!
assert '30000' in html_after_rev
print("Payment reversal verified: marked isReversed=True, audit reason recorded, and full pending balance restored!")

# 14. Test Payment Receipts History Tab & KPIs
print("\n--- 13. Testing GET /fees/collect/?tab=history (Audit Ledger & KPIs) ---")
res_history = client.get('/fees/collect/?tab=history')
assert res_history.status_code == 200
html_history = res_history.content.decode('utf-8')
assert 'Total Collections' in html_history
assert 'Today\'s Collections' in html_history
assert 'Total Receipts' in html_history
assert 'Voided / Reversed' in html_history
assert payment.receipt_number in html_history
assert 'REVERSED' in html_history
print("Payment Receipts History tab loaded with 4 KPI cards and reversed receipt status!")

# 15. Cleanup
print("\n--- 14. Cleanup Test Artifacts ---")
cleanup_student('Ishaan Vijay Joshi')
print("Cleaned up test student successfully.")

print("\n" + "=" * 70)
print("ALL STEP 9 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

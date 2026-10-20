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
from MyApp.whatsapp import (
    format_whatsapp_number, generate_whatsapp_url,
    build_receipt_whatsapp_message, build_fee_reminder_whatsapp_message,
    build_admission_whatsapp_message, build_general_notice_whatsapp_message
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
cleanup_student('Pooja Ashok Shinde')

client = Client()

print("=" * 70)
print("RUNNING STEP 10 AUTOMATED VERIFICATION SUITE")
print("FEE RECEIPTS, DUAL-COPY PRINTING & WHATSAPP AUTOMATION")
print("=" * 70)

# 1. Test WhatsApp Phone Standardization Helper
print("\n--- 1. Testing WhatsApp Phone Number Standardization ---")
assert format_whatsapp_number('9822123456') == '919822123456', "Failed 10-digit format"
assert format_whatsapp_number('09822123456') == '919822123456', "Failed 11-digit leading zero format"
assert format_whatsapp_number('+91 98221 23456') == '919822123456', "Failed +91 spaced format"
assert format_whatsapp_number('919822123456') == '919822123456', "Failed 12-digit format"
print("WhatsApp phone formatting passed: correctly converts 10/11/12 digit inputs to '91XXXXXXXXXX'!")

# 2. Test WhatsApp Message Templates
print("\n--- 2. Testing WhatsApp Message Builders ---")

# A. Receipt Message
rcpt_msg = build_receipt_whatsapp_message(
    institute_name='Sutawane Classes',
    student_name='Pooja Shinde',
    student_code='SC-2026-999',
    roll_number='ROLL-45',
    standard='Class 10',
    receipt_number='SC/2026-27/NGP/REC-00099',
    total_amount=12000,
    payment_date='18 October 2026',
    payment_mode='UPI',
    reference_number='UPI-REF-887766',
    remaining_balance=8000,
    branch_name='Nagpur Main',
    helpline='+91 9822000000'
)
assert 'OFFICIAL FEE PAYMENT RECEIPT' in rcpt_msg
assert 'Pooja Shinde' in rcpt_msg
assert 'SC/2026-27/NGP/REC-00099' in rcpt_msg
assert '12,000' in rcpt_msg
assert 'UPI-REF-887766' in rcpt_msg
assert '8,000' in rcpt_msg
print("Receipt WhatsApp message builder passed with correct fee details and remaining balance!")

# B. Four-case Fee Reminder Message
# Case 1: Zero dues
rem_zero = build_fee_reminder_whatsapp_message(
    student_name='Pooja Shinde',
    current_pending_amount=0,
    previous_dues_pending=0
)
assert 'FEE CLEARED — APPRECIATION NOTE' in rem_zero
assert '100% CLEARED (NIL)' in rem_zero

# Case 2: Both current and prior dues pending
rem_both = build_fee_reminder_whatsapp_message(
    student_name='Pooja Shinde',
    current_pending_amount=5000,
    previous_dues_pending=3000,
    next_due_date='25 October 2026'
)
assert 'OFFICIAL FEE PAYMENT REMINDER' in rem_both
assert 'Current Session Pending: *Rs. 5,000*' in rem_both or '5,000' in rem_both
assert '3,000' in rem_both
assert '8,000' in rem_both

# Case 3: Current session pending only
rem_curr = build_fee_reminder_whatsapp_message(
    student_name='Pooja Shinde',
    current_pending_amount=6000,
    previous_dues_pending=0
)
assert 'Prior Session Dues: *Nil (Fully Cleared) ✅*' in rem_curr
assert '6,000' in rem_curr

# Case 4: Prior year dues only
rem_prior = build_fee_reminder_whatsapp_message(
    student_name='Pooja Shinde',
    current_pending_amount=0,
    previous_dues_pending=4000
)
assert 'Current Session: *Paid in Full (Nil) ✅*' in rem_prior
assert '4,000' in rem_prior

print("Intelligent 4-case Fee Reminder WhatsApp message builder passed 100%!")

# C. Admission & General Notice
adm_msg = build_admission_whatsapp_message(
    student_name='Pooja Shinde',
    roll_number='ROLL-45',
    standard='Class 10',
    total_fees=20000
)
assert 'CONGRATULATIONS & WELCOME!' in adm_msg
assert '20,000' in adm_msg

gen_msg = build_general_notice_whatsapp_message(
    student_name='Pooja Shinde',
    roll_number='ROLL-45',
    standard='Class 10'
)
assert 'Regarding student: *Pooja Shinde*' in gen_msg
print("Admission and General Notice WhatsApp builders verified!")

# D. WhatsApp Deep Link
wa_url = generate_whatsapp_url('9822123456', rcpt_msg)
assert wa_url.startswith('https://api.whatsapp.com/send?phone=919822123456&text=')
print(f"Generated universal WhatsApp deep link verified successfully!")

# 3. Authenticate User
print("\n--- 3. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
session = AcademicSession.objects.filter(is_current=True).first()
branch = Branch.objects.filter(is_active=True).first()
print(f"Owner authenticated! Active Session: '{session.name}', Branch: '{branch.name}'")

# 4. Setup Test Student with Fee Plan & Payment
print("\n--- 4. Setting Up Student and Payment Record ---")
student = Student.objects.create(
    student_code='SC-2026-9090',
    full_name='Pooja Ashok Shinde',
    parent_phone='9822556677',
    student_phone='9822556688',
    address='Gangapur Road, Vaijapur',
    date_of_birth='2010-04-12',
)

admission = StudentAdmission.objects.create(
    student=student,
    branch=branch,
    session=session,
    roll_number='PAS-10',
    standard='Class 10',
    admission_date=timezone.now(),
    is_active=True,
)

fee_plan = FeePlan.objects.create(
    admission=admission,
    session=session,
    total_fees=25000.0,
    total_discount=1000.0,
    net_payable=24000.0,
)

inst1 = Installment.objects.create(
    fee_plan=fee_plan,
    installment_no=1,
    label='Installment 1 (Term 1)',
    due_date=timezone.now(),
    amount_due=12000.0,
)
inst2 = Installment.objects.create(
    fee_plan=fee_plan,
    installment_no=2,
    label='Installment 2 (Term 2)',
    due_date=timezone.now() + timedelta(days=60),
    amount_due=12000.0,
)

# Record Payment of 12,000 via UPI
payment = Payment.objects.create(
    student=student,
    branch=branch,
    admission=admission,
    session=session,
    receipt_number=f"SC/{session.name}/{branch.code}/REC-88888",
    total_amount=12000.0,
    payment_mode='UPI',
    reference_number='UPI-PAY-STEP10',
    notes='Installment 1 paid via GPay',
    payment_date=timezone.now(),
    is_reversed=False,
)

PaymentAllocation.objects.create(
    payment=payment,
    installment=inst1,
    allocated_amount=12000.0,
)
print(f"Test payment recorded: Receipt #{payment.receipt_number} for Rs. 12,000.")

# 5. Test Receipt Modal View
print("\n--- 5. Testing GET /fees/receipt-modal/<payment_id>/ ---")
res_modal = client.get(f'/fees/receipt-modal/{payment.id}/')
assert res_modal.status_code == 200
html_modal = res_modal.content.decode('utf-8')
assert 'SUTAWANE CLASSES' in html_modal
assert 'STUDENT COPY' in html_modal
assert 'OFFICE COPY' in html_modal
assert 'Cut or fold along dotted line for student / office copy' in html_modal
assert payment.receipt_number in html_modal
assert 'Pooja Ashok Shinde' in html_modal
assert 'Rupees Twelve Thousand Only' in html_modal
assert 'UPI-PAY-STEP10' in html_modal
assert 'btn-mode-thermal' in html_modal
assert 'thermal-preview-container' in html_modal
assert 'https://api.whatsapp.com/send?phone=919822556677' in html_modal
print("Receipt modal rendered with A4 dual-copy, scissor cut line, thermal preview, and WhatsApp direct trigger!")

# 6. Test Dedicated Standalone Print View (A4 Dual-Copy, Student Copy, Office Copy, 80mm Thermal)
print("\n--- 6. Testing GET /fees/receipts/<payment_id>/print/ ---")

# Default: A4 Dual
res_print_dual = client.get(f'/fees/receipts/{payment.id}/print/?format=a4_dual')
assert res_print_dual.status_code == 200
html_dual = res_print_dual.content.decode('utf-8')
assert 'STUDENT COPY' in html_dual
assert 'OFFICE COPY' in html_dual
assert 'Cut or fold along dotted line for student / office copy' in html_dual
assert 'printing-receipt' in html_dual
print("Dedicated print sheet loaded in A4 Dual-Copy mode!")

# Student Slip Only
res_print_student = client.get(f'/fees/receipts/{payment.id}/print/?format=student_only')
assert res_print_student.status_code == 200
html_student = res_print_student.content.decode('utf-8')
assert 'STUDENT COPY' in html_student
assert 'OFFICE COPY' not in html_student
print("Dedicated print sheet loaded in Student Slip Only mode!")

# Office Slip Only
res_print_office = client.get(f'/fees/receipts/{payment.id}/print/?format=office_only')
assert res_print_office.status_code == 200
html_office = res_print_office.content.decode('utf-8')
assert 'OFFICE COPY' in html_office
assert 'STUDENT COPY' not in html_office
print("Dedicated print sheet loaded in Office Slip Only mode!")

# 80mm Thermal Mode
res_print_thermal = client.get(f'/fees/receipts/{payment.id}/print/?format=thermal')
assert res_print_thermal.status_code == 200
html_thermal = res_print_thermal.content.decode('utf-8')
assert 'printable-thermal-receipt' in html_thermal
assert 'printing-thermal' in html_thermal
assert 'TOTAL PAID:' in html_thermal
assert '12000' in html_thermal
print("Dedicated print sheet loaded in 80mm Thermal POS printer mode!")

# Autoprint flag check
res_autoprint = client.get(f'/fees/receipts/{payment.id}/print/?autoprint=1')
assert res_autoprint.status_code == 200
assert 'window.print()' in res_autoprint.content.decode('utf-8')
print("Autoprint flag (?autoprint=1) invokes browser print automatically!")

# 7. Test Receipt Voiding / Reversal Workflow
print("\n--- 7. Testing POST /fees/receipts/<payment_id>/void/ ---")
res_void = client.post(
    f'/fees/receipts/{payment.id}/void/',
    {'reversal_reason': 'Entered by mistake in wrong student account'}
)
assert res_void.status_code == 302

payment.refresh_from_db()
assert payment.is_reversed is True
assert payment.reversal_reason == 'Entered by mistake in wrong student account'
assert payment.reversed_at is not None
print("Payment marked is_reversed=True and reversal reason logged successfully!")

# Verify VOIDED Banner is rendered in modal and print view
res_modal_rev = client.get(f'/fees/receipt-modal/{payment.id}/')
html_modal_rev = res_modal_rev.content.decode('utf-8')
assert '⚠️ THIS RECEIPT HAS BEEN VOIDED / REVERSED' in html_modal_rev
assert 'Entered by mistake in wrong student account' in html_modal_rev
assert 'REVERSED' in html_modal_rev

res_print_rev = client.get(f'/fees/receipts/{payment.id}/print/?format=thermal')
html_print_rev = res_print_rev.content.decode('utf-8')
assert '*** VOIDED / REVERSED ***' in html_print_rev
assert 'Entered by mistake in wrong student account' in html_print_rev
print("Prominent VOIDED / REVERSED watermark and reason verified in modal and thermal layouts!")

# 8. Cleanup
print("\n--- 8. Cleanup Test Artifacts ---")
cleanup_student('Pooja Ashok Shinde')
print("Cleaned up test records cleanly.")

print("\n" + "=" * 70)
print("ALL STEP 10 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

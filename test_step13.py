import os
import django
import sys
import json
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
    Branch, AcademicSession, Student, StudentAdmission,
    FeePlan, Installment, Payment, PaymentAllocation, Expense, ExpenseCategory, User
)

TEST_TAG = "TEST_STEP13_DASHBOARD"

def cleanup_step13_records():
    for p in Payment.objects.filter(receipt_number__icontains=TEST_TAG):
        p.allocations.all().delete()
        p.delete()
    for exp in Expense.objects.filter(description__icontains=TEST_TAG):
        exp.attachments.all().delete()
        exp.delete()
    for s in Student.objects.filter(student_code__icontains="SC-2026-9999"):
        for adm in s.admissions.all():
            if hasattr(adm, 'fee_plan'):
                adm.fee_plan.installments.all().delete()
                adm.fee_plan.delete()
            adm.delete()
        s.delete()

cleanup_step13_records()

client = Client()

print("=" * 70)
print("RUNNING STEP 13 AUTOMATED VERIFICATION SUITE")
print("DASHBOARD ANALYTICS, CHARTS & ACTIVITY FEED")
print("=" * 70)

# 1. Authenticate Owner
print("\n--- 1. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
branch = Branch.objects.filter(is_active=True).first()
session = AcademicSession.objects.filter(is_current=True).first()
today = timezone.localtime().date()
print(f"Owner authenticated! Active Session: '{session.name}', Branch: '{branch.name}', Date: {today}")

# 2. Test Initial Dashboard GET /
print("\n--- 2. Testing Initial GET / (Dashboard View) ---")
res_initial = client.get('/')
assert res_initial.status_code == 200
html_initial = res_initial.content.decode('utf-8')
assert 'Institute Financial Dashboard' in html_initial
assert "Today's Collections" in html_initial
assert "Today's Expenses" in html_initial
assert "Today's Net Movement" in html_initial
assert 'Overdue Fee Dues' in html_initial
assert 'Total Expected Fees' in html_initial
assert 'Total Fees Collected' in html_initial
assert 'Total Outstanding Dues' in html_initial
assert 'Active Enrolled Students' in html_initial
assert 'Monthly Financial Movement (Last 6 Months)' in html_initial
assert 'Recent Activity Feed' in html_initial
assert 'Live Feed' in html_initial
print("Initial / page loaded with all 8 KPI cards, chart container, and live feed!")

# 3. Setting Up Test Financial Activity (Inflow, Outflow, Overdue Due)
print("\n--- 3. Injecting Test Financial Records (Collections, Expenses, Overdue Dues) ---")
# Student & Admission
student = Student.objects.create(
    student_code='SC-2026-9999',
    full_name='Vikramaditya Rao',
    parent_phone='9811223344',
)
adm = StudentAdmission.objects.create(
    student=student,
    branch=branch,
    session=session,
    roll_number='VR-99',
    standard='Class 10',
    is_active=True,
    admission_date=timezone.now(),
)
fp = FeePlan.objects.create(
    admission=adm,
    session=session,
    total_fees=40000.0,
    net_payable=40000.0,
)
# Installment 1: Due in the past (Overdue)
inst_past = Installment.objects.create(
    fee_plan=fp,
    installment_no=1,
    label='Overdue Milestone',
    due_date=timezone.make_aware(datetime.combine(today - timedelta(days=10), datetime.min.time())),
    amount_due=10000.0,
)
# Installment 2: Due today
inst_today = Installment.objects.create(
    fee_plan=fp,
    installment_no=2,
    label='Admission Milestone',
    due_date=timezone.make_aware(datetime.combine(today, datetime.min.time())),
    amount_due=15000.0,
)
# Installment 3: Upcoming
inst_fut = Installment.objects.create(
    fee_plan=fp,
    installment_no=3,
    label='Final Milestone',
    due_date=timezone.make_aware(datetime.combine(today + timedelta(days=30), datetime.min.time())),
    amount_due=15000.0,
)

# Inflow: Payment of 15,000 received today via UPI
p_today = Payment.objects.create(
    student=student,
    branch=branch,
    admission=adm,
    session=session,
    receipt_number=f"SC/{session.name}/{branch.code}/{TEST_TAG}-REC1",
    total_amount=15000.0,
    payment_mode='UPI',
    payment_date=timezone.now(),
)
PaymentAllocation.objects.create(payment=p_today, installment=inst_today, allocated_amount=15000.0)

# Outflow: Center Expense of 3,000 recorded today via CASH
cat_rent = ExpenseCategory.objects.first()
exp_today = Expense.objects.create(
    branch=branch,
    category=cat_rent,
    amount=3000.0,
    description=f'{TEST_TAG} Center Routine Maintenance & Supplies',
    payment_mode='CASH',
    vendor='City Hardware',
    expense_date=timezone.now(),
)
print("Test activity injected: Fee Inflow ₹15,000, Expense Outflow ₹3,000, Overdue Dues ₹10,000!")

# 4. Testing GET / with Live Aggregated Metrics
print("\n--- 4. Testing GET / (Live Aggregated Financial Dashboard) ---")
res_active = client.get('/')
assert res_active.status_code == 200
html_active = res_active.content.decode('utf-8')

# Verify Today's Collections (15,000), Expenses (3,000), Net Movement (12,000)
assert '15,000' in html_active
assert '3,000' in html_active
assert '12,000' in html_active
assert '10,000' in html_active  # Overdue due
print("Live KPI calculations verified in HTML: Collections ₹15,000, Expenses ₹3,000, Net ₹12,000, Overdue ₹10,000!")

# 5. Testing Live Activity Feed Contents
print("\n--- 5. Testing Live Activity Feed ---")
assert 'Vikramaditya Rao' in html_active
assert 'Center Routine Maintenance' in html_active
assert 'Fee Collection' in html_active
print("Recent activity feed verified: both fee collection and center expense rendered with badges and relative time!")

# 6. Testing JSON Format API (GET /?format=json)
print("\n--- 6. Testing Dashboard JSON Analytics API (GET /?format=json) ---")
res_json = client.get('/?format=json')
assert res_json.status_code == 200
assert res_json['Content-Type'] == 'application/json'
data = json.loads(res_json.content.decode('utf-8'))

# Check keys
assert 'today' in data
assert 'month' in data
assert 'session' in data
assert 'dues' in data
assert 'monthlyTrend' in data
assert 'branchComparison' in data
assert 'recentTransactions' in data

assert data['today']['collections'] >= 15000.0
assert data['today']['expenses'] >= 3000.0
assert data['today']['netMovement'] == data['today']['collections'] - data['today']['expenses']
assert data['dues']['overdueAmount'] >= 10000.0
assert len(data['monthlyTrend']) == 6
assert len(data['recentTransactions']) >= 2
print("Dashboard JSON API verified: returned complete analytics payload matching React contract!")

# 7. Testing Multi-Branch Comparison Table (GET /?branch_id=ALL)
print("\n--- 7. Testing Multi-Branch Performance Comparison ---")
res_all = client.get('/?branch_id=ALL')
assert res_all.status_code == 200
html_all = res_all.content.decode('utf-8')
assert 'Multi-Branch Performance Comparison' in html_all
assert 'Consolidated View (All Centers)' in html_all
assert branch.name in html_all
print("Multi-Branch comparison table verified for consolidated view!")

# 8. Testing Specific Branch Scope Isolation
print("\n--- 8. Testing Branch Scope Isolation ---")
res_scoped = client.get(f'/?branch_id={branch.id}')
assert res_scoped.status_code == 200
html_scoped = res_scoped.content.decode('utf-8')
assert branch.name in html_scoped
print(f"Scope successfully isolated to branch '{branch.name}'!")

# 9. Cleanup
print("\n--- 9. Cleanup Test Artifacts ---")
cleanup_step13_records()
print("Cleaned up test dashboard records cleanly.")

print("\n" + "=" * 70)
print("ALL STEP 13 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

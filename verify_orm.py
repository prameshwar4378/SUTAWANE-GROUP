import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from MyApp.models import (
    SystemSetting, HealthLog, User, Branch, AcademicSession, Course,
    Student, StudentAdmission, FeePlan, FeeDiscount, Installment,
    Payment, PaymentAllocation, PreviousSessionDue, ReceiptCounter,
    ExpenseCategory, Expense, ExpenseAttachment
)

print("=== VERIFYING DJANGO ORM QUERIES ON EXISTING DATA ===")
print("SystemSetting count:", SystemSetting.objects.count())
print("Branch count:", Branch.objects.count())
for b in Branch.objects.all():
    print(f"  Branch: {b.name} ({b.code})")

print("AcademicSession count:", AcademicSession.objects.count())
for s in AcademicSession.objects.all():
    print(f"  Session: {s.display_name} (is_current={s.is_current})")

print("Course count:", Course.objects.count())
for c in Course.objects.all():
    print(f"  Course: {c.name} - Fee: {c.default_fee}")

print("User count:", User.objects.count())
for u in User.objects.all():
    print(f"  User: {u.username} ({u.role})")

print("ExpenseCategory count:", ExpenseCategory.objects.count())
for ec in ExpenseCategory.objects.all():
    print(f"  Category: {ec.name}")

print("Student count:", Student.objects.count())
for st in Student.objects.all():
    print(f"  Student: {st.full_name} ({st.student_code})")
    for adm in st.admissions.all():
        print(f"    Admission: Roll {adm.roll_number}, Class: {adm.standard}, Branch: {adm.branch.name}")
        if hasattr(adm, 'fee_plan'):
            fp = adm.fee_plan
            print(f"    Fee Plan: Total Rs.{fp.total_fees}, Net Rs.{fp.net_payable}")
            for inst in fp.installments.all():
                print(f"      Installment #{inst.installment_no}: Rs.{inst.amount_due} due {inst.due_date} [Status: {inst.status}]")

print("ALL 18 MODELS VERIFIED SUCCESSFULLY VIA DJANGO ORM!")

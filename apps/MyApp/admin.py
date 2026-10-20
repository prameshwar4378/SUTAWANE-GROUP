from django.contrib import admin
from .models import (
    SystemSetting, HealthLog, User, Branch, AcademicSession, Course,
    Student, StudentAdmission, FeePlan, FeeDiscount, Installment,
    PreviousSessionDue, Payment, PaymentAllocation, ReceiptCounter,
    ExpenseCategory, Expense, ExpenseAttachment
)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'updated_at')
    search_fields = ('key', 'value')


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'name')


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'phone', 'contact_person', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_name', 'start_date', 'end_date', 'is_current', 'isActive')
    list_filter = ('is_current', 'isActive')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'default_fee', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


class StudentAdmissionInline(admin.TabularInline):
    model = StudentAdmission
    extra = 0


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_code', 'full_name', 'parent_phone', 'created_at')
    search_fields = ('student_code', 'full_name', 'parent_phone')
    inlines = [StudentAdmissionInline]


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0


class FeeDiscountInline(admin.TabularInline):
    model = FeeDiscount
    extra = 0


@admin.register(FeePlan)
class FeePlanAdmin(admin.ModelAdmin):
    list_display = ('admission', 'total_fees', 'total_discount', 'net_payable', 'session')
    inlines = [InstallmentInline, FeeDiscountInline]


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student', 'total_amount', 'payment_mode', 'payment_date', 'is_reversed')
    list_filter = ('payment_mode', 'is_reversed', 'branch', 'session')
    search_fields = ('receipt_number', 'student__full_name', 'reference_number')
    inlines = [PaymentAllocationInline]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active')


class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 0


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('expense_date', 'category', 'amount', 'branch', 'payment_mode', 'vendor')
    list_filter = ('category', 'branch', 'payment_mode')
    search_fields = ('description', 'vendor', 'reference_number')
    inlines = [ExpenseAttachmentInline]


admin.site.register(HealthLog)
admin.site.register(PreviousSessionDue)
admin.site.register(ReceiptCounter)
admin.site.register(StudentAdmission)
admin.site.register(Installment)
admin.site.register(PaymentAllocation)
admin.site.register(FeeDiscount)
admin.site.register(ExpenseAttachment)

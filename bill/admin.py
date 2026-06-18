from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *



@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'branch', 'is_active', 'is_approved')
    list_filter = ('role', 'is_active', 'is_approved', 'branch')
    search_fields = ('username', 'email', 'phone')
    fieldsets = UserAdmin.fieldsets + (
        ('Vetri RMS User Details', {'fields': ('role', 'branch', 'phone', 'is_approved')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Vetri RMS User Details', {'fields': ('role', 'branch', 'phone', 'is_approved')}),
    )



@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'address')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'gstin')
    search_fields = ('name', 'contact_person', 'phone')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'selling_price', 'status')
    list_filter = ('status', 'category')
    search_fields = ('name',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'total_purchases', 'last_purchase_date')
    search_fields = ('name', 'phone')

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'unit_price', 'line_total')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'grand_total', 'payment_mode', 'status', 'created_at')
    list_filter = ('status', 'payment_mode', 'created_at')
    search_fields = ('invoice_number', 'customer__name', 'customer__phone')
    readonly_fields = ('invoice_id', 'invoice_number')
    inlines = [InvoiceItemInline]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'branch', 'entry_type', 'category', 'amount')
    list_filter = ('entry_type', 'branch', 'date')
    search_fields = ('category', 'description')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'validity_days', 'max_cashiers', 'is_active']
    list_editable = ['is_active']


@admin.register(BranchSubscription)
class BranchSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['branch', 'plan', 'status', 'start_date', 'end_date', 'days_remaining']
    list_filter = ['status']
    readonly_fields = ['razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature']


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
import uuid

# ==========================================
# 0. CUSTOM USER MANAGER
# ==========================================
class CustomUserManager(BaseUserManager):
    """
    Custom manager to ensure that terminal-created superusers 
    automatically receive the 'admin' role required by the BRD.
    """
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        # FORCE THE ROLE TO ADMIN FOR ALL SUPERUSERS
        extra_fields.setdefault('role', 'admin') 

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)



class Branch(models.Model):
    name = models.CharField(max_length=255)
    shop_type=models.CharField(max_length=255,blank=True, null=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    pan_number = models.CharField(max_length=50, blank=True, null=True)
    owner_name=models.CharField(max_length=255,blank=True, null=True)
    phonenumber= models.CharField(max_length=20, blank=True, null=True)
    street_address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    invoice_prefix=models.CharField(max_length=20, blank=True, null=True)
    opening_date = models.DateField(blank=True, null=True)
    logo=models.ImageField(upload_to='branch_logos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def address(self):
        """Helper to combine address fields for the frontend card view"""
        parts = [self.street_address, self.city, self.state, self.pincode]
        return ", ".join([str(p) for p in parts if p])

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Super Admin'),
        ('manager', 'Branch Manager'),
        ('inventory', 'Inventory Manager'),
        ('cashier', 'Cashier'),
    )
    
    full_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    branch = models.ForeignKey('Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff')
    phone = models.CharField(max_length=15, blank=True)
    is_approved = models.BooleanField(default=False) 
    position_request = models.CharField(max_length=255, blank=True, null=True) 
    request_description = models.TextField(blank=True, null=True)
    objects = CustomUserManager()

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name="vetri_user_groups", 
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name="vetri_user_permissions",
        related_query_name="user",
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


# ==========================================
# 2. PRODUCT CATALOG & INVENTORY SUPPLY
# ==========================================
class Category(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.name

# Update your Product model in models.py
class Product(models.Model):
    STATUS_CHOICES = (('Active', 'Active'), ('Archived', 'Archived'))
    product_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    unit = models.CharField(max_length=20, default='Unit')
    stock_quantity = models.IntegerField(default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    expiry_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    def __str__(self):
        return self.name



class Customer(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, null=True)
    total_purchases = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    last_purchase_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name

class Invoice(models.Model):
    PAYMENT_CHOICES = (('Cash', 'Cash'), ('Card', 'Card'), ('UPI', 'UPI'), ('Wallet', 'Wallet'), ('Split', 'Split'))
    STATUS_CHOICES = (('Paid', 'Paid'), ('Pending', 'Pending'), ('Overdue', 'Overdue'))

    invoice_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='Cash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Paid')
    created_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Fetch the first branch to get the custom prefix
            branch = Branch.objects.first()
            prefix = branch.invoice_prefix if branch and branch.invoice_prefix else "INV"
            
            current_year = timezone.now().strftime('%Y')
            random_slug = uuid.uuid4().hex[:5].upper()
            self.invoice_number = f"{prefix}-{current_year}-{random_slug}"
            
        super().save(*args, **kwargs)

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)


# ==========================================
# 5. GENERAL LEDGER ACCOUNTING
# ==========================================
class LedgerEntry(models.Model):
    ENTRY_TYPES = (('Income', 'Income'), ('Expense', 'Expense'))
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True)  
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    category = models.CharField(max_length=100)
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)



class Coupon(models.Model):
    DISCOUNT_CHOICES = (('Flat', 'Flat'), ('Percentage', 'Percentage'))
    
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_CHOICES, default='Flat')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code
    

class Plan(models.Model):
    name = models.CharField(max_length=100)      
    price = models.DecimalField(max_digits=10, decimal_places=2)
    validity_days = models.IntegerField()            
    max_cashiers = models.IntegerField(default=1)
    features = models.TextField(blank=True)          
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - ₹{self.price}/{self.validity_days}d"


class BranchSubscription(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
    )
    branch = models.OneToOneField(Branch, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def is_active(self):
        return self.status == 'active' and self.end_date > timezone.now()
    
    @property
    def days_remaining(self):
        if self.end_date > timezone.now():
            return (self.end_date - timezone.now()).days
        return 0

    def __str__(self):
        return f"{self.branch.name} → {self.plan.name} (expires {self.end_date.date()})"
    


class SiteSettings(models.Model):
    login_logo = models.ImageField(upload_to='site/', blank=True, null=True)
    login_bg_color = models.CharField(max_length=20, default='#2B2B2B')
    login_bg_image = models.ImageField(upload_to='site/', blank=True, null=True)  # <-- add this
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return 'Site Settings'

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
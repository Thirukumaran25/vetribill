from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.db.models import Sum, Count
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import re
import json
import uuid
import razorpay
import hmac, hashlib
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import *

# ==========================================
# 0. HELPER: FIXED TO USE THE USER'S BRANCH
# ==========================================
def get_store_profile(user=None):
    """Fetches the branch specific to the logged-in user with strict fallbacks."""
    if user and user.is_authenticated and hasattr(user, 'branch') and user.branch:
        return user.branch
        
    # Fallback only if the user has no branch assigned
    store = Branch.objects.first()
    if not store:
        store = Branch.objects.create(
            name="My Shop", 
            shop_type="Retail Store", 
            street_address="Not Set", 
            city="Not Set", 
            state="Not Set", 
            pincode="000000"
        )
    return store


# ==========================================
# 1. AUTHENTICATION & LOGIN LOGIC
# ==========================================
def login_view(request):
    """Handles user authentication with strict Role Validation."""
    if request.user.is_authenticated:
        store = get_store_profile(request.user)
        try:
            sub = store.subscription
            if not sub.is_active:
                return redirect('plans_page')
        except:
            if request.user.role == 'admin':
                return redirect('plans_page')
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        requested_role = request.POST.get('role')

        user = authenticate(request, username=email, password=password)

        if user is not None:
            if user.role != requested_role:
                error_msg = f"Access Denied: Your account does not have {requested_role.title()} privileges."
                return render(request, 'auth/login.html', {'error': error_msg})

            login(request, user)

            store = get_store_profile(request.user)
            try:
                sub = store.subscription
                if not sub.is_active:
                    if user.role == 'admin':
                        return redirect('plans_page')
                    else:
                        logout(request)
                        return render(request, 'auth/login.html', {
                            'error': 'Access restricted. The shop subscription has expired. Please contact your admin.'
                        })
            except:
                if user.role == 'admin':
                    return redirect('plans_page')
                else:
                    logout(request)
                    return render(request, 'auth/login.html', {
                        'error': 'Access restricted. No active subscription found. Please contact your admin.'
                    })

            return redirect('dashboard')

        else:
            return render(request, 'auth/login.html', {'error': 'Invalid username or password.'})

    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ==========================================
# PROFILE
# ==========================================

@login_required
def profile_view(request):
    store = get_store_profile(request.user)
    
    try:
        current_sub = store.subscription
    except Exception:
        current_sub = None

    if request.method == 'POST':
        if 'logo' in request.FILES:
            store.logo = request.FILES['logo']

        request.user.email = request.POST.get('email', request.user.email)
        request.user.phone = request.POST.get('alt_phone', request.user.phone) 
        request.user.save()

        store.name = request.POST.get('shop_name', store.name)
        store.shop_type = request.POST.get('business_type', store.shop_type)
        store.owner_name = request.POST.get('owner_name', store.owner_name)
        store.phonenumber = request.POST.get('phone', store.phonenumber)
        store.street_address = request.POST.get('street_address', store.street_address)
        store.city = request.POST.get('city', store.city)
        store.state = request.POST.get('state', store.state)
        store.pincode = request.POST.get('pincode', store.pincode)
        store.gst_number = request.POST.get('gst_number', store.gst_number)
        store.pan_number = request.POST.get('pan_number', store.pan_number)
        store.save()

        messages.success(request, "Shop profile updated successfully.")
        return redirect('profile')

    plan_features = []
    if current_sub and current_sub.plan and current_sub.plan.features:
        plan_features = [f.strip() for f in current_sub.plan.features.split(',') if f.strip()]

    context = {
        'branch': store,
        'branch_context': store,          # ✅ for base.html nav
        'user': request.user,
        'current_sub': current_sub,
        'plan_features': plan_features,
    }
    return render(request, 'pages/profile.html', context)


# ==========================================
# DASHBOARD
# ==========================================

@login_required
def dynamic_dashboard_view(request):
    user = request.user
    today = timezone.now().date()
    store = get_store_profile(user)
    
    context = {'role': user.role, 'user': user, 'branch_context': store}  # ✅ already here

    if user.role == 'admin':
        today_invoices = Invoice.objects.filter(branch=store, created_at__date=today, status='Paid')
        pending_invs = Invoice.objects.filter(branch=store, status='Pending')
        
        context['today_sales'] = today_invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        context['pending_payments_amount'] = pending_invs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        context['pending_payments_count'] = pending_invs.count()
        context['total_products_count'] = Product.objects.filter(branch=store).count()
        context['total_categories_count'] = Category.objects.filter(branch=store).count()

        chart_labels = []
        chart_sales = []
        chart_revenue = []
        
        for i in range(6, -1, -1):
            target_date = today - timedelta(days=i)
            chart_labels.append(target_date.strftime('%a'))
            day_invs = Invoice.objects.filter(branch=store, created_at__date=target_date, status='Paid')
            sales_val = day_invs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
            rev_val = day_invs.aggregate(Sum('subtotal'))['subtotal__sum'] or 0
            chart_sales.append(float(sales_val))
            chart_revenue.append(float(rev_val))

        context['chart_labels'] = json.dumps(chart_labels)
        context['chart_sales'] = json.dumps(chart_sales)
        context['chart_revenue'] = json.dumps(chart_revenue)

        low_stock_threshold = 10
        context['low_stock_products'] = Product.objects.filter(branch=store, stock_quantity__lte=low_stock_threshold)
        context['recent_activities'] = Invoice.objects.filter(branch=store).order_by('-created_at').select_related('cashier', 'customer')[:5]

        return render(request, 'pages/admin_portal.html', context)

    elif user.role == 'cashier':
        yesterday = today - timedelta(days=1)
        today_invoices = Invoice.objects.filter(branch=store, created_at__date=today)
        yesterday_invoices = Invoice.objects.filter(branch=store, created_at__date=yesterday, status='Paid')

        today_sales = today_invoices.filter(status='Paid').aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        yesterday_sales = yesterday_invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        
        if yesterday_sales > 0:
            sales_diff_pct = ((float(today_sales) - float(yesterday_sales)) / float(yesterday_sales)) * 100
        else:
            sales_diff_pct = 100 if today_sales > 0 else 0

        bills_today = today_invoices.count()
        pending_bills = today_invoices.filter(status__in=['Pending', 'Overdue']).count()

        cash_sales = today_invoices.filter(status='Paid', payment_mode='Cash').aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        upi_card_sales = today_invoices.filter(status='Paid', payment_mode__in=['UPI', 'Card']).aggregate(Sum('grand_total'))['grand_total__sum'] or 0

        cash_sales_pct = (float(cash_sales) / float(today_sales) * 100) if today_sales > 0 else 0
        upi_card_sales_pct = (float(upi_card_sales) / float(today_sales) * 100) if today_sales > 0 else 0

        context.update({
            'today_sales': today_sales,
            'sales_diff_pct': sales_diff_pct,
            'bills_today': bills_today,
            'pending_bills': pending_bills,
            'cash_sales': cash_sales,
            'cash_sales_pct': cash_sales_pct,
            'upi_card_sales': upi_card_sales,
            'upi_card_sales_pct': upi_card_sales_pct,
            'recent_activities': today_invoices.order_by('-created_at')[:10],
        })
        
        return render(request, 'pages/cashier_portal.html', context)

    return redirect('login')


# ==========================================
# POS TRANSACTION API
# ==========================================

@login_required
@transaction.atomic
def pos_invoice_transaction_api(request):
    if request.method != 'POST' or request.user.role not in ['cashier', 'admin']:
        return JsonResponse({'error': 'Unauthorized access to POS systems.'}, status=403)
        
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Cart is empty. Cannot process transaction.'}, status=400)

        store = get_store_profile(request.user)
        subtotal_dec = Decimal(str(data.get('subtotal', 0)))
        discount_dec = Decimal(str(data.get('discount', 0)))
        tax_dec = Decimal(str(data.get('tax', 0)))
        grand_total_dec = Decimal(str(data.get('grand_total', 0)))

        customer_inst = None
        if data.get('customer_phone'):
            customer_inst, _ = Customer.objects.get_or_create(
                phone=data.get('customer_phone'),
                branch=store,
                defaults={'name': data.get('customer_name', 'Walk-in')}
            )

        invoice = Invoice.objects.create(
            branch=store,
            cashier=request.user,
            customer=customer_inst,
            subtotal=subtotal_dec,
            discount_amount=discount_dec,
            tax_amount=tax_dec,
            grand_total=grand_total_dec,
            payment_mode=data.get('payment_mode', 'Cash'),
            status='Paid'
        )

        for single_item in items:
            product_obj = get_object_or_404(Product, id=single_item['product_id'], branch=store)
            order_qty = int(single_item['quantity'])
            
            if product_obj.stock_quantity < order_qty:
                raise ValueError(f"Cannot process bill: {product_obj.name} only has {product_obj.stock_quantity} left in stock.")
            
            product_obj.stock_quantity -= order_qty
            product_obj.save()
            
            InvoiceItem.objects.create(
                invoice=invoice,
                product=product_obj,
                quantity=order_qty,
                unit_price=product_obj.selling_price,
                line_total=Decimal(order_qty) * product_obj.selling_price
            )

        if customer_inst:
            customer_inst.total_purchases = Decimal(str(customer_inst.total_purchases)) + grand_total_dec
            customer_inst.last_purchase_date = timezone.now()
            customer_inst.save()

        LedgerEntry.objects.create(
            branch=store,
            entry_type='Income',
            category='Sales',
            description=f"Sales POS {invoice.invoice_number}",
            amount=grand_total_dec,
            created_by=request.user
        )

        return JsonResponse({'success': True, 'invoice_number': invoice.invoice_number, 'payable': float(grand_total_dec)})
        
    except Exception as err:
        transaction.set_rollback(True)
        return JsonResponse({'error': str(err)}, status=400)


# ==========================================
# BILLING POS
# ==========================================

@login_required
def billing_pos(request):
    if request.user.role not in ['admin', 'cashier']:
        return redirect('dashboard')
    
    store = get_store_profile(request.user)
    active_products = Product.objects.filter(branch=store, status='Active')
    prefix = store.invoice_prefix if store.invoice_prefix else "INV"
    active_coupons = Coupon.objects.filter(branch=store, is_active=True)
    
    catalog = []
    for item in active_products:
        catalog.append({
            'id': item.id,
            'name': item.name,
            'price': float(item.selling_price),
            'stock': item.stock_quantity,
            'barcode': item.barcode or '',
        })
        
    context = {
        'catalog_json': json.dumps(catalog),
        'branch': store,
        'branch_context': store,          # ✅ ADDED
        'coupons': active_coupons,
        'branch_name': store.name,
        'next_invoice_id': f"{prefix}-{timezone.now().strftime('%Y')}-{uuid.uuid4().hex[:5].upper()}"
    }
    
    return render(request, 'pages/billing_pos.html', context)


# ==========================================
# INVENTORY
# ==========================================

@login_required
def inventory_list(request):
    if request.user.role not in ['admin']:
        return redirect('dashboard')

    store = get_store_profile(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_product':
            cat_id = request.POST.get('category')
            new_cat_name = request.POST.get('new_category')
            
            if new_cat_name and new_cat_name.strip() and cat_id == 'NEW_CATEGORY':
                new_category_obj, created = Category.objects.get_or_create(name=new_cat_name.strip(), branch=store)
                cat_id = new_category_obj.id
            else:
                cat_id = cat_id if cat_id and cat_id != 'NEW_CATEGORY' else None

            Product.objects.create(
                branch=store,
                name=request.POST.get('name'),
                barcode=request.POST.get('barcode', ''),
                selling_price=request.POST.get('price', 0),
                cost_price=request.POST.get('cost_price', 0),
                stock_quantity=int(request.POST.get('initial_stock') or 0),
                unit=request.POST.get('product_type', 'Unit'),
                category_id=cat_id
            )
            
        elif action == 'edit_product':
            prod_id = request.POST.get('product_id')
            if prod_id:
                prod = get_object_or_404(Product, id=prod_id, branch=store)
                prod.name = request.POST.get('name')
                cat_id = request.POST.get('category')
                prod.category_id = cat_id if cat_id else None
                prod.cost_price = request.POST.get('cost_price', 0)
                prod.selling_price = request.POST.get('price', 0)
                prod.stock_quantity = int(request.POST.get('stock_quantity') or 0)
                prod.save()
                
        elif action == 'delete_product':
            Product.objects.filter(id=request.POST.get('product_id'), branch=store).delete()
            
        return redirect('inventory_list')

    products = Product.objects.filter(branch=store).order_by('-id')
    categories = Category.objects.filter(branch=store)

    product_data = []
    low_stock_count = 0
    out_of_stock_count = 0
    low_stock_threshold = 10

    for p in products:
        profit = float(p.selling_price) - float(p.cost_price)
        stock_qty = p.stock_quantity
        
        if stock_qty <= 0:
            status_badge = 'Out of Stock'
            out_of_stock_count += 1
        elif stock_qty <= low_stock_threshold:
            status_badge = 'Low stock'
            low_stock_count += 1
        else:
            status_badge = 'In Stock'

        product_data.append({
            'id': p.id,
            'name': p.name,
            'category': p.category.name if p.category else 'Uncategorized',
            'stock_qty': stock_qty,
            'cost_price': p.cost_price,
            'selling_price': p.selling_price,
            'unit': p.unit,
            'profit': profit,
            'status': status_badge,
            'category_id': p.category.id if p.category else ''
        })

    context = {
        'products': product_data,
        'categories': categories,
        'branch_context': store,          # ✅ ADDED
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
    }
    return render(request, 'pages/inventory_list.html', context)


# ==========================================
# INVOICES
# ==========================================

@login_required
def invoice_list(request):
    if request.user.role not in ['admin', 'cashier']:
        return redirect('dashboard')

    store = get_store_profile(request.user)
    invoices = Invoice.objects.filter(branch=store).order_by('-created_at')

    total_count = invoices.count()
    total_amount = invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0

    paid_invoices = invoices.filter(status='Paid')
    paid_count = paid_invoices.count()
    paid_amount = paid_invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0

    pending_invoices = invoices.filter(status__in=['Pending', 'Overdue'])
    pending_count = pending_invoices.count()
    pending_amount = pending_invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0

    invoice_data = []
    for inv in invoices:
        items = []
        for item in inv.items.all():
            items.append({
                'name': item.product.name if item.product else "Unknown",
                'qty': item.quantity,
                'price': float(item.unit_price),
                'total': float(item.line_total)
            })
        
        if inv.customer:
            cust_name = inv.customer.name
            cust_phone = inv.customer.phone
        else:
            cust_name = "Walk-in"
            cust_phone = "N/A"
            
        invoice_data.append({
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'customer_name': cust_name,
            'customer_phone': cust_phone,
            'date': inv.created_at,
            'items_count': inv.items.count(),
            'total_amount': float(inv.grand_total),
            'status': inv.status,
            'items_json': json.dumps(items)
        })

    context = {
        'invoices': invoice_data,
        'branch_context': store,          # ✅ ADDED
        'kpi': {
            'total_count': total_count,
            'total_amount': total_amount,
            'paid_count': paid_count,
            'paid_amount': paid_amount,
            'pending_count': pending_count,
            'pending_amount': pending_amount,
        }
    }
    return render(request, 'pages/invoice_list.html', context)


# ==========================================
# SALES REPORT
# ==========================================

@login_required
def sales_report(request):
    if request.user.role not in ['admin']:
        return redirect('dashboard')

    today = timezone.now().date()
    store = get_store_profile(request.user)
    
    try:
        selected_range = int(request.GET.get('range', 7))
    except ValueError:
        selected_range = 7
        
    start_date = today - timedelta(days=selected_range - 1)

    invoices = Invoice.objects.filter(branch=store, status='Paid', created_at__date__gte=start_date)
    all_invoices = Invoice.objects.filter(branch=store, created_at__date__gte=start_date).order_by('-created_at')

    total_sales = invoices.aggregate(Sum('grand_total'))['grand_total__sum'] or 0
    total_items_sold = InvoiceItem.objects.filter(invoice__in=invoices).aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_invoices_count = all_invoices.count()
    avg_daily_sales = float(total_sales) / selected_range if selected_range > 0 else 0

    top_products_query = InvoiceItem.objects.filter(invoice__in=invoices).values(
        'product__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_rev=Sum('line_total')
    ).order_by('-total_rev')[:5]

    top_products = list(top_products_query)

    category_sales_query = InvoiceItem.objects.filter(invoice__in=invoices).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum('line_total')
    ).order_by('-total_sales')
    
    cat_labels = [c['product__category__name'] or 'Uncategorized' for c in category_sales_query]
    cat_data = [float(c['total_sales'] or 0) for c in category_sales_query]
    
    if not cat_labels:
        cat_labels, cat_data = ['No Data'], [100]

    dates = []
    sales_data = []
    
    for i in range(selected_range - 1, -1, -1):
        target_date = today - timedelta(days=i)
        if selected_range > 30:
            dates.append(target_date.strftime('%d %b'))
        else:
            dates.append(target_date.strftime('%b %d'))
        day_sales = invoices.filter(created_at__date=target_date).aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        sales_data.append(float(day_sales))

    context = {
        'kpi': {
            'total_sales': total_sales,
            'avg_daily_sales': avg_daily_sales,
            'total_invoices': total_invoices_count,
            'total_items_sold': total_items_sold,
        },
        'store': store,
        'branch_context': store,          # ✅ ADDED
        'top_products': top_products,
        'recent_invoices': all_invoices,
        'current_range': str(selected_range),
        'chart_dates': json.dumps(dates),
        'chart_sales': json.dumps(sales_data),
        'cat_labels': json.dumps(cat_labels),
        'cat_data': json.dumps(cat_data),
    }

    return render(request, 'pages/sales_report.html', context)


# ==========================================
# SETTINGS
# ==========================================

@login_required
def settings_view(request):
    if request.user.role != 'admin':
        return redirect('dashboard')
    
    store = get_store_profile(request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_business_details':
            gst_number = request.POST.get('gst_number', '').strip().upper()
            if gst_number:
                gst_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
                if not re.match(gst_pattern, gst_number):
                    messages.error(request, 'Invalid GST number format. Expected format: 22AAAAA0000A1Z5')
                    return redirect('settings')
            
            store.name = request.POST.get('shop_name', store.name)
            store.street_address = request.POST.get('street_address', store.street_address)
            store.city = request.POST.get('city', store.city)
            store.state = request.POST.get('state', store.state)
            store.pincode = request.POST.get('pincode', store.pincode)
            store.gst_number = request.POST.get('gst_number', store.gst_number)
            store.invoice_prefix = request.POST.get('invoice_prefix', store.invoice_prefix)
            
            if 'logo' in request.FILES:
                store.logo = request.FILES['logo']
            if 'login_background' in request.FILES:
                store.login_background = request.FILES['login_background']
                
            store.save()
            messages.success(request, 'Business details updated successfully.')

        elif action == 'create_user':
            try:
                sub = store.subscription
                if not sub.is_active:
                    messages.error(request, 'Your subscription has expired. Renew your plan to create users.')
                    return redirect('settings')
                
                current_staff_count = User.objects.filter(
                    branch=store, is_superuser=False
                ).exclude(role='admin').count()
                
                if current_staff_count >= sub.plan.max_cashiers:
                    messages.error(
                        request,
                        f'User limit reached. Your "{sub.plan.name}" plan allows only '
                        f'{sub.plan.max_cashiers} staff user(s). '
                        f'Upgrade your plan to add more users.'
                    )
                    return redirect('settings')
                    
            except Exception:
                messages.error(request, 'No active subscription found. Purchase a plan to create users.')
                return redirect('settings')

            username  = request.POST.get('username', '').strip()
            password  = request.POST.get('password', '').strip()
            full_name = request.POST.get('full_name', '').strip()
            email     = request.POST.get('email', '').strip()
            phone     = request.POST.get('phone', '').strip()
            role      = request.POST.get('role', 'cashier')

            if not username or not password:
                messages.error(request, 'Username and password are required.')
                return redirect('settings')

            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" is already taken.')
                return redirect('settings')

            User.objects.create_user(
                branch=store,
                username=username,
                password=password,
                full_name=full_name,
                email=email,
                phone=phone,
                role=role,
                is_approved=True,
            )
            messages.success(request, f'User "{username}" created successfully.')

        elif action == 'edit_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id, branch=store)
            user.full_name = request.POST.get('full_name')
            user.email = request.POST.get('email')
            user.phone = request.POST.get('phone')
            user.role = request.POST.get('role')
            new_password = request.POST.get('password')
            if new_password:
                user.set_password(new_password)
            user.save()
            messages.success(request, f'User {user.username} updated successfully.')

        elif action == 'toggle_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, id=user_id, branch=store)
            if user == request.user:
                messages.error(request, "You cannot deactivate your own account.")
            else:
                user.is_active = not user.is_active
                user.save()
                status = "activated" if user.is_active else "deactivated"
                messages.success(request, f'User {user.username} has been {status}.')

        elif action == 'create_coupon':
            code = request.POST.get('code', '').strip().upper()
            if not Coupon.objects.filter(code=code, branch=store).exists():
                Coupon.objects.create(
                    branch=store,
                    code=code,
                    description=request.POST.get('description', ''),
                    discount_type=request.POST.get('discount_type', 'Flat'),
                    discount_value=request.POST.get('discount_value', 0)
                )
                messages.success(request, 'Coupon created successfully.')
            else:
                messages.error(request, 'A coupon with this code already exists in your shop.')
                
        elif action == 'toggle_coupon':
            coupon_id = request.POST.get('coupon_id')
            coupon = get_object_or_404(Coupon, id=coupon_id, branch=store)
            coupon.is_active = not coupon.is_active
            coupon.save()
            
        elif action == 'delete_coupon':
            coupon_id = request.POST.get('coupon_id')
            Coupon.objects.filter(id=coupon_id, branch=store).delete()
            messages.success(request, 'Coupon deleted.')
            
        return redirect('settings')
    
    users = User.objects.filter(branch=store).order_by('id')
    coupons = Coupon.objects.filter(branch=store).order_by('-created_at')

    current_staff_count = User.objects.filter(
        branch=store, is_superuser=False
    ).exclude(role='admin').count()
    
    context = {
        'branch': store,
        'branch_context': store,          # ✅ ADDED
        'users': users,
        'coupons': coupons,
        'current_staff_count': current_staff_count,
    }
    return render(request, 'pages/settings.html', context)


# ==========================================
# PLANS & PAYMENTS
# ==========================================

@login_required
def plans_page(request):
    from .models import Plan, BranchSubscription
    
    plans = Plan.objects.filter(is_active=True).order_by('price')
    store = get_store_profile(request.user)
    
    current_sub = None
    try:
        current_sub = store.subscription
    except Exception:
        pass
    
    plans_data = []
    for plan in plans:
        plans_data.append({
            'obj': plan,
            'features_list': [f.strip() for f in plan.features.split(',') if f.strip()] if plan.features else []
        })
    
    context = {
        'plans_data': plans_data,
        'current_sub': current_sub,
        'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'branch': store,
        'branch_context': store,          # ✅ ADDED
    }
    return render(request, 'pages/plans.html', context)


@login_required
def create_plan_order(request):
    """Creates a Razorpay order when user clicks Buy on a plan."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Only admin can purchase plans'}, status=403)
    
    data = json.loads(request.body)
    plan_id = data.get('plan_id')
    
    try:
        plan = Plan.objects.get(id=plan_id, is_active=True)
    except Plan.DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    amount_paise = int(plan.price * 100)
    
    razorpay_order = client.order.create({
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': f'plan_{plan.id}_{request.user.id}',
        'notes': {
            'plan_name': plan.name,
            'branch': get_store_profile(request.user).name,
        }
    })
    
    return JsonResponse({
        'order_id': razorpay_order['id'],
        'amount': amount_paise,
        'plan_id': plan.id,
        'plan_name': plan.name,
        'key_id': settings.RAZORPAY_KEY_ID,
        'user_name': request.user.full_name or request.user.username,
        'user_email': request.user.email,
        'user_phone': request.user.phone or '',
    })


@csrf_exempt
@login_required
def payment_success(request):
    """Verifies Razorpay signature and activates the subscription."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    
    razorpay_order_id   = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature  = data.get('razorpay_signature')
    plan_id             = data.get('plan_id')
    
    key_secret = settings.RAZORPAY_KEY_SECRET.encode('utf-8')
    msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8')
    generated_signature = hmac.new(key_secret, msg, hashlib.sha256).hexdigest()
    
    if generated_signature != razorpay_signature:
        return JsonResponse({'error': 'Payment verification failed. Invalid signature.'}, status=400)
    
    try:
        plan = Plan.objects.get(id=plan_id)
        store = get_store_profile(request.user)
        
        now = timezone.now()
        end_date = now + timedelta(days=plan.validity_days)
        
        from .models import BranchSubscription
        sub, created = BranchSubscription.objects.update_or_create(
            branch=store,
            defaults={
                'plan': plan,
                'start_date': now,
                'end_date': end_date,
                'status': 'active',
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature,
            }
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{plan.name} activated until {end_date.strftime("%d %b %Y")}',
            'redirect': '/dashboard/'
        })
        
    except Plan.DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
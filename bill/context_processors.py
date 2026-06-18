from .models import Product, Branch,SiteSettings

def global_notifications(request):
    context = {}
    
    # Make the branch profile globally available so the Logo works everywhere
    store = Branch.objects.first()
    context['global_branch'] = store

    # Only calculate notifications if the user is an Admin
    if request.user.is_authenticated and request.user.role == 'admin':
        notifs = []
        
        # 1. Out of Stock
        out_stock = Product.objects.filter(stock_quantity=0).count()
        if out_stock > 0:
            notifs.append(f"🚨 {out_stock} products are currently Out of Stock!")
            
        # 2. Low Stock
        low_stock = Product.objects.filter(stock_quantity__lte=10, stock_quantity__gt=0).count()
        if low_stock > 0:
            notifs.append(f"⚠️ {low_stock} products are running low on stock.")
            
        # 3. Plan Expiration
        if store and hasattr(store, 'subscription'):
            sub = store.subscription
            if sub.is_active and sub.days_remaining <= 5:
                notifs.append(f"⏳ Action Required: Plan expires in {sub.days_remaining} days!")
            elif not sub.is_active:
                notifs.append("❌ Your subscription plan has expired.")
        else:
            notifs.append("❌ No active subscription plan found.")
        
        context['admin_notifications'] = notifs
        context['admin_notif_count'] = len(notifs)

    return context


def site_settings(request):
    return {
        'site_settings': SiteSettings.get_settings()
    }
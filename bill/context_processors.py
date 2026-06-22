from .models import Product, Branch, SiteSettings

def global_notifications(request):
    context = {}

    if not request.user.is_authenticated:
        return context

    store = getattr(request.user, 'branch', None)
    if not store:
        store = Branch.objects.first()

    context['branch_context'] = store 

    if request.user.role == 'admin' and store:
        notifs = []

        # Filter by THIS branch only
        out_stock = Product.objects.filter(branch=store, stock_quantity=0).count()
        if out_stock > 0:
            notifs.append(f"🚨 {out_stock} products are currently Out of Stock!")

        low_stock = Product.objects.filter(branch=store, stock_quantity__lte=10, stock_quantity__gt=0).count()
        if low_stock > 0:
            notifs.append(f"⚠️ {low_stock} products are running low on stock.")

        try:
            sub = store.subscription
            if sub.is_active and sub.days_remaining <= 5:
                notifs.append(f"⏳ Action Required: Plan expires in {sub.days_remaining} days!")
            elif not sub.is_active:
                notifs.append("❌ Your subscription plan has expired.")
        except Exception:
            notifs.append("❌ No active subscription plan found.")

        context['admin_notifications'] = notifs
        context['admin_notif_count'] = len(notifs)

    return context


def site_settings(request):
    return {
        'site_settings': SiteSettings.get_settings()
    }
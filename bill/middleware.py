from django.shortcuts import redirect
from django.utils import timezone
from .models import BranchSubscription

# URLs that are always accessible (no plan check)
EXEMPT_URLS = [
    '/plans/',
    '/plans/checkout/',
    '/plans/payment-success/',
    '/',          # login
    '/logout/',
]

class PlanExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.role == 'admin':
            path = request.path
            
            # Skip check for exempt URLs
            if not any(path.startswith(url) for url in EXEMPT_URLS):
                branch = getattr(request.user, 'branch', None)
                
                # Also check branch from get_store_profile() for single-store setup
                if not branch:
                    from .models import Branch
                    branch = Branch.objects.first()
                
                if branch:
                    try:
                        sub = branch.subscription
                        if not sub.is_active:
                            return redirect('plans_page')
                    except BranchSubscription.DoesNotExist:
                        return redirect('plans_page')
        
        # For cashier/other roles: check if their branch admin has an active plan
        elif request.user.is_authenticated and request.user.role != 'admin':
            path = request.path
            if not any(path.startswith(url) for url in EXEMPT_URLS):
                from .models import Branch
                branch = Branch.objects.first()
                if branch:
                    try:
                        sub = branch.subscription
                        if not sub.is_active:
                            return redirect('plans_page')
                    except BranchSubscription.DoesNotExist:
                        return redirect('plans_page')

        return self.get_response(request)
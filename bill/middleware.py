from django.shortcuts import redirect
from .models import BranchSubscription

EXEMPT_URLS = [
    '/plans/',
    '/plans/checkout/',
    '/plans/payment-success/',
    '/',
    '/logout/',
]

class PlanExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path

            if not any(path.startswith(url) for url in EXEMPT_URLS):
                # ✅ Always use the logged-in user's branch
                branch = getattr(request.user, 'branch', None)

                if branch:
                    try:
                        sub = branch.subscription
                        if not sub.is_active:
                            # Cashiers get logged out, admins go to plans page
                            if request.user.role != 'admin':
                                from django.contrib.auth import logout
                                logout(request)
                                return redirect('login')
                            return redirect('plans_page')
                    except BranchSubscription.DoesNotExist:
                        if request.user.role == 'admin':
                            return redirect('plans_page')
                        from django.contrib.auth import logout
                        logout(request)
                        return redirect('login')

        return self.get_response(request)
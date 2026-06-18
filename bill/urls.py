from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dynamic_dashboard_view, name='dashboard'),
    path('api/pos/checkout/', views.pos_invoice_transaction_api, name='pos_checkout_endpoint'),
    path('settings/', views.settings_view, name='settings'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('billing/', views.billing_pos, name='billing_pos'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('profile/', views.profile_view, name='profile'),

    path('plans/', views.plans_page, name='plans_page'),
    path('plans/create-order/', views.create_plan_order, name='create_plan_order'),
    path('plans/payment-success/', views.payment_success, name='payment_success'),
]
from django.urls import path
from apps.payments.views import PaymentInitiateView, PaymentWebhookView, MockPayView

app_name = 'payments'

urlpatterns = [
    path('<int:pk>/initiate/', PaymentInitiateView.as_view(), name='initiate'),
    path('webhook/',           PaymentWebhookView.as_view(),  name='webhook'),
    path('mock/pay/<str:order_id>/', MockPayView.as_view(),   name='mock_pay'),
]

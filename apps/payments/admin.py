from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'amount', 'currency', 'status', 'paid_at')
    list_filter = ('status', 'currency', 'gateway_name')
    search_fields = ('gateway_order_id', 'submission__title')
    date_hierarchy = 'created_at'

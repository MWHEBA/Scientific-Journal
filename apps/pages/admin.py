from django.contrib import admin
from apps.pages.models import SiteSettings, EditorialBoardMember


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['journal_name', 'apc_amount', 'payment_deadline_days', 'contact_email']


@admin.register(EditorialBoardMember)
class EditorialBoardMemberAdmin(admin.ModelAdmin):
    list_display  = ['name', 'role', 'institution', 'country', 'order', 'is_active']
    list_editable = ['order', 'is_active']
    list_filter   = ['role', 'is_active']
    search_fields = ['name', 'institution', 'country']
    ordering      = ['order', 'name']

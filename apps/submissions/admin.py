from django.contrib import admin
from .models import JournalSection, ArticleSubmission, CoAuthor, ManuscriptFile, AuditLog

@admin.register(JournalSection)
class JournalSectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'order')
    list_editable = ('order',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

class CoAuthorInline(admin.TabularInline):
    model = CoAuthor
    extra = 1

class ManuscriptFileInline(admin.TabularInline):
    model = ManuscriptFile
    extra = 1

@admin.register(ArticleSubmission)
class ArticleSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'author', 'section', 'status', 'created_at')
    list_filter = ('status', 'section', 'is_archived')
    search_fields = ('title', 'abstract', 'corresponding_author_email', 'author__username')
    inlines = [CoAuthorInline, ManuscriptFileInline]
    date_hierarchy = 'created_at'

@admin.register(CoAuthor)
class CoAuthorAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'full_name', 'institution', 'order')
    list_filter = ('institution',)
    search_fields = ('full_name', 'institution')

@admin.register(ManuscriptFile)
class ManuscriptFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'file', 'version', 'is_current', 'uploaded_at')
    list_filter = ('is_current',)
    date_hierarchy = 'uploaded_at'

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'entity_type', 'entity_id', 'event', 'actor', 'created_at')
    list_filter = ('entity_type', 'event')
    search_fields = ('notes', 'actor__username')
    date_hierarchy = 'created_at'

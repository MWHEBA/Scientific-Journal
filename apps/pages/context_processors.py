"""
Context processor للصفحات العامة — يوفر:
- latest_issues: آخر 5 أعداد للـ sidebar
- stats: إحصائيات المجلة للـ stats bar
- sections: أقسام المجلة للـ sidebar
"""
from apps.publishing.models import Issue, PublishedArticle
from apps.submissions.models import JournalSection, ArticleSubmission
from apps.accounts.models import User


def public_context(request):
    """يُضاف لكل الصفحات — خفيف ومُخزَّن في الـ queryset cache."""
    latest_issues = Issue.objects.select_related('volume').prefetch_related(
        'articles'
    ).order_by('-published_at', '-volume__number', '-number')[:5]

    sections = JournalSection.objects.all()

    stats = {
        'published':   PublishedArticle.objects.count(),
        'under_review': ArticleSubmission.objects.filter(
            status='under_review'
        ).count(),
        'reviewers':   User.objects.filter(role=User.ROLE_REVIEWER).count(),
    }

    return {
        'latest_issues': latest_issues,
        'sections':      sections,
        'stats':         stats,
    }

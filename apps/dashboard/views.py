from django.views.generic import ListView, TemplateView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.db import models as django_models
from django.conf import settings
from urllib.parse import urlencode

from apps.accounts.mixins import AuthorRequiredMixin, ReviewerRequiredMixin, AdminRequiredMixin, SuperUserRequiredMixin
from apps.submissions.models import ArticleSubmission
from apps.submissions.statuses import SubmissionStatus
from apps.payments.models import Payment


class DashboardHomeRedirectView(LoginRequiredMixin, View):
    """مدخل موحّد للوحة التحكم: يوجّه حسب دور المستخدم."""

    def get(self, request):
        if request.user.role == 'admin':
            return redirect('dashboard:admin')
        if request.user.role == 'reviewer':
            return redirect('dashboard:reviewer')
        return redirect('dashboard:author')


class AuthorDashboardView(AuthorRequiredMixin, ListView):
    """لوحة تحكم المؤلف — قائمة تقديماته مع حالاتها."""
    model               = ArticleSubmission
    template_name       = 'dashboard/author/index.html'
    context_object_name = 'submissions'
    ordering            = ['-created_at']

    def get_queryset(self):
        qs = ArticleSubmission.objects.filter(
            author=self.request.user,
            is_archived=False,
        ).exclude(status='published').select_related('section').prefetch_related(
            'manuscript_files', 'reviews', 'co_authors'
        ).order_by('-created_at')
        
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # احسب الإحصائيات من كل التقديمات بدون فلترة (بدون المنشورة)
        all_submissions = ArticleSubmission.objects.filter(
            author=self.request.user,
            is_archived=False,
        ).exclude(status='published')
        ctx['total']     = all_submissions.count()
        ctx['active']    = all_submissions.exclude(status__in=['draft', 'rejected', 'expired']).count()
        ctx['published'] = ArticleSubmission.objects.filter(
            author=self.request.user, status='published'
        ).count()
        ctx['archived'] = ArticleSubmission.objects.filter(
            author=self.request.user, is_archived=True
        ).count()
        return ctx


class AuthorArchiveView(AuthorRequiredMixin, ListView):
    """أرشيف المؤلف — تقديمات مرفوضة أو مسحوبة أخفاها المؤلف من القائمة الرئيسية."""
    model               = ArticleSubmission
    template_name       = 'dashboard/author/archive.html'
    context_object_name = 'submissions'
    ordering            = ['-updated_at']

    def get_queryset(self):
        return ArticleSubmission.objects.filter(
            author=self.request.user,
            is_archived=True,
        ).select_related('section').prefetch_related(
            'manuscript_files', 'reviews', 'co_authors'
        ).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['archived_count'] = self.get_queryset().count()
        return ctx


class AuthorDraftsView(AuthorRequiredMixin, ListView):
    """صفحة المسودات — قائمة مسودات المؤلف فقط."""
    model               = ArticleSubmission
    template_name       = 'dashboard/author/drafts.html'
    context_object_name = 'submissions'
    ordering            = ['-created_at']

    def get_queryset(self):
        return ArticleSubmission.objects.filter(
            author=self.request.user,
            status='draft'
        ).select_related('section').prefetch_related(
            'manuscript_files', 'reviews', 'co_authors'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_drafts'] = self.get_queryset().count()
        return ctx


class AuthorSubmissionDetailView(AuthorRequiredMixin, View):
    """عرض تفاصيل تقديم يملكه المؤلف."""
    template_name = 'dashboard/admin/submission_detail.html'

    def get(self, request, pk):
        from apps.submissions.models import ManuscriptFile
        submission = get_object_or_404(
            ArticleSubmission.objects.select_related(
                'author', 'section', 'assigned_reviewer'
            ).prefetch_related(
                django_models.Prefetch(
                    'manuscript_files',
                    queryset=ManuscriptFile.objects.order_by('-uploaded_at', '-version')
                ),
                'reviews',
                'co_authors'
            ),
            pk=pk,
            author=request.user,
        )
        try:
            payment_record = submission.payment
        except Exception:
            payment_record = None
        return render(request, self.template_name, {
            'submission': submission,
            'payment_record': payment_record,
        })


class AuthorPublishedArticlesView(AuthorRequiredMixin, ListView):
    """لوحة تحكم المؤلف — قائمة مقالاته المنشورة."""
    template_name       = 'dashboard/author/published.html'
    context_object_name = 'articles'
    paginate_by         = 20

    def get_queryset(self):
        from apps.publishing.models import PublishedArticle
        return PublishedArticle.objects.filter(
            submission__author=self.request.user
        ).select_related(
            'submission__author', 'section', 'issue', 'issue__volume'
        ).order_by('-published_at')


class ReviewerDashboardView(ReviewerRequiredMixin, ListView):
    """لوحة تحكم المراجع — مخطوطات مصنّفة: جديدة، قيد المراجعة، مكتملة."""
    template_name       = 'dashboard/reviewer/index.html'
    context_object_name = 'reviews'

    def get_queryset(self):
        from apps.reviews.models import Review
        # احصل على المراجعات اللي المراجع الحالي هو المراجع المعيّن فيها الآن فقط
        # (وليس كل المراجعات اللي راجعها في الماضي)
        return Review.objects.filter(
            reviewer=self.request.user,
            submission__assigned_reviewer=self.request.user
        ).select_related('submission', 'submission__section').order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.reviews.models import Review
        qs = self.get_queryset()
        ctx['new_reviews']        = qs.filter(is_submitted=False,
                                               submission__status=SubmissionStatus.UNDER_REVIEW)
        ctx['in_progress_reviews'] = qs.filter(is_submitted=False)
        ctx['completed_reviews']   = qs.filter(is_submitted=True)
        ctx['total']               = qs.count()
        ctx['pending_count']       = qs.filter(is_submitted=False).count()
        ctx['completed_count']     = qs.filter(is_submitted=True).count()
        return ctx


class ReviewerSubmissionsView(ReviewerRequiredMixin, ListView):
    """عرض التقديمات للمراجع — مقالاته قيد المراجعة + مقالات الفحص الأولي بدون مراجع."""
    model               = ArticleSubmission
    template_name       = 'dashboard/admin/submissions.html'
    context_object_name = 'submissions'
    paginate_by         = 20

    def get_queryset(self):
        from apps.reviews.models import Review
        
        # احصل على المقالات اللي المراجع الحالي هو المراجع المعيّن فيها الآن
        # (وليس كل المقالات اللي راجعها في الماضي)
        my_assigned_submissions = ArticleSubmission.objects.filter(
            assigned_reviewer=self.request.user,
            status=SubmissionStatus.UNDER_REVIEW
        ).values_list('pk', flat=True)
        
        # دمج الاستعلامات:
        # 1. المقالات قيد المراجعة اللي هو المراجع المعيّن فيها الآن
        # 2. مقالات الفحص الأولي بدون مراجع معيّن
        # 3. مقالات تحت المراجعة بدون مراجع معيّن
        from django.db.models import Q
        qs = ArticleSubmission.objects.filter(
            Q(pk__in=my_assigned_submissions) |
            Q(status=SubmissionStatus.UNDER_REVIEW, assigned_reviewer__isnull=True)
        ).select_related(
            'author', 'section', 'assigned_reviewer'
        ).order_by('-created_at')

        section = self.request.GET.get('section')
        search = (self.request.GET.get('q') or '').strip()

        if section:
            qs = qs.filter(section_id=section)
        if search:
            search_filter = (
                django_models.Q(title__icontains=search) |
                django_models.Q(author__username__icontains=search) |
                django_models.Q(author__first_name__icontains=search) |
                django_models.Q(author__last_name__icontains=search)
            )
            if search.isdigit():
                search_filter |= django_models.Q(pk=int(search))
            qs = qs.filter(search_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        
        ctx['sections']        = JournalSection.objects.all()
        ctx['status_choices']  = ArticleSubmission.STATUS_CHOICES
        ctx['current_filters'] = {
            'status':    '',
            'section':   self.request.GET.get('section', ''),
            'q':         self.request.GET.get('q', '').strip(),
        }
        
        # احصل على المقالات اللي المراجع الحالي هو المراجع المعيّن فيها الآن
        my_assigned_submissions = ArticleSubmission.objects.filter(
            assigned_reviewer=self.request.user,
            status=SubmissionStatus.UNDER_REVIEW
        ).values_list('pk', flat=True)
        
        from django.db.models import Q
        base_qs = ArticleSubmission.objects.filter(
            Q(pk__in=my_assigned_submissions) |
            Q(status=SubmissionStatus.UNDER_REVIEW, assigned_reviewer__isnull=True)
        ).select_related('author', 'section', 'assigned_reviewer')
        
        section = self.request.GET.get('section')
        search = (self.request.GET.get('q') or '').strip()
        if section:
            base_qs = base_qs.filter(section_id=section)
        if search:
            search_filter = (
                django_models.Q(title__icontains=search) |
                django_models.Q(author__username__icontains=search) |
                django_models.Q(author__first_name__icontains=search) |
                django_models.Q(author__last_name__icontains=search)
            )
            if search.isdigit():
                search_filter |= django_models.Q(pk=int(search))
            base_qs = base_qs.filter(search_filter)

        # عرض الحالات المتاحة
        status_labels = dict(ArticleSubmission.STATUS_CHOICES)
        ctx['preset_items'] = [
            {
                'key': f'status:{SubmissionStatus.UNDER_REVIEW}',
                'label': 'قيد المراجعة',
                'count': base_qs.filter(status=SubmissionStatus.UNDER_REVIEW).count()
            },
            {
                'key': f'status:{SubmissionStatus.INITIAL_CHECK}',
                'label': 'فحص أولي',
                'count': base_qs.filter(status=SubmissionStatus.INITIAL_CHECK).count()
            }
        ]

        preset_query = {}
        if current := self.request.GET.get('q', '').strip():
            preset_query['q'] = current
        if current := self.request.GET.get('section', ''):
            preset_query['section'] = current
        ctx['preset_query'] = urlencode(preset_query, doseq=True)

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        ctx['page_query'] = urlencode(query_params, doseq=True)
        ctx['default_submissions_url'] = reverse('dashboard:admin_submissions')
        ctx['base_submissions_url'] = reverse('dashboard:reviewer_submissions')
        
        return ctx


class ReviewerArticlesView(ReviewerRequiredMixin, ListView):
    """عرض المقالات المنشورة للمراجع — بدون مقالات الفحص الأولي."""
    template_name = 'dashboard/admin/articles.html'
    context_object_name = 'articles'
    paginate_by = 20

    def get_queryset(self):
        from apps.publishing.models import PublishedArticle
        
        # عرض المقالات المنشورة فقط (بدون الفحص الأولي)
        qs = PublishedArticle.objects.filter(
            submission__reviews__reviewer=self.request.user
        ).select_related(
            'submission__author', 'section', 'issue', 'issue__volume'
        ).order_by('-published_at').distinct()

        section = self.request.GET.get('section', '').strip()
        issue = self.request.GET.get('issue', '').strip()
        search = (self.request.GET.get('q') or '').strip()

        if section:
            qs = qs.filter(section_id=section)
        if issue:
            qs = qs.filter(issue_id=issue)
        if search:
            qs = qs.filter(
                django_models.Q(title__icontains=search) |
                django_models.Q(submission__author__username__icontains=search) |
                django_models.Q(submission__author__first_name__icontains=search) |
                django_models.Q(submission__author__last_name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        from apps.publishing.models import Issue
        
        ctx['sections'] = JournalSection.objects.order_by('name')
        ctx['issues'] = Issue.objects.select_related('volume').order_by('-volume__number', '-number')
        ctx['current_filters'] = {
            'section': self.request.GET.get('section', '').strip(),
            'issue': self.request.GET.get('issue', '').strip(),
            'q': self.request.GET.get('q', '').strip(),
        }
        
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        ctx['page_query'] = urlencode(query_params, doseq=True)
        ctx['default_submissions_url'] = reverse('dashboard:admin_submissions')
        ctx['base_submissions_url'] = reverse('dashboard:reviewer_submissions')
        
        return ctx


class ReviewerPostReviewView(ReviewerRequiredMixin, ListView):
    """تقديمات المراجع بعد إرسال المراجعة وقبل النشر."""
    model = ArticleSubmission
    template_name = 'dashboard/admin/submissions.html'
    context_object_name = 'submissions'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Prefetch
        from apps.reviews.models import Review
        post_review_statuses = [
            SubmissionStatus.REVISION_REQUIRED,
            SubmissionStatus.ACCEPTED,
            SubmissionStatus.PAYMENT_PROCESSING,
            SubmissionStatus.PAID,
            SubmissionStatus.EXPIRED,
        ]
        qs = ArticleSubmission.objects.filter(
            reviews__reviewer=self.request.user,
            reviews__is_submitted=True,
            status__in=post_review_statuses,
        ).select_related(
            'author', 'section', 'assigned_reviewer'
        ).prefetch_related(
            Prefetch(
                'reviews',
                queryset=Review.objects.filter(reviewer=self.request.user).order_by('-submitted_at', '-created_at'),
            )
        ).distinct().order_by('-updated_at', '-created_at')

        status = (self.request.GET.get('status') or '').strip()
        section = (self.request.GET.get('section') or '').strip()
        date_from = (self.request.GET.get('date_from') or '').strip()
        date_to = (self.request.GET.get('date_to') or '').strip()
        search = (self.request.GET.get('q') or '').strip()

        if status:
            qs = qs.filter(status=status)
        if section:
            qs = qs.filter(section_id=section)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            search_filter = (
                django_models.Q(title__icontains=search) |
                django_models.Q(author__username__icontains=search) |
                django_models.Q(author__first_name__icontains=search) |
                django_models.Q(author__last_name__icontains=search)
            )
            if search.isdigit():
                search_filter |= django_models.Q(pk=int(search))
            qs = qs.filter(search_filter)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        from django.urls import reverse
        ctx['sections'] = JournalSection.objects.all()
        ctx['status_choices'] = ArticleSubmission.STATUS_CHOICES
        ctx['current_filters'] = {
            'status': (self.request.GET.get('status') or '').strip(),
            'section': (self.request.GET.get('section') or '').strip(),
            'date_from': (self.request.GET.get('date_from') or '').strip(),
            'date_to': (self.request.GET.get('date_to') or '').strip(),
            'q': (self.request.GET.get('q') or '').strip(),
            'preset': '',
        }
        ctx['preset_items'] = []
        ctx['preset_query'] = ''
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        ctx['page_query'] = urlencode(query_params, doseq=True)
        ctx['default_submissions_url'] = reverse('dashboard:admin_submissions')
        ctx['base_submissions_url'] = reverse('dashboard:reviewer_post_review')
        ctx['is_post_review_page'] = True
        return ctx


class ReviewerSubmissionDetailView(ReviewerRequiredMixin, View):
    """عرض تفاصيل تقديم للمراجع — يقدر يشوف مقالته أو الفحص الأولي."""
    template_name = 'dashboard/admin/submission_detail.html'

    def get(self, request, pk):
        from apps.submissions.models import ManuscriptFile
        from apps.submissions.models import JournalSection
        
        submission = get_object_or_404(
            ArticleSubmission.objects.select_related(
                'author', 'section', 'assigned_reviewer'
            ).prefetch_related(
                django_models.Prefetch(
                    'manuscript_files',
                    queryset=ManuscriptFile.objects.order_by('-uploaded_at', '-version')
                ),
                'reviews',
                'co_authors'
            ),
            pk=pk,
        )
        
        # تحقق من أن المراجع يقدر يشوف هذه المقالة
        # إما أنه المراجع المعيّن الآن أو أنها في الفحص الأولي بدون مراجع معيّن أو تحت المراجعة بدون مراجع معيّن
        is_assigned_reviewer = (
            submission.assigned_reviewer_id == request.user.id and
            submission.status == SubmissionStatus.UNDER_REVIEW
        )
        
        is_initial_check_unassigned = (
            submission.status == SubmissionStatus.INITIAL_CHECK and
            submission.assigned_reviewer is None
        )
        
        is_under_review_unassigned = (
            submission.status == SubmissionStatus.UNDER_REVIEW and
            submission.assigned_reviewer is None
        )
        
        if not (
            is_assigned_reviewer
            or is_initial_check_unassigned
            or is_under_review_unassigned
            or (submission.status == SubmissionStatus.ACCEPTED and submission.assigned_reviewer is None)
        ):
            raise PermissionDenied("ليس لديك صلاحية لعرض هذه المقالة")
        
        try:
            payment_record = submission.payment
        except Exception:
            payment_record = None
        return render(request, self.template_name, {
            'submission': submission,
            'sections': JournalSection.objects.order_by('name'),
            'payment_record': payment_record,
        })

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        
        # تحقق من الصلاحيات
        is_assigned_reviewer = (
            submission.assigned_reviewer_id == request.user.id and
            submission.status == SubmissionStatus.UNDER_REVIEW
        )
        
        is_initial_check_unassigned = (
            submission.status == SubmissionStatus.INITIAL_CHECK and
            submission.assigned_reviewer is None
        )
        
        is_under_review_unassigned = (
            submission.status == SubmissionStatus.UNDER_REVIEW and
            submission.assigned_reviewer is None
        )
        
        if not (
            is_assigned_reviewer
            or is_initial_check_unassigned
            or is_under_review_unassigned
            or (submission.status == SubmissionStatus.ACCEPTED and submission.assigned_reviewer is None)
        ):
            raise PermissionDenied("ليس لديك صلاحية لتعديل هذه المقالة")
        
        action = request.POST.get('action')
        from apps.submissions.services import SubmissionService
        from apps.submissions.exceptions import InvalidStateTransitionError

        # المراجع يمكنه فقط تعيين نفسه أو مراجعة التقديمات المعينة له
        # لا يمكنه رفع/رفض التقديمات في الفحص الأولي
        if action == 'self_assign':
            # تعيين المراجع نفسه كمراجع للتقديم
            if submission.status == SubmissionStatus.INITIAL_CHECK:
                messages.error(request, 'لا يمكن تعيين نفسك أثناء قيد الفحص الأولي.')
                return redirect(reverse('dashboard:reviewer_submissions'))

            if submission.assigned_reviewer is not None:
                messages.error(request, 'هذا التقديم معيّن لمراجع بالفعل.')
                return redirect(reverse('dashboard:reviewer_submissions'))
            
            from apps.reviews.models import Review
            submission.assigned_reviewer = request.user
            submission.save(update_fields=['assigned_reviewer', 'updated_at'])
            
            # إنشاء Review object
            Review.objects.get_or_create(
                submission=submission,
                reviewer=request.user,
                defaults={'revision_round': submission.revision_count + 1},
            )
            
            messages.success(request, 'تم تعيينك كمراجع لهذا التقديم.')
            return redirect(reverse('dashboard:reviewer_submissions'))
        
        # الإجراءات الأخرى (pass/reject) غير مسموحة للمراجع
        messages.error(request, 'ليس لديك صلاحية لتنفيذ هذا الإجراء.')
        return redirect(reverse('dashboard:reviewer_submissions'))


class AssignReviewerView(AdminRequiredMixin, View):
    """تعيين مراجع لتقديم — قائمة المراجعين + تخصصاتهم + عدد مراجعاتهم الحالية."""
    template_name = 'dashboard/admin/assign_reviewer.html'

    def get(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        from apps.accounts.models import User, ReviewerProfile
        from apps.reviews.models import Review
        reviewers = User.objects.filter(role=User.ROLE_REVIEWER).select_related(
            'reviewer_profile'
        ).prefetch_related('reviewer_profile__specialties')

        reviewer_data = []
        for reviewer in reviewers:
            active_count = Review.objects.filter(
                reviewer=reviewer, is_submitted=False
            ).count()
            try:
                profile = reviewer.reviewer_profile
                specialties = profile.specialties.all()
            except Exception:
                specialties = []
            reviewer_data.append({
                'user':        reviewer,
                'specialties': specialties,
                'active_count': active_count,
            })

        return render(request, self.template_name, {
            'submission':    submission,
            'reviewer_data': reviewer_data,
        })

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        reviewer_id = request.POST.get('reviewer_id')
        if not reviewer_id:
            messages.error(request, 'يرجى اختيار مراجع.')
            return redirect(reverse('dashboard:assign_reviewer', kwargs={'pk': pk}))

        from apps.accounts.models import User
        from apps.reviews.models import Review
        reviewer = get_object_or_404(User, pk=reviewer_id, role=User.ROLE_REVIEWER)

        # حفظ original_reviewer عند أول تعيين فقط
        if submission.original_reviewer is None:
            submission.original_reviewer = reviewer

        submission.assigned_reviewer = reviewer
        submission.save(update_fields=['assigned_reviewer', 'original_reviewer', 'updated_at'])

        # إنشاء Review object للمراجع
        Review.objects.get_or_create(
            submission=submission,
            reviewer=reviewer,
            defaults={'revision_round': submission.revision_count + 1},
        )

        # إشعار المراجع
        from apps.notifications.services import NotificationService
        NotificationService.notify_reviewer_assigned(submission, reviewer)

        messages.success(request, f'تم تعيين {reviewer.get_full_name() or reviewer.username} مراجعاً للمقالة.')
        return redirect(reverse('dashboard:admin_submissions'))


class SiteSettingsView(AdminRequiredMixin, View):
    """إدارة إعدادات المجلة — Singleton."""
    template_name = 'dashboard/admin/settings.html'

    def get(self, request):
        from apps.pages.models import SiteSettings
        from apps.pages.forms import SiteSettingsForm
        settings_obj = SiteSettings.get()
        form = SiteSettingsForm(instance=settings_obj)
        return render(request, self.template_name, {'form': form, 'settings': settings_obj})

    @staticmethod
    def _recompute_current_issue():
        from apps.publishing.models import Issue
        current = Issue.objects.select_related('volume').order_by('-volume__year', '-quarter', '-number').first()
        Issue.objects.update(is_current=False)
        if current:
            Issue.objects.filter(pk=current.pk).update(is_current=True)

    def post(self, request):
        from apps.pages.models import SiteSettings
        from apps.pages.forms import SiteSettingsForm
        settings_obj = SiteSettings.get()
        form = SiteSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ إعدادات المجلة بنجاح.')
            return redirect(reverse('dashboard:settings'))
        return render(request, self.template_name, {'form': form, 'settings': settings_obj})


# ═══════════════════════════════════════════════════════════════
# المرحلة 7 — لوحات التحكم الكاملة
# ═══════════════════════════════════════════════════════════════

class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """لوحة تحكم المشرف — إحصائيات شاملة."""
    template_name = 'dashboard/admin/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.payments.models import Payment
        from apps.publishing.models import PublishedArticle

        qs = ArticleSubmission.objects.all()
        ctx['total_submissions']  = qs.count()
        ctx['status_counts']      = {
            s: qs.filter(status=s).count()
            for s in [
                SubmissionStatus.INITIAL_CHECK,
                SubmissionStatus.UNDER_REVIEW,
                SubmissionStatus.REVISION_REQUIRED,
                SubmissionStatus.ACCEPTED,
                SubmissionStatus.PAYMENT_PROCESSING,
                SubmissionStatus.PAID,
                SubmissionStatus.PUBLISHED,
                SubmissionStatus.REJECTED,
                SubmissionStatus.EXPIRED,
            ]
        }
        ctx['pending_payments']   = Payment.objects.filter(
            status__in=[Payment.STATUS_PENDING, Payment.STATUS_PROCESSING]
        ).count()
        ctx['ready_to_publish']   = qs.filter(status=SubmissionStatus.PAID).count()
        ctx['recent_submissions'] = qs.select_related(
            'author', 'section'
        ).order_by('-created_at')[:10]
        return ctx


class AdminSubmissionsView(AdminRequiredMixin, ListView):
    """لوحة تحكم المشرف — إدارة التقديمات مع فلترة."""
    model               = ArticleSubmission
    template_name       = 'dashboard/admin/submissions.html'
    context_object_name = 'submissions'
    paginate_by         = 20

    PRESET_FILTERS = {
        'unassigned_review': {'status': SubmissionStatus.UNDER_REVIEW, 'assigned_reviewer__isnull': True},
    }

    def get_queryset(self):
        qs = ArticleSubmission.objects.select_related(
            'author', 'section', 'assigned_reviewer'
        ).exclude(
            status__in=[SubmissionStatus.PUBLISHED, SubmissionStatus.DRAFT]
        ).order_by('-created_at')

        status = self.request.GET.get('status')
        section = self.request.GET.get('section')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        search = (self.request.GET.get('q') or '').strip()
        preset = (self.request.GET.get('preset') or '').strip()

        if preset.startswith('status:'):
            status_value = preset.split(':', 1)[1]
            qs = qs.filter(status=status_value)
        elif preset in self.PRESET_FILTERS:
            qs = qs.filter(**self.PRESET_FILTERS[preset])

        if status:
            qs = qs.filter(status=status)
        if section:
            qs = qs.filter(section_id=section)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            search_filter = (
                django_models.Q(title__icontains=search) |
                django_models.Q(author__username__icontains=search) |
                django_models.Q(author__first_name__icontains=search) |
                django_models.Q(author__last_name__icontains=search)
            )
            if search.isdigit():
                search_filter |= django_models.Q(pk=int(search))
            qs = qs.filter(search_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        from django.urls import reverse
        ctx['sections']        = JournalSection.objects.all()
        ctx['status_choices']  = ArticleSubmission.STATUS_CHOICES
        ctx['current_filters'] = {
            'status':    self.request.GET.get('status', ''),
            'section':   self.request.GET.get('section', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to':   self.request.GET.get('date_to', ''),
            'q':         self.request.GET.get('q', '').strip(),
            'preset':    self.request.GET.get('preset', '').strip(),
        }

        # Preset counters based on current search scope (without status/preset restriction).
        base_qs = ArticleSubmission.objects.select_related('author', 'section', 'assigned_reviewer')
        base_qs = base_qs.exclude(status__in=[SubmissionStatus.PUBLISHED, SubmissionStatus.DRAFT])
        section = self.request.GET.get('section')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        search = (self.request.GET.get('q') or '').strip()
        if section:
            base_qs = base_qs.filter(section_id=section)
        if date_from:
            base_qs = base_qs.filter(created_at__date__gte=date_from)
        if date_to:
            base_qs = base_qs.filter(created_at__date__lte=date_to)
        if search:
            search_filter = (
                django_models.Q(title__icontains=search) |
                django_models.Q(author__username__icontains=search) |
                django_models.Q(author__first_name__icontains=search) |
                django_models.Q(author__last_name__icontains=search)
            )
            if search.isdigit():
                search_filter |= django_models.Q(pk=int(search))
            base_qs = base_qs.filter(search_filter)

        status_labels = dict(ArticleSubmission.STATUS_CHOICES)
        ordered_statuses = [key for key, _ in ArticleSubmission.STATUS_CHOICES]
        status_counts = {
            row['status']: row['count']
            for row in base_qs.values('status').annotate(count=django_models.Count('id'))
        }
        ctx['preset_items'] = []
        for status_key in ordered_statuses:
            count = status_counts.get(status_key, 0)
            preset_key = f'status:{status_key}'
            if count > 0 or self.request.GET.get('preset') == preset_key:
                ctx['preset_items'].append({
                    'key': preset_key,
                    'label': status_labels.get(status_key, status_key),
                    'count': count
                })

        unassigned_count = base_qs.filter(
            status=SubmissionStatus.UNDER_REVIEW,
            assigned_reviewer__isnull=True
        ).count()
        if unassigned_count > 0 or self.request.GET.get('preset') == 'unassigned_review':
            ctx['preset_items'].insert(0, {
                'key': 'unassigned_review',
                'label': 'تحت المراجعة بدون مراجع',
                'count': unassigned_count
            })

        preset_query = {}
        if current := self.request.GET.get('q', '').strip():
            preset_query['q'] = current
        if current := self.request.GET.get('section', ''):
            preset_query['section'] = current
        if current := self.request.GET.get('date_from', ''):
            preset_query['date_from'] = current
        if current := self.request.GET.get('date_to', ''):
            preset_query['date_to'] = current
        ctx['preset_query'] = urlencode(preset_query, doseq=True)

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        ctx['page_query'] = urlencode(query_params, doseq=True)
        ctx['default_submissions_url'] = reverse('dashboard:admin_submissions')
        return ctx


class AdminArticlesView(AdminRequiredMixin, ListView):
    """Admin page for published articles only."""
    template_name = 'dashboard/admin/articles.html'
    context_object_name = 'articles'
    paginate_by = 20

    def get_queryset(self):
        from apps.publishing.models import PublishedArticle
        qs = PublishedArticle.objects.select_related(
            'submission__author', 'section', 'issue', 'issue__volume'
        ).order_by('-published_at')

        section = self.request.GET.get('section', '').strip()
        issue = self.request.GET.get('issue', '').strip()
        search = (self.request.GET.get('q') or '').strip()

        if section:
            qs = qs.filter(section_id=section)
        if issue:
            qs = qs.filter(issue_id=issue)
        if search:
            qs = qs.filter(
                django_models.Q(title__icontains=search) |
                django_models.Q(submission__author__username__icontains=search) |
                django_models.Q(submission__author__first_name__icontains=search) |
                django_models.Q(submission__author__last_name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        from apps.publishing.models import Issue
        ctx['sections'] = JournalSection.objects.order_by('name')
        ctx['issues'] = Issue.objects.select_related('volume').order_by('-volume__number', '-number')
        ctx['current_filters'] = {
            'section': self.request.GET.get('section', '').strip(),
            'issue': self.request.GET.get('issue', '').strip(),
            'q': self.request.GET.get('q', '').strip(),
        }
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            query_params.pop('page')
        ctx['page_query'] = urlencode(query_params, doseq=True)
        return ctx


class AdminSubmissionDetailView(AdminRequiredMixin, View):
    """عرض تفاصيل تقديم + إجراءات الفحص الأولي."""
    template_name = 'dashboard/admin/submission_detail.html'

    def get(self, request, pk):
        from apps.submissions.models import ManuscriptFile
        submission = get_object_or_404(
            ArticleSubmission.objects.select_related(
                'author', 'section', 'assigned_reviewer'
            ).prefetch_related(
                django_models.Prefetch(
                    'manuscript_files',
                    queryset=ManuscriptFile.objects.order_by('-uploaded_at', '-version')
                ),
                'reviews',
                'co_authors'
            ),
            pk=pk,
        )
        try:
            payment_record = submission.payment
        except Exception:
            payment_record = None
        return render(request, self.template_name, {
            'submission': submission,
            'payment_record': payment_record,
        })

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        action = request.POST.get('action')
        from apps.submissions.services import SubmissionService
        from apps.submissions.exceptions import InvalidStateTransitionError

        if action == 'pass':
            if submission.section_id is None:
                messages.error(request, 'لا يمكن قبول التقديم للمراجعة قبل تحديد القسم.')
                return redirect(reverse('dashboard:submission_detail', kwargs={'pk': pk}))
            try:
                SubmissionService.admin_pass_initial_check(submission, actor=request.user)
                messages.success(request, 'تم قبول التقديم للمراجعة.')
            except InvalidStateTransitionError as e:
                messages.error(request, f'خطأ: {e}')

        elif action == 'set_section':
            section_id = (request.POST.get('section_id') or '').strip()
            if not section_id:
                messages.error(request, 'يرجى اختيار قسم صالح.')
                return redirect(reverse('dashboard:submission_detail', kwargs={'pk': pk}))
            submission.section_id = section_id
            submission.save(update_fields=['section', 'updated_at'])
            messages.success(request, 'تم تحديث قسم المقالة بنجاح.')
            return redirect(reverse('dashboard:submission_detail', kwargs={'pk': pk}))

        elif action == 'reject':
            reason = request.POST.get('reason', '').strip()
            if not reason:
                messages.error(request, 'يرجى إدخال سبب الرفض.')
                return redirect(reverse('dashboard:submission_detail', kwargs={'pk': pk}))
            try:
                SubmissionService.admin_reject_initial_check(
                    submission, actor=request.user, reason=reason
                )
                messages.success(request, 'تم رفض التقديم.')
            except InvalidStateTransitionError as e:
                messages.error(request, f'خطأ: {e}')

        return redirect(reverse('dashboard:admin_submissions'))


class VolumeCreateView(AdminRequiredMixin, View):
    """إنشاء مجلد جديد."""
    template_name = 'dashboard/admin/volume_form.html'

    def get(self, request):
        from apps.publishing.models import Volume
        volumes = Volume.objects.all()
        return render(request, self.template_name, {'volumes': volumes})

    def post(self, request):
        from apps.publishing.models import Volume
        number = request.POST.get('number')
        year   = request.POST.get('year')
        if number and year:
            Volume.objects.get_or_create(number=number, defaults={'year': year})
            messages.success(request, f'تم إنشاء المجلد {number}.')
        else:
            messages.error(request, 'يرجى إدخال رقم المجلد والسنة.')
        return redirect(reverse('dashboard:volumes'))


class VolumeManagementView(AdminRequiredMixin, View):
    """Admin view for managing volumes."""
    template_name = 'dashboard/admin/volume_form.html'

    def get(self, request):
        from django.db.models import Count
        from django.utils import timezone
        from apps.publishing.models import Volume

        volumes = Volume.objects.annotate(issue_count=Count('issues')).order_by('-number')
        next_number = (volumes.first().number + 1) if volumes.exists() else 1
        return render(request, self.template_name, {
            'volumes': volumes,
            'stats': {
                'total_volumes': volumes.count(),
                'total_issues': sum(v.issue_count for v in volumes),
                'latest_volume': volumes.first(),
            },
            'defaults': {
                'number': next_number,
                'year': timezone.now().year,
            },
        })

    def post(self, request):
        from apps.publishing.models import Volume

        number_raw = (request.POST.get('number') or '').strip()
        year_raw = (request.POST.get('year') or '').strip()
        try:
            number = int(number_raw)
            year = int(year_raw)
            if number < 1 or year < 1900 or year > 2100:
                raise ValueError
        except ValueError:
            messages.error(request, 'يرجى إدخال رقم مجلد وسنة صالحين.')
            return redirect(reverse('dashboard:volumes'))

        _, created = Volume.objects.get_or_create(number=number, defaults={'year': year})
        if created:
            messages.success(request, f'تم إنشاء المجلد {number}.')
        else:
            messages.warning(request, f'المجلد {number} موجود مسبقاً.')
        return redirect(reverse('dashboard:volumes'))


class VolumeUpdateView(AdminRequiredMixin, View):
    """Update an existing volume."""

    def post(self, request, pk):
        from django.db import IntegrityError
        from apps.publishing.models import Volume

        volume = get_object_or_404(Volume, pk=pk)
        number_raw = (request.POST.get('number') or '').strip()
        year_raw = (request.POST.get('year') or '').strip()
        try:
            number = int(number_raw)
            year = int(year_raw)
            if number < 1 or year < 1900 or year > 2100:
                raise ValueError
        except ValueError:
            messages.error(request, 'يرجى إدخال رقم مجلد وسنة صالحين.')
            return redirect(reverse('dashboard:volumes'))

        volume.number = number
        volume.year = year
        try:
            volume.save(update_fields=['number', 'year'])
        except IntegrityError:
            messages.error(request, 'رقم المجلد مستخدم بالفعل.')
            return redirect(reverse('dashboard:volumes'))

        messages.success(request, f'تم تحديث المجلد {volume.number}.')
        return redirect(reverse('dashboard:volumes'))


class IssueCreateView(AdminRequiredMixin, View):
    @staticmethod
    def _recompute_current_issue():
        from apps.publishing.models import Issue
        current = Issue.objects.select_related('volume').order_by('-volume__year', '-quarter', '-number').first()
        Issue.objects.update(is_current=False)
        if current:
            Issue.objects.filter(pk=current.pk).update(is_current=True)
    """إنشاء عدد جديد."""

    def post(self, request):
        from apps.publishing.models import Volume, Issue
        volume_id = request.POST.get('volume_id')
        number    = request.POST.get('number')
        quarter   = request.POST.get('quarter')

        if not all([volume_id, number, quarter]):
            messages.error(request, 'يرجى إدخال جميع البيانات المطلوبة.')
            return redirect(reverse('dashboard:issues'))

        volume = get_object_or_404(Volume, pk=volume_id)

        try:
            number_int = int(number)
            quarter_int = int(quarter)
            if number_int < 1 or quarter_int not in (1, 2, 3, 4, 5, 6):
                raise ValueError
        except ValueError:
            messages.error(request, 'يرجى إدخال بيانات عدد صحيحة.')
            return redirect(reverse('dashboard:issues'))

        Issue.objects.get_or_create(
            volume=volume,
            number=number_int,
            defaults={'quarter': quarter_int, 'is_current': False},
        )
        self._recompute_current_issue()
        messages.success(request, f'تم إنشاء العدد {number}.')
        
        return redirect(reverse('dashboard:issues'))


class IssueUpdateView(AdminRequiredMixin, View):
    """Update an existing issue."""

    @staticmethod
    def _recompute_current_issue():
        from apps.publishing.models import Issue
        current = Issue.objects.select_related('volume').order_by('-volume__year', '-quarter', '-number').first()
        Issue.objects.update(is_current=False)
        if current:
            Issue.objects.filter(pk=current.pk).update(is_current=True)

    def post(self, request, pk):
        from django.db import IntegrityError
        from apps.publishing.models import Volume, Issue

        issue = get_object_or_404(Issue, pk=pk)
        volume_id = (request.POST.get('volume_id') or '').strip()
        number_raw = (request.POST.get('number') or '').strip()
        quarter_raw = (request.POST.get('quarter') or '').strip()

        try:
            number = int(number_raw)
            quarter = int(quarter_raw)
            if number < 1 or quarter not in (1, 2, 3, 4, 5, 6):
                raise ValueError
        except ValueError:
            messages.error(request, 'يرجى إدخال بيانات عدد صحيحة.')
            return redirect(reverse('dashboard:issues'))

        volume = get_object_or_404(Volume, pk=volume_id)
        issue.volume = volume
        issue.number = number
        issue.quarter = quarter
        issue.is_current = False
        try:
            issue.save(update_fields=['volume', 'number', 'quarter', 'is_current'])
        except IntegrityError:
            messages.error(request, 'يوجد عدد بنفس الرقم داخل هذا المجلد.')
            return redirect(reverse('dashboard:issues'))

        messages.success(request, f'تم تحديث العدد {issue.number}.')
        return redirect(reverse('dashboard:issues'))


class IssueManagementView(AdminRequiredMixin, TemplateView):
    """إدارة المجلدات والأعداد."""
    template_name = 'dashboard/admin/issues.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.publishing.models import Volume, Issue
        current = Issue.objects.select_related('volume').order_by('-volume__year', '-quarter', '-number').first()
        Issue.objects.update(is_current=False)
        if current:
            Issue.objects.filter(pk=current.pk).update(is_current=True)
        ctx['volumes'] = Volume.objects.prefetch_related('issues__articles').order_by('-number')
        ctx['issues']  = Issue.objects.select_related('volume').order_by('-volume__number', '-number')
        return ctx


class AssignArticleToIssueView(AdminRequiredMixin, View):
    """تعيين مقال منشور لعدد محدد."""

    def post(self, request, pk):
        from apps.publishing.models import PublishedArticle, Issue
        article  = get_object_or_404(PublishedArticle, pk=pk)
        issue_id = request.POST.get('issue_id')

        if issue_id:
            issue = get_object_or_404(Issue, pk=issue_id)
            article.issue = issue
            article.save(update_fields=['issue'])
            messages.success(request, f'تم تعيين المقال للعدد {issue}.')
        else:
            article.issue = None
            article.save(update_fields=['issue'])
            messages.success(request, 'تم إلغاء تعيين المقال من العدد.')

        return redirect(reverse('dashboard:issues'))


class AdminPaymentsView(AdminRequiredMixin, ListView):
    """إدارة الدفعات — عرض كل الدفعات مع فلترة حسب الحالة."""
    template_name       = 'dashboard/admin/payments.html'
    context_object_name = 'payments'
    paginate_by         = 20

    def get_queryset(self):
        from apps.payments.models import Payment
        qs = Payment.objects.select_related(
            'submission__author', 'submission__section'
        ).order_by('-created_at')

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.payments.models import Payment
        from django.db.models import Sum

        ctx['status_choices'] = Payment.STATUS_CHOICES
        ctx['current_status'] = self.request.GET.get('status', '')

        # إحصائيات سريعة
        all_payments = Payment.objects.all()
        ctx['stats'] = {
            'total':      all_payments.count(),
            'pending':    all_payments.filter(status=Payment.STATUS_PENDING).count(),
            'processing': all_payments.filter(status=Payment.STATUS_PROCESSING).count(),
            'completed':  all_payments.filter(status=Payment.STATUS_COMPLETED).count(),
            'failed':     all_payments.filter(status=Payment.STATUS_FAILED).count(),
            'expired':    all_payments.filter(status=Payment.STATUS_EXPIRED).count(),
            'total_revenue': all_payments.filter(
                status=Payment.STATUS_COMPLETED
            ).aggregate(total=Sum('amount'))['total'] or 0,
        }
        return ctx


class UserManagementView(AdminRequiredMixin, ListView):
    """إدارة المستخدمين — عرض كل المستخدمين مع فلترة وتعديل الدور والحالة."""
    template_name       = 'dashboard/admin/users.html'
    context_object_name = 'users'
    paginate_by         = 20

    def get_queryset(self):
        from apps.accounts.models import User
        from django.db import models as django_models
        # نجلب فقط الإداريين
        qs = User.objects.filter(role=User.ROLE_ADMIN).order_by('-date_joined')

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                django_models.Q(username__icontains=search) |
                django_models.Q(first_name__icontains=search) |
                django_models.Q(last_name__icontains=search) |
                django_models.Q(email__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.accounts.models import User
        from apps.accounts.forms import AdminCreateUserForm
        
        ctx['role_choices']   = User.ROLE_CHOICES
        ctx['current_search'] = self.request.GET.get('q', '')
        
        # تحديث خيارات النموذج ديناميكياً
        form = ctx.get('create_form')
        if not form:
            form = AdminCreateUserForm()
        ctx['create_form']    = form
        
        return ctx

    def post(self, request):
        from apps.accounts.models import User
        from apps.accounts.forms import AdminCreateUserForm
        action = request.POST.get('action')

        # ─── إنشاء مستخدم جديد ───────────────────────────────────────────
        if action == 'create_user':
            form = AdminCreateUserForm(request.POST)
            if form.is_valid():
                user = form.save()
                messages.success(request, f'تم إنشاء حساب {user.get_full_name() or user.username} بنجاح.')
                referer = request.META.get('HTTP_REFERER')
                if referer:
                    return redirect(referer)
                return redirect(reverse('dashboard:users'))
            # إعادة العرض مع الأخطاء
            self.object_list = self.get_queryset()
            context = self.get_context_data(object_list=self.object_list)
            context['create_form'] = form
            context['show_modal']  = True
            return self.render_to_response(context)

        # ─── تغيير الدور ─────────────────────────────────────────────────
        user_id = request.POST.get('user_id')
        user    = get_object_or_404(User, pk=user_id)

        if user == request.user:
            messages.error(request, 'لا يمكنك تعديل حسابك من هنا.')
            return redirect(reverse('dashboard:users'))

        if action == 'set_role':
            # منع تغيير دور الـ superuser
            if user.is_superuser:
                messages.error(request, 'لا يمكن تغيير دور superuser.')
                return redirect(reverse('dashboard:users'))
            
            new_role = request.POST.get('role')
            if new_role in dict(User.ROLE_CHOICES) and new_role != User.ROLE_AUTHOR:
                user.role = new_role
                user.save(update_fields=['role'])
                if new_role == User.ROLE_REVIEWER:
                    from apps.accounts.models import ReviewerProfile
                    ReviewerProfile.objects.get_or_create(user=user)
                messages.success(request, f'تم تغيير دور {user.get_full_name() or user.username} إلى {user.get_role_display()}.')
            else:
                messages.error(request, 'دور غير صالح.')

        elif action == 'toggle_active':
            # منع تعطيل الـ superuser
            if user.is_superuser:
                messages.error(request, 'لا يمكن تعطيل حساب superuser.')
                return redirect(reverse('dashboard:users'))
            
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            status_text = 'تفعيل' if user.is_active else 'تعطيل'
            messages.success(request, f'تم {status_text} حساب {user.get_full_name() or user.username}.')

        return redirect(reverse('dashboard:users'))


class ReviewerManagementView(AdminRequiredMixin, ListView):
    """إدارة المراجعين — عرض وتعديل بياناتهم وأقسامهم."""
    template_name       = 'dashboard/admin/reviewers.html'
    context_object_name = 'reviewers'
    paginate_by         = 20

    def get_queryset(self):
        from apps.accounts.models import User
        from django.db import models as django_models
        
        qs = User.objects.filter(role=User.ROLE_REVIEWER).select_related(
            'reviewer_profile'
        ).prefetch_related('reviewer_profile__specialties').order_by('-date_joined')

        # 1. Search filter (q)
        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                django_models.Q(username__icontains=search) |
                django_models.Q(first_name__icontains=search) |
                django_models.Q(last_name__icontains=search) |
                django_models.Q(email__icontains=search) |
                django_models.Q(reviewer_profile__institution__icontains=search)
            )

        # 2. Section filter (section)
        section_id = self.request.GET.get('section', '').strip()
        if section_id:
            qs = qs.filter(reviewer_profile__specialties__id=section_id)

        # 3. Availability filter (availability)
        availability = self.request.GET.get('availability', '').strip()
        if availability == 'available':
            qs = qs.filter(reviewer_profile__is_available=True)
        elif availability == 'unavailable':
            qs = qs.filter(reviewer_profile__is_available=False)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.accounts.models import User
        from apps.submissions.models import JournalSection
        from apps.reviews.models import Review
        
        ctx['sections'] = JournalSection.objects.all()
        ctx['current_search'] = self.request.GET.get('q', '')
        ctx['current_section'] = self.request.GET.get('section', '')
        ctx['current_availability'] = self.request.GET.get('availability', '')

        # Active & completed stats per reviewer shown on the current page
        reviewer_stats = {}
        for reviewer in ctx['reviewers']:
            reviewer_stats[reviewer.pk] = {
                'active':    Review.objects.filter(reviewer=reviewer, is_submitted=False).count(),
                'completed': Review.objects.filter(reviewer=reviewer, is_submitted=True).count(),
            }
        ctx['reviewer_stats'] = reviewer_stats

        from apps.accounts.forms import AdminCreateUserForm
        from apps.accounts.models import User
        ctx['role_choices']   = User.ROLE_CHOICES
        ctx['create_form']    = AdminCreateUserForm()

        return ctx

    def post(self, request):
        """تحديث تخصصات مراجع."""
        from apps.accounts.models import User
        from apps.submissions.models import JournalSection
        reviewer_id  = request.POST.get('reviewer_id')
        section_ids  = request.POST.getlist('sections')
        is_available = request.POST.get('is_available') == 'on'

        reviewer = get_object_or_404(User, pk=reviewer_id, role=User.ROLE_REVIEWER)
        try:
            profile = reviewer.reviewer_profile
            profile.specialties.set(JournalSection.objects.filter(pk__in=section_ids))
            profile.is_available = is_available
            profile.save(update_fields=['is_available'])
            messages.success(request, f'تم تحديث بيانات {reviewer.get_full_name() or reviewer.username}.')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')

        # Preserve search and page filters if referrer is available
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect(reverse('dashboard:reviewers'))


class AdminAuthorsView(AdminRequiredMixin, ListView):
    """إدارة المؤلفين — عرض قائمة المؤلفين مع إحصائيات المقالات وإجراءات تفعيل/تعطيل الحساب."""
    template_name       = 'dashboard/admin/authors.html'
    context_object_name = 'authors'
    paginate_by         = 20

    def get_queryset(self):
        from apps.accounts.models import User
        from django.db import models as django_models
        from django.db.models import Count
        
        # نجلب فقط المؤلفين
        qs = User.objects.filter(role=User.ROLE_AUTHOR).order_by('-date_joined')
        
        # البحث بالاسم أو البريد أو اسم المستخدم
        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                django_models.Q(username__icontains=search) |
                django_models.Q(first_name__icontains=search) |
                django_models.Q(last_name__icontains=search) |
                django_models.Q(email__icontains=search)
            )
            
        # نقوم بـ annotation لحساب المقالات الكلية والمنشورة
        qs = qs.annotate(
            total_submissions_count=Count('submissions'),
            published_articles_count=Count('submissions__published')
        )
        return qs
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.accounts.forms import AdminCreateUserForm
        from apps.accounts.models import User
        ctx['current_search'] = self.request.GET.get('q', '')
        ctx['role_choices']   = User.ROLE_CHOICES
        ctx['create_form']    = AdminCreateUserForm()
        return ctx

    def post(self, request):
        """تفعيل/تعطيل حساب المؤلف."""
        from apps.accounts.models import User
        user_id = request.POST.get('user_id')
        user    = get_object_or_404(User, pk=user_id, role=User.ROLE_AUTHOR)
        
        if user == request.user:
            messages.error(request, 'لا يمكنك تعديل حسابك من هنا.')
            return redirect(reverse('dashboard:admin_authors'))
            
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        status_text = 'تفعيل' if user.is_active else 'تعطيل'
        messages.success(request, f'تم {status_text} حساب {user.get_full_name() or user.username}.')
        
        return redirect(reverse('dashboard:admin_authors'))


class AdminImpersonateStartView(SuperUserRequiredMixin, View):
    """السماح للـ superuser فقط بتسجيل الدخول كمستخدم آخر."""

    def post(self, request, pk):
        from apps.accounts.models import User

        target_user = get_object_or_404(User, pk=pk)
        if target_user.pk == request.user.pk:
            messages.error(request, 'لا يمكن تسجيل الدخول بنفس الحساب الحالي.')
            return redirect(reverse('dashboard:users'))

        # احفظ معرف المشرف الأصلي (superuser)
        admin_id = request.user.pk
        
        # قم بتسجيل الدخول كمستخدم آخر
        target_user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, target_user)
        
        # بعد تسجيل الدخول، أعد تعيين impersonator_user_id
        request.session['impersonator_user_id'] = admin_id
        request.session.save()
        
        messages.success(request, f'أنت الآن داخل حساب {target_user.get_full_name() or target_user.username}.')
        return redirect(reverse('dashboard:home'))


class AdminImpersonateStopView(LoginRequiredMixin, View):
    """العودة إلى حساب الـ superuser الأصلي بعد الدخول كمستخدم آخر."""

    def post(self, request):
        from apps.accounts.models import User

        impersonator_id = request.session.get('impersonator_user_id')
        if not impersonator_id:
            messages.error(request, 'لا يوجد وضع دخول كمستخدم نشط.')
            return redirect(reverse('dashboard:home'))

        # تحقق من أن المستخدم الأصلي كان superuser
        admin_user = get_object_or_404(
            User.objects.filter(is_superuser=True, is_active=True),
            pk=impersonator_id
        )
        
        # حذف المفتاح من الـ session أولاً
        request.session.pop('impersonator_user_id', None)
        # حفظ الجلسة قبل تسجيل الدخول
        request.session.save()
        
        # ثم قم بتسجيل الدخول كـ superuser
        admin_user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, admin_user)
        
        messages.success(request, 'تمت العودة إلى حسابك.')
        return redirect(reverse('dashboard:users'))


class AdminSectionManagementView(AdminRequiredMixin, ListView):
    """إدارة التصنيفات/الأقسام — عرضها وإضافتها."""
    template_name       = 'dashboard/admin/sections.html'
    context_object_name = 'sections'

    def get_queryset(self):
        from django.db.models import Count
        from apps.submissions.models import JournalSection
        return JournalSection.objects.annotate(
            articles_count=Count('publishedarticle')
        ).order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.dashboard.forms import JournalSectionForm
        ctx['form'] = ctx.get('form', JournalSectionForm())
        return ctx

    def post(self, request):
        from apps.dashboard.forms import JournalSectionForm
        form = JournalSectionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة التصنيف الجديد بنجاح.')
            return redirect(reverse('dashboard:sections'))
        
        self.object_list = self.get_queryset()
        context = self.get_context_data(object_list=self.object_list)
        context['form'] = form
        context['show_modal'] = True
        return self.render_to_response(context)


class AdminSectionUpdateView(AdminRequiredMixin, View):
    """تعديل بيانات تصنيف."""
    def get(self, request, pk):
        from apps.submissions.models import JournalSection
        from apps.dashboard.forms import JournalSectionForm
        section = get_object_or_404(JournalSection, pk=pk)
        form = JournalSectionForm(instance=section)
        return render(request, 'dashboard/admin/section_form.html', {'form': form, 'section': section})

    def post(self, request, pk):
        from apps.submissions.models import JournalSection
        from apps.dashboard.forms import JournalSectionForm
        section = get_object_or_404(JournalSection, pk=pk)
        form = JournalSectionForm(request.POST, instance=section)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات التصنيف بنجاح.')
            return redirect(reverse('dashboard:sections'))
        return render(request, 'dashboard/admin/section_form.html', {'form': form, 'section': section})


class AdminSectionDeleteView(AdminRequiredMixin, View):
    """حذف تصنيف."""
    def post(self, request, pk):
        from apps.submissions.models import JournalSection
        section = get_object_or_404(JournalSection, pk=pk)
        if section.publishedarticle_set.exists() or section.articlesubmission_set.exists():
            messages.error(request, 'لا يمكن حذف هذا التصنيف لأنه يحتوي على مقالات أو تقديمات مرتبطة به.')
        else:
            section.delete()
            messages.success(request, 'تم حذف التصنيف بنجاح.')
        return redirect(reverse('dashboard:sections'))


class AdminTagManagementView(AdminRequiredMixin, ListView):
    """إدارة الوسوم/الكلمات المفتاحية — عرضها وإضافتها."""
    template_name       = 'dashboard/admin/tags.html'
    context_object_name = 'tags'
    paginate_by         = 30

    def get_queryset(self):
        from django.db.models import Count
        from taggit.models import Tag
        return Tag.objects.annotate(
            articles_count=Count('articlesubmission__published')
        ).order_by('-articles_count', 'name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.dashboard.forms import TagForm
        ctx['form'] = ctx.get('form', TagForm())
        return ctx

    def post(self, request):
        from apps.dashboard.forms import TagForm
        form = TagForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة الوسم الجديد بنجاح.')
            return redirect(reverse('dashboard:tags'))
        
        self.object_list = self.get_queryset()
        context = self.get_context_data(object_list=self.object_list)
        context['form'] = form
        context['show_modal'] = True
        return self.render_to_response(context)


class AdminTagUpdateView(AdminRequiredMixin, View):
    """تعديل بيانات وسم."""
    def get(self, request, pk):
        from taggit.models import Tag
        from apps.dashboard.forms import TagForm
        tag = get_object_or_404(Tag, pk=pk)
        form = TagForm(instance=tag)
        return render(request, 'dashboard/admin/tag_form.html', {'form': form, 'tag': tag})

    def post(self, request, pk):
        from taggit.models import Tag
        from apps.dashboard.forms import TagForm
        tag = get_object_or_404(Tag, pk=pk)
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات الوسم بنجاح.')
            return redirect(reverse('dashboard:tags'))
        return render(request, 'dashboard/admin/tag_form.html', {'form': form, 'tag': tag})


class AdminTagDeleteView(AdminRequiredMixin, View):
    """حذف وسم."""
    def post(self, request, pk):
        from taggit.models import Tag
        tag = get_object_or_404(Tag, pk=pk)
        tag.delete()
        messages.success(request, 'تم حذف الوسم بنجاح.')
        return redirect(reverse('dashboard:tags'))


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

from apps.accounts.mixins import AuthorRequiredMixin, ReviewerRequiredMixin, AdminRequiredMixin
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
        return ArticleSubmission.objects.filter(
            author=self.request.user
        ).select_related('section').prefetch_related(
            'manuscript_files', 'reviews', 'co_authors'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx['total']     = qs.count()
        ctx['drafts']    = qs.filter(status='draft').count()
        ctx['active']    = qs.exclude(status__in=['draft', 'published', 'rejected', 'expired']).count()
        ctx['published'] = qs.filter(status='published').count()
        return ctx


class ReviewerDashboardView(ReviewerRequiredMixin, ListView):
    """لوحة تحكم المراجع — مخطوطات مصنّفة: جديدة، قيد المراجعة، مكتملة."""
    template_name       = 'dashboard/reviewer/index.html'
    context_object_name = 'reviews'

    def get_queryset(self):
        from apps.reviews.models import Review
        return Review.objects.filter(
            reviewer=self.request.user
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
        ).exclude(status=SubmissionStatus.PUBLISHED).order_by('-created_at')

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
        base_qs = base_qs.exclude(status=SubmissionStatus.PUBLISHED)
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
        return render(request, self.template_name, {'submission': submission})

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        action = request.POST.get('action')
        from apps.submissions.services import SubmissionService
        from apps.submissions.exceptions import InvalidStateTransitionError

        if action == 'pass':
            try:
                SubmissionService.admin_pass_initial_check(submission, actor=request.user)
                messages.success(request, 'تم قبول التقديم للمراجعة.')
            except InvalidStateTransitionError as e:
                messages.error(request, f'خطأ: {e}')

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
    """إنشاء عدد جديد."""

    def post(self, request):
        from apps.publishing.models import Volume, Issue
        volume_id = request.POST.get('volume_id')
        number    = request.POST.get('number')
        quarter   = request.POST.get('quarter')
        is_current = request.POST.get('is_current') == 'on'

        if not all([volume_id, number, quarter]):
            messages.error(request, 'يرجى إدخال جميع البيانات المطلوبة.')
            return redirect(reverse('dashboard:issues'))

        volume = get_object_or_404(Volume, pk=volume_id)

        if is_current:
            Issue.objects.filter(is_current=True).update(is_current=False)

        Issue.objects.get_or_create(
            volume=volume,
            number=number,
            defaults={'quarter': quarter, 'is_current': is_current},
        )
        messages.success(request, f'تم إنشاء العدد {number}.')
        return redirect(reverse('dashboard:issues'))


class IssueUpdateView(AdminRequiredMixin, View):
    """Update an existing issue."""

    def post(self, request, pk):
        from django.db import IntegrityError
        from apps.publishing.models import Volume, Issue

        issue = get_object_or_404(Issue, pk=pk)
        volume_id = (request.POST.get('volume_id') or '').strip()
        number_raw = (request.POST.get('number') or '').strip()
        quarter_raw = (request.POST.get('quarter') or '').strip()
        is_current = request.POST.get('is_current') == 'on'

        try:
            number = int(number_raw)
            quarter = int(quarter_raw)
            if number < 1 or quarter not in (1, 2, 3, 4):
                raise ValueError
        except ValueError:
            messages.error(request, 'يرجى إدخال بيانات عدد صحيحة.')
            return redirect(reverse('dashboard:issues'))

        volume = get_object_or_404(Volume, pk=volume_id)
        if is_current:
            Issue.objects.exclude(pk=issue.pk).filter(is_current=True).update(is_current=False)

        issue.volume = volume
        issue.number = number
        issue.quarter = quarter
        issue.is_current = is_current
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
        qs = User.objects.order_by('-date_joined')

        role   = self.request.GET.get('role')
        search = self.request.GET.get('q', '').strip()

        if role:
            qs = qs.filter(role=role)
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
        ctx['current_role']   = self.request.GET.get('role', '')
        ctx['current_search'] = self.request.GET.get('q', '')
        ctx['create_form']    = ctx.get('create_form', AdminCreateUserForm())
        ctx['stats'] = {
            'total':     User.objects.count(),
            'authors':   User.objects.filter(role=User.ROLE_AUTHOR).count(),
            'reviewers': User.objects.filter(role=User.ROLE_REVIEWER).count(),
            'admins':    User.objects.filter(role=User.ROLE_ADMIN).count(),
            'active':    User.objects.filter(is_active=True).count(),
            'inactive':  User.objects.filter(is_active=False).count(),
        }
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
                return redirect(reverse('dashboard:users'))
            # إعادة العرض مع الأخطاء
            context = self.get_context_data(object_list=self.get_queryset())
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
            new_role = request.POST.get('role')
            if new_role in dict(User.ROLE_CHOICES):
                user.role = new_role
                user.save(update_fields=['role'])
                if new_role == User.ROLE_REVIEWER:
                    from apps.accounts.models import ReviewerProfile
                    ReviewerProfile.objects.get_or_create(user=user)
                messages.success(request, f'تم تغيير دور {user.get_full_name() or user.username} إلى {user.get_role_display()}.')
            else:
                messages.error(request, 'دور غير صالح.')

        elif action == 'toggle_active':
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            status_text = 'تفعيل' if user.is_active else 'تعطيل'
            messages.success(request, f'تم {status_text} حساب {user.get_full_name() or user.username}.')

        return redirect(reverse('dashboard:users'))


class ReviewerManagementView(AdminRequiredMixin, ListView):
    """إدارة المراجعين — عرض وتعديل بياناتهم وأقسامهم."""
    template_name       = 'dashboard/admin/reviewers.html'
    context_object_name = 'reviewers'

    def get_queryset(self):
        from apps.accounts.models import User
        return User.objects.filter(role=User.ROLE_REVIEWER).select_related(
            'reviewer_profile'
        ).prefetch_related('reviewer_profile__specialties')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.submissions.models import JournalSection
        from apps.reviews.models import Review
        ctx['sections'] = JournalSection.objects.all()
        reviewer_stats = {}
        for reviewer in ctx['reviewers']:
            reviewer_stats[reviewer.pk] = {
                'active':    Review.objects.filter(reviewer=reviewer, is_submitted=False).count(),
                'completed': Review.objects.filter(reviewer=reviewer, is_submitted=True).count(),
            }
        ctx['reviewer_stats'] = reviewer_stats
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

        return redirect(reverse('dashboard:reviewers'))


class AdminImpersonateStartView(AdminRequiredMixin, View):
    """Allow admins to log in as another user from the dashboard."""

    def post(self, request, pk):
        from apps.accounts.models import User

        target_user = get_object_or_404(User, pk=pk)
        if target_user.pk == request.user.pk:
            messages.error(request, 'لا يمكن تسجيل الدخول بنفس الحساب الحالي.')
            return redirect(reverse('dashboard:users'))

        if not request.session.get('impersonator_user_id'):
            request.session['impersonator_user_id'] = request.user.pk

        target_user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, target_user)
        messages.success(request, f'أنت الآن داخل حساب {target_user.get_full_name() or target_user.username}.')
        return redirect(reverse('dashboard:home'))


class AdminImpersonateStopView(LoginRequiredMixin, View):
    """Return to the original admin account after impersonation."""

    def post(self, request):
        from apps.accounts.models import User

        impersonator_id = request.session.get('impersonator_user_id')
        if not impersonator_id:
            messages.error(request, 'لا يوجد وضع دخول كمستخدم نشط.')
            return redirect(reverse('dashboard:home'))

        admin_user = get_object_or_404(
            User.objects.filter(role=User.ROLE_ADMIN, is_active=True),
            pk=impersonator_id
        )
        admin_user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, admin_user)
        request.session.pop('impersonator_user_id', None)
        messages.success(request, 'تمت العودة إلى حساب المشرف.')
        return redirect(reverse('dashboard:users'))

from django.views.generic import CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse_lazy, reverse

from apps.accounts.mixins import AuthorRequiredMixin
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.forms import SubmissionForm, CoAuthorFormSet, ManuscriptUploadForm
from apps.submissions.services import SubmissionService
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
    InvalidManuscriptFileError,
)


class SubmissionCreateView(AuthorRequiredMixin, CreateView):
    """إنشاء تقديم جديد — يُحفظ كمسودة."""
    model         = ArticleSubmission
    form_class    = SubmissionForm
    template_name = 'submissions/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['coauthor_formset'] = CoAuthorFormSet(self.request.POST)
        else:
            ctx['coauthor_formset'] = CoAuthorFormSet()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        coauthor_formset = ctx['coauthor_formset']

        form.instance.author = self.request.user
        form.instance.status = ArticleSubmission.STATUS_DRAFT
        self.object = form.save()

        # حفظ ملف المخطوطة إذا رُفع
        manuscript = self.request.FILES.get('manuscript')
        if manuscript:
            if not manuscript.name.lower().endswith('.pdf'):
                messages.error(self.request, 'يجب أن يكون الملف بصيغة PDF.')
                self.object.delete()
                return self.form_invalid(form)
            ManuscriptFile.objects.create(
                submission=self.object,
                file=manuscript,
                version=1,
                is_current=True,
            )

        if coauthor_formset.is_valid():
            coauthor_formset.instance = self.object
            coauthor_formset.save()

        messages.success(self.request, 'تم حفظ التقديم كمسودة.')
        return redirect(reverse('submissions:edit', kwargs={'pk': self.object.pk}))

    def form_invalid(self, form):
        messages.error(self.request, 'يرجى تصحيح الأخطاء أدناه.')
        return super().form_invalid(form)


class SubmissionUpdateView(AuthorRequiredMixin, UpdateView):
    """تعديل مسودة — object-level permission."""
    model         = ArticleSubmission
    form_class    = SubmissionForm
    template_name = 'submissions/edit.html'

    def get_object(self, queryset=None):
        obj = get_object_or_404(ArticleSubmission, pk=self.kwargs['pk'])
        if obj.author != self.request.user:
            raise PermissionDenied
        if obj.status != ArticleSubmission.STATUS_DRAFT:
            messages.error(self.request, 'لا يمكن تعديل تقديم بعد إرساله.')
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['coauthor_formset'] = CoAuthorFormSet(
                self.request.POST, instance=self.object
            )
        else:
            ctx['coauthor_formset'] = CoAuthorFormSet(instance=self.object)
        ctx['current_manuscript'] = self.object.manuscript_files.filter(
            is_current=True
        ).first()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        coauthor_formset = ctx['coauthor_formset']
        self.object = form.save()

        # رفع ملف جديد إذا وُجد
        manuscript = self.request.FILES.get('manuscript')
        if manuscript:
            if not manuscript.name.lower().endswith('.pdf'):
                messages.error(self.request, 'يجب أن يكون الملف بصيغة PDF.')
                return self.form_invalid(form)
            # إلغاء النسخة الحالية وإنشاء نسخة جديدة
            ManuscriptFile.objects.filter(
                submission=self.object, is_current=True
            ).update(is_current=False)
            last_version = self.object.manuscript_files.count()
            ManuscriptFile.objects.create(
                submission=self.object,
                file=manuscript,
                version=last_version + 1,
                is_current=True,
            )

        if coauthor_formset.is_valid():
            coauthor_formset.instance = self.object
            coauthor_formset.save()

        messages.success(self.request, 'تم حفظ التعديلات.')
        return redirect(reverse('submissions:edit', kwargs={'pk': self.object.pk}))


class SubmissionSubmitView(AuthorRequiredMixin, View):
    """إرسال التقديم رسمياً — Draft → Under Initial Check."""

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        # التحقق من وجود ملف مخطوطة
        if not submission.manuscript_files.filter(is_current=True).exists():
            messages.error(request, 'يجب رفع ملف المخطوطة قبل الإرسال.')
            return redirect(reverse('submissions:edit', kwargs={'pk': pk}))

        try:
            SubmissionService.submit(submission, actor=request.user)
            messages.success(request, 'تم إرسال مقالتك بنجاح. سيتم مراجعته من قِبَل المشرف.')
        except InvalidStateTransitionError as e:
            messages.error(request, f'لا يمكن إرسال التقديم: {e}')

        return redirect(reverse('dashboard:author'))


class RevisionUploadView(AuthorRequiredMixin, View):
    """رفع نسخة معدّلة — Revision Required → Under Review."""
    template_name = 'submissions/revise.html'

    def get(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied
        from django.shortcuts import render
        return render(request, self.template_name, {
            'submission': submission,
            'form': ManuscriptUploadForm(),
        })

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        form = ManuscriptUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            from django.shortcuts import render
            return render(request, self.template_name, {
                'submission': submission,
                'form': form,
            })

        try:
            SubmissionService.upload_revision(
                submission,
                file=form.cleaned_data['manuscript'],
                actor=request.user,
            )
            messages.success(request, 'تم رفع النسخة المعدّلة بنجاح. سيتم إعادة المراجعة.')
        except InvalidStateTransitionError as e:
            messages.error(request, f'خطأ: {e}')
        except RevisionLimitExceededError:
            messages.error(request, 'تجاوزت الحد الأقصى لدورات التعديل (دورتان).')
        except InvalidManuscriptFileError:
            messages.error(request, 'يجب أن يكون الملف بصيغة PDF.')

        return redirect(reverse('dashboard:author'))

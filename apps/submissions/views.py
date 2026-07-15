from django.views.generic import CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse_lazy, reverse

from apps.accounts.mixins import AuthorRequiredMixin
from apps.submissions.models import ArticleSubmission, ManuscriptFile
from apps.submissions.statuses import SubmissionStatus
from apps.submissions.forms import SubmissionForm, CoAuthorFormSet, ManuscriptUploadForm
from apps.submissions.services import SubmissionService
from apps.submissions.exceptions import (
    InvalidStateTransitionError,
    RevisionLimitExceededError,
    InvalidManuscriptFileError,
)

def _t(ar_text, en_text):
    from django.utils import translation
    return en_text if translation.get_language() == 'en' else ar_text


class SubmissionCreateView(AuthorRequiredMixin, CreateView):
    """إنشاء تقديم جديد — يُحفظ كمسودة."""
    model         = ArticleSubmission
    form_class    = SubmissionForm
    template_name = 'submissions/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['coauthor_formset'] = CoAuthorFormSet(self.request.POST)
        else:
            ctx['coauthor_formset'] = CoAuthorFormSet()
            # ملء بيانات المؤلف الأول من المستخدم
            user = self.request.user
            if ctx['coauthor_formset'].forms:
                first_form = ctx['coauthor_formset'].forms[0]
                first_form.fields['full_name'].initial = user.get_full_name() or user.username
                # محاولة الحصول على المؤسسة من AuthorProfile إن وجدت
                if hasattr(user, 'author_profile'):
                    first_form.fields['institution'].initial = user.author_profile.institution
        ctx['is_create'] = True
        ctx['is_edit'] = False
        ctx['current_manuscript'] = None
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
                messages.error(self.request, _t('يجب أن يكون الملف بصيغة PDF.', 'The file must be in PDF format.'))
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

        # التحقق من نوع الإجراء (حفظ أو تقديم)
        action = self.request.POST.get('action', 'save')
        if action == 'submit':
            # تقديم مباشر إذا كان هناك ملف
            if ManuscriptFile.objects.filter(submission=self.object, is_current=True).exists():
                try:
                    SubmissionService.submit(self.object, actor=self.request.user)
                    messages.success(self.request, _t('تم إرسال مقالتك بنجاح. سيتم مراجعته من قِبَل المشرف.', 'Your article has been submitted successfully. It will be reviewed by the admin.'))
                    return redirect(reverse('dashboard:author'))
                except InvalidStateTransitionError as e:
                    messages.error(self.request, _t(f'خطأ: {e}', f'Error: {e}'))
            else:
                messages.error(self.request, _t('يجب رفع ملف المخطوطة قبل الإرسال.', 'The manuscript file must be uploaded before submitting.'))
        else:
            messages.success(self.request, _t('تم حفظ التقديم كمسودة.', 'Submission saved as draft.'))

        return redirect(reverse('submissions:edit', kwargs={'pk': self.object.pk}))

    def form_invalid(self, form):
        messages.error(self.request, _t('يرجى تصحيح الأخطاء أدناه.', 'Please correct the errors below.'))
        return super().form_invalid(form)


class SubmissionUpdateView(AuthorRequiredMixin, UpdateView):
    """تعديل مسودة — object-level permission."""
    model         = ArticleSubmission
    form_class    = SubmissionForm
    template_name = 'submissions/form.html'

    def get_object(self, queryset=None):
        obj = get_object_or_404(ArticleSubmission, pk=self.kwargs['pk'])
        if obj.author != self.request.user:
            raise PermissionDenied
        if obj.status != ArticleSubmission.STATUS_DRAFT:
            messages.error(self.request, _t('لا يمكن تعديل تقديم بعد إرساله.', 'A submission cannot be edited after it has been submitted.'))
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
        ctx['is_create'] = False
        ctx['is_edit'] = True
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        coauthor_formset = ctx['coauthor_formset']
        self.object = form.save()

        # رفع ملف جديد إذا وُجد
        manuscript = self.request.FILES.get('manuscript')
        if manuscript:
            if not manuscript.name.lower().endswith('.pdf'):
                messages.error(self.request, _t('يجب أن يكون الملف بصيغة PDF.', 'The file must be in PDF format.'))
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

        # التحقق من نوع الإجراء (حفظ أو تقديم)
        action = self.request.POST.get('action', 'save')
        if action == 'submit':
            # تقديم مباشر
            if ManuscriptFile.objects.filter(submission=self.object, is_current=True).exists():
                try:
                    SubmissionService.submit(self.object, actor=self.request.user)
                    messages.success(self.request, _t('تم إرسال مقالتك بنجاح. سيتم مراجعته من قِبَل المشرف.', 'Your article has been submitted successfully. It will be reviewed by the admin.'))
                    return redirect(reverse('dashboard:author'))
                except InvalidStateTransitionError as e:
                    messages.error(self.request, _t(f'خطأ: {e}', f'Error: {e}'))
            else:
                messages.error(self.request, _t('يجب رفع ملف المخطوطة قبل الإرسال.', 'The manuscript file must be uploaded before submitting.'))
                return self.form_invalid(form)
        else:
            messages.success(self.request, _t('تم حفظ التعديلات.', 'Changes saved.'))

        return redirect(reverse('submissions:edit', kwargs={'pk': self.object.pk}))


class SubmissionSubmitView(AuthorRequiredMixin, View):
    """إرسال التقديم رسمياً — Draft → Under Initial Check."""

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        # التحقق من وجود ملف مخطوطة
        if not submission.manuscript_files.filter(is_current=True).exists():
            messages.error(request, _t('يجب رفع ملف المخطوطة قبل الإرسال.', 'The manuscript file must be uploaded before submitting.'))
            return redirect(reverse('submissions:edit', kwargs={'pk': pk}))

        try:
            SubmissionService.submit(submission, actor=request.user)
            messages.success(request, _t('تم إرسال مقالتك بنجاح. سيتم مراجعته من قِبَل المشرف.', 'Your article has been submitted successfully. It will be reviewed by the admin.'))
        except InvalidStateTransitionError as e:
            messages.error(request, _t(f'لا يمكن إرسال التقديم: {e}', f'Cannot submit: {e}'))

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
            messages.success(request, _t('تم رفع النسخة المعدّلة بنجاح. سيتم إعادة المراجعة.', 'Revised version uploaded successfully. It will be reviewed again.'))
        except InvalidStateTransitionError as e:
            messages.error(request, _t(f'خطأ: {e}', f'Error: {e}'))
        except RevisionLimitExceededError:
            messages.error(request, _t('تجاوزت الحد الأقصى لدورات التعديل (دورتان).', 'You have exceeded the maximum number of revision rounds (2 rounds).'))
        except InvalidManuscriptFileError:
            messages.error(request, _t('يجب أن يكون الملف بصيغة PDF.', 'The file must be in PDF format.'))

        return redirect(reverse('dashboard:author'))


class SubmissionWithdrawView(AuthorRequiredMixin, View):
    """سحب التقديم — Under Initial Check → Withdrawn."""

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        try:
            SubmissionService.withdraw(submission, actor=request.user)
            messages.success(request, _t('تم سحب مقالتك بنجاح.', 'Your article has been successfully withdrawn.'))
        except InvalidStateTransitionError as e:
            messages.error(request, _t(f'لا يمكن سحب التقديم: {e}', f'Cannot withdraw submission: {e}'))

        return redirect(reverse('dashboard:author'))


class SubmissionArchiveView(AuthorRequiredMixin, View):
    """إخفاء التقديم من قائمة المؤلف الرئيسية بعد الرفض أو السحب."""

    allowed_statuses = {
        SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN,
    }

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        if submission.status not in self.allowed_statuses:
            messages.error(request, _t('يمكن أرشفة التقديمات المرفوضة أو المسحوبة فقط.', 'Only rejected or withdrawn submissions can be archived.'))
            return redirect(reverse('dashboard:author'))

        submission.is_archived = True
        submission.save(update_fields=['is_archived', 'updated_at'])
        messages.success(request, _t('تم إرسال التقديم إلى الأرشيف.', 'Submission has been archived.'))
        return redirect(reverse('dashboard:author'))


class SubmissionUnarchiveView(AuthorRequiredMixin, View):
    """إرجاع التقديم المؤرشف إلى قائمة المؤلف الرئيسية."""

    def post(self, request, pk):
        submission = get_object_or_404(ArticleSubmission, pk=pk)
        if submission.author != request.user:
            raise PermissionDenied

        submission.is_archived = False
        submission.save(update_fields=['is_archived', 'updated_at'])
        messages.success(request, _t('تمت إزالة التقديم من الأرشيف.', 'Submission has been unarchived.'))
        return redirect(reverse('dashboard:author_archive'))

# مراجعة مشاكل النظام

هذا الملف يلخص المشاكل الحرجة والنقاط التي تحتاج تعديلا في مشروع المجلة العلمية، بناء على مراجعة الكود الحالية.

## مشاكل حرجة

### 1. إعدادات الإنتاج غير آمنة

- الملف: `Journal/settings.py`
- السطور المهمة: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- المشكلة:
  - `SECRET_KEY` مكتوب مباشرة داخل الكود.
  - `DEBUG = True`.
  - `ALLOWED_HOSTS = []`.
- الخطورة:
  - كشف تفاصيل أخطاء حساسة في الإنتاج.
  - تعريض الجلسات والتوقيعات للخطر إذا تم نشر نفس المفتاح.
  - إعدادات غير مناسبة لأي بيئة عامة.
- المطلوب:
  - نقل `SECRET_KEY` إلى environment variable.
  - جعل `DEBUG` يعتمد على متغير بيئة ويكون `False` في الإنتاج.
  - ضبط `ALLOWED_HOSTS` بالدومينات الفعلية.
  - إضافة إعدادات أمان مثل `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

### 2. بوابة الدفع التجريبية مفعلة داخل التطبيق

- الملفات:
  - `apps/payments/views.py`
  - `apps/payments/urls.py`
- المشكلة:
  - النظام يستخدم `MockPaymentGatewayAdapter` كـ gateway فعلي.
  - مسار `payments/mock/pay/<order_id>/` متاح.
  - صفحة الدفع التجريبية تسمح بمحاكاة نجاح أو فشل الدفع.
- الخطورة:
  - أي شخص يعرف `order_id` قد يحاول محاكاة عملية دفع.
  - لا يصلح إطلاقا للإنتاج.
- المطلوب:
  - تعطيل mock routes خارج بيئة التطوير.
  - اختيار بوابة الدفع من الإعدادات.
  - استخدام مزود دفع حقيقي في الإنتاج.

### 3. مفتاح توقيع الدفع hardcoded

- الملف: `apps/payments/adapters.py`
- المشكلة:
  - `SECRET_KEY = 'mock-secret-key-for-testing'` موجود داخل الكود.
- الخطورة:
  - webhook يعتمد على signature، لكن السر معروف وموجود في المستودع.
- المطلوب:
  - نقل مفاتيح الدفع إلى environment variables.
  - منع تشغيل mock gateway في الإنتاج.
  - تدوير أي أسرار تم نشرها أو مشاركتها.

### 4. تسريب بيانات التقديمات للمراجعين

- الملفات:
  - `apps/dashboard/views.py`
  - `templates/dashboard/admin/submission_detail.html`
- المشكلة:
  - `ReviewerSubmissionDetailView` يسمح للمراجع بفتح تقديمات غير معينة له في حالات معينة، منها:
    - `under_initial_check`
    - `under_review` بدون مراجع
    - `accepted_awaiting_payment` بدون مراجع
  - نفس template يعرض:
    - ملفات المخطوطة.
    - معلومات الدفع.
    - رقم طلب الدفع.
    - بيانات المراجعات.
- الخطورة:
  - مراجع غير مكلف قد يرى ملفات أو بيانات دفع لا تخصه.
  - هذا يعتبر خللا في صلاحيات الوصول.
- المطلوب:
  - حصر عرض التفاصيل للمراجع المكلف فقط.
  - فصل template المراجع عن template المشرف.
  - إخفاء معلومات الدفع والمراجعات غير المصرح بها عن المراجع.

### 5. ملفات المخطوطات متاحة بروابط media مباشرة

- الملف: `templates/dashboard/admin/submission_detail.html`
- المشكلة:
  - رابط التحميل يستخدم `{{ mf.file.url }}` مباشرة.
- الخطورة:
  - إذا كانت ملفات media عامة في الإنتاج، يمكن فتح الملف خارج صلاحيات Django بمجرد معرفة الرابط.
- المطلوب:
  - إنشاء protected download view.
  - التحقق من أن المستخدم هو:
    - المؤلف صاحب التقديم.
    - المراجع المكلف.
    - المشرف.
  - إرسال الملف عبر view محمي بدلا من رابط media مباشر.

### 6. تحقق رفع الملفات ضعيف وغير موحد

- الملفات:
  - `apps/submissions/views.py`
  - `apps/submissions/forms.py`
  - `apps/submissions/services.py`
- المشكلة:
  - في إنشاء وتعديل التقديم يتم التحقق من الامتداد `.pdf` فقط.
  - حد الحجم 20MB موجود في `ManuscriptUploadForm` فقط وليس في كل مسارات الرفع.
  - لا يوجد تحقق من MIME type أو محتوى الملف.
- الخطورة:
  - رفع ملفات غير PDF بامتداد مزيف.
  - رفع ملفات ضخمة في بعض المسارات.
- المطلوب:
  - توحيد validation في مكان واحد.
  - التحقق من الحجم.
  - التحقق من MIME type.
  - التحقق من magic bytes للـ PDF.

## مشاكل تحتاج تعديل قريب

### 7. `gateway_order_id` غير unique ومسموح أن يكون فارغا

- الملفات:
  - `apps/payments/models.py`
  - `apps/payments/services.py`
- المشكلة:
  - `gateway_order_id` عليه index فقط وليس unique.
  - webhook يبحث بـ `get(gateway_order_id=data.external_order_id)`.
  - إذا كان order id فارغا أو مكررا قد يحدث خطأ أو معالجة خاطئة.
- المطلوب:
  - منع webhook payload بدون order id.
  - جعل order id فريدا عند وجوده.
  - التعامل صراحة مع `MultipleObjectsReturned`.

### 8. حفظ التقديم يحدث قبل التأكد من صحة coauthor formset

- الملف: `apps/submissions/views.py`
- المشكلة:
  - يتم حفظ المقال والملف أولا.
  - إذا كان `coauthor_formset` غير صالح يتم تجاهله بدون إظهار خطأ.
- الخطورة:
  - بيانات جزئية أو غير متوقعة.
  - تجربة مستخدم مربكة.
- المطلوب:
  - التحقق من form و formset قبل أي حفظ.
  - استخدام `transaction.atomic()`.
  - إرجاع أخطاء formset للمستخدم.

### 9. سباق محتمل في رفع النسخ المعدلة

- الملف: `apps/submissions/services.py`
- المشكلة:
  - يتم فحص status و revision limit قبل الدخول إلى transaction وقبل `select_for_update`.
- الخطورة:
  - في طلبين متزامنين قد يتم تجاوز حد المراجعات أو إنشاء نسخ غير متوقعة.
- المطلوب:
  - إعادة فحص status و revision count داخل transaction بعد lock.

### 10. GET request يغير قاعدة البيانات

- الملف: `apps/dashboard/views.py`
- المشكلة:
  - `IssueManagementView.get_context_data()` يقوم بتحديث `Issue.objects.update(is_current=False)`.
- الخطورة:
  - GET يجب أن يكون read-only.
  - قد يسبب side effects غير متوقعة عند مجرد فتح الصفحة.
- المطلوب:
  - نقل إعادة حساب العدد الحالي إلى service أو command.
  - تنفيذها فقط عند إنشاء أو تعديل issue.

### 11. صلاحيات الإدارة واسعة جدا

- الملفات:
  - `apps/accounts/mixins.py`
  - `apps/dashboard/views.py`
- المشكلة:
  - `AdminRequiredMixin` يعتمد على `role == 'admin'`.
  - أي admin يستطيع تعديل أدوار المستخدمين وإنشاء مستخدمين بأدوار حساسة.
- الخطورة:
  - تصعيد صلاحيات داخلي غير مضبوط.
- المطلوب:
  - استخدام Django permissions أو التفريق بين admin و superuser.
  - منع إنشاء أو ترقية admin إلا بواسطة superuser.

### 12. Impersonation بلا audit log كاف

- الملف: `apps/dashboard/views.py`
- المشكلة:
  - superuser يستطيع الدخول كمستخدم آخر.
  - لا يوجد سجل تدقيق واضح لبدء/إنهاء impersonation.
  - لا توجد قيود كافية على المستخدم الهدف.
- الخطورة:
  - صعوبة تتبع العمليات التي تمت أثناء impersonation.
- المطلوب:
  - تسجيل audit log عند البداية والنهاية.
  - منع impersonating superusers أو inactive users.
  - إظهار banner واضح أثناء impersonation.

### 13. Slug المقالات العربية غير مناسب

- الملف: `apps/publishing/models.py`
- المشكلة:
  - استخدام `slugify` الافتراضي مع العناوين العربية غالبا ينتج `article`, `article-2`, وهكذا.
- الخطورة:
  - روابط ضعيفة وغير معبرة.
  - تكرارات كثيرة.
- المطلوب:
  - استخدام `slugify(..., allow_unicode=True)` أو transliteration مناسب.

### 14. عداد المشاهدات غير آمن للطلبات المتزامنة

- الملف: `apps/pages/views.py`
- المشكلة:
  - التحديث يتم بهذه الطريقة: `views_count=obj.views_count + 1`.
- الخطورة:
  - فقدان بعض الزيادات مع الطلبات المتزامنة.
- المطلوب:
  - استخدام `F('views_count') + 1`.

### 15. أوامر تذكير الدفع مكررة

- الملفات:
  - `apps/payments/management/commands/expire_payments.py`
  - `apps/submissions/management/commands/send_payment_reminders.py`
- المشكلة:
  - يوجد أكثر من command يرسل تذكيرات دفع.
- الخطورة:
  - احتمال إرسال تذكيرات مكررة.
- المطلوب:
  - توحيد منطق التذكير في service واحد.
  - استخدام command واحد أو ضمان idempotency.

## ملاحظات جودة وتجربة مستخدم

### 16. إعادة استخدام template إداري لأدوار مختلفة

- الملف: `templates/dashboard/admin/submission_detail.html`
- المشكلة:
  - نفس الصفحة تستخدم للمؤلف والمراجع والمشرف.
- الأثر:
  - صعوبة ضبط الصلاحيات.
  - تسريب محتمل لعناصر خاصة بالإدارة.
- المطلوب:
  - فصل صفحات التفاصيل حسب الدور أو التحكم الصريح في كل جزء مع tests.

### 17. عدم وجود tests كافية لصلاحيات views

- الموجود:
  - اختبارات جيدة نسبيا للـ services.
- الناقص:
  - اختبارات وصول للمؤلف والمراجع والمشرف.
  - اختبارات منع المراجع غير المكلف من رؤية ملفات أو دفع.
  - اختبارات mock payment route.
- المطلوب:
  - إضافة tests على مستوى views والـ templates الحساسة.

## ملاحظات التحقق

- تمت محاولة تشغيل الاختبارات، لكن البيئة الحالية لا تحتوي Python قابل للتشغيل:
  - `py -m pytest -q` أعاد: `No installed Python found`
  - `python -m pytest -q` فشل بسبب عدم إمكانية الوصول إلى `python.exe`
- لذلك هذه المراجعة مبنية على فحص static للكود وليست نتيجة تشغيل الاختبارات.

## أولويات الإصلاح المقترحة

1. إغلاق إعدادات الإنتاج غير الآمنة.
2. تعطيل mock payment routes خارج التطوير.
3. حماية ملفات المخطوطات بـ download view بصلاحيات.
4. إصلاح صلاحيات `ReviewerSubmissionDetailView`.
5. توحيد validation رفع الملفات.
6. إضافة tests لصلاحيات views.
7. تحسين webhook وقيود `gateway_order_id`.
8. إصلاح معاملات الحفظ والسباقات في submissions.

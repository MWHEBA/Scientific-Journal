from apps.accounts.models import User


def impersonation_context(request):
    """
    يتحقق من حالة الـ impersonation للـ superuser فقط ويمرر البيانات للقالب.
    """
    impersonator_id = request.session.get('impersonator_user_id')
    
    if not impersonator_id:
        return {'is_impersonating': False, 'impersonator_user': None}

    # تحقق من أن المستخدم الأصلي كان superuser
    impersonator = User.objects.filter(pk=impersonator_id, is_superuser=True).first()
    if not impersonator:
        # امسح الـ session إذا كان المستخدم الأصلي ليس superuser
        if 'impersonator_user_id' in request.session:
            del request.session['impersonator_user_id']
            request.session.modified = True
        return {'is_impersonating': False, 'impersonator_user': None}

    # تحقق إذا كان المستخدم الحالي مختلفاً عن الـ superuser الأصلي
    is_impersonating = (
        request.user.is_authenticated and 
        request.user.pk != impersonator.pk
    )

    return {
        'is_impersonating': is_impersonating,
        'impersonator_user': impersonator,
    }

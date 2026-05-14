from apps.accounts.models import User


def impersonation_context(request):
    impersonator_id = request.session.get('impersonator_user_id')
    if not impersonator_id:
        return {'is_impersonating': False, 'impersonator_user': None}

    impersonator = User.objects.filter(pk=impersonator_id, role=User.ROLE_ADMIN).first()
    if not impersonator:
        request.session.pop('impersonator_user_id', None)
        return {'is_impersonating': False, 'impersonator_user': None}

    return {
        'is_impersonating': request.user.is_authenticated and request.user.pk != impersonator.pk,
        'impersonator_user': impersonator,
    }

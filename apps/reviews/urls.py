from django.urls import path
from apps.reviews.views import ReviewDetailView, ReviewSubmitView

app_name = 'reviews'

urlpatterns = [
    path('<int:pk>/',        ReviewDetailView.as_view(), name='detail'),
    path('<int:pk>/submit/', ReviewSubmitView.as_view(), name='submit'),
]

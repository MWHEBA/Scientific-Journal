from django.urls import path
from apps.submissions.views import (
    SubmissionCreateView,
    SubmissionUpdateView,
    SubmissionSubmitView,
    RevisionUploadView,
)

app_name = 'submissions'

urlpatterns = [
    path('new/',              SubmissionCreateView.as_view(), name='create'),
    path('<int:pk>/edit/',    SubmissionUpdateView.as_view(), name='edit'),
    path('<int:pk>/submit/',  SubmissionSubmitView.as_view(), name='submit'),
    path('<int:pk>/revise/',  RevisionUploadView.as_view(),   name='revise'),
]

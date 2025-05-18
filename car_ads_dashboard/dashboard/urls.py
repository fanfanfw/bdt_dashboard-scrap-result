from django.urls import path
from . import views
from .views import trigger_sync

urlpatterns = [
    path('user/<str:username>/', views.user_dashboard, name='user_dashboard'),
    path('listing/<str:username>/', views.data_listing, name='data_listing'),
    path('admin/<str:username>/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/<str:username>/sync/', trigger_sync, name='trigger_sync'),
]

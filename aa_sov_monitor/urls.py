from django.urls import path
from . import views

app_name = 'aa_sov_monitor'

urlpatterns = [
    path('', views.index, name='index'),
    path('add-owner/', views.add_owner, name='add_owner'),
    path('rift-export/', views.rift_export, name='rift_export'),
]

from django.urls import path
from . import views

app_name = 'qa_monitor'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('tests/', views.test_list, name='test_list'),
    path('tests/<int:test_id>/', views.test_detail, name='test_detail'),
    path('tests/<int:testcase_id>/detail/', views.testcase_detail, name='testcase_detail'),
    path('testrun/<int:run_id>/', views.testrun_detail, name='testrun_detail'),
    path('test_result_test/', views.test_result_test, name='test_result_test'),
]
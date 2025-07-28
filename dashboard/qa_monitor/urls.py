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
    
    # API 관련 화면
    path('api/', views.api_dashboard, name='api_dashboard'),
    path('api/performance/', views.api_performance_chart, name='api_performance_chart'),
    path('api/errors/', views.api_error_analysis, name='api_error_analysis'),
    path('api/menu-logs/', views.menu_api_logs, name='menu_api_logs'),
    
    # Hierarchy 분석 화면
    path('hierarchy/', views.hierarchy_analysis, name='hierarchy_analysis'),
    path('hierarchy/<int:test_case_id>/', views.hierarchy_detail, name='hierarchy_detail'),
]
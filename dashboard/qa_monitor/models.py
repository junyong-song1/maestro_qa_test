from django.db import models
from django.utils import timezone

# Create your models here.

class TestCase(models.Model):
    """테스트 케이스 모델"""
    case_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"TC{self.case_id}: {self.title}"

class TestRun(models.Model):
    """테스트 실행 모델"""
    run_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, default='untested')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Run{self.run_id}: {self.name}"

class TestAPI(models.Model):
    """API 호출 데이터 모델"""
    test_case_id = models.IntegerField()
    url = models.URLField()
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    elapsed = models.FloatField()  # 응답 시간 (초)
    request_size = models.IntegerField(default=0)
    response_size = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"API {self.method} {self.url} ({self.status_code})"

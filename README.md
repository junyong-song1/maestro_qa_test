# maestro_qa_test

## 프로젝트 개요
Maestro와 TestRail을 연동하여 테스트 자동화 및 결과 업로드를 지원하는 프로젝트입니다.

---

## 전체 동작 다이어그램

```mermaid
flowchart TD
    A[사용자] -->|install_and_run.sh 실행| B(가상환경 생성 및 패키지 설치)
    B --> C{config.ini 존재 확인}
    C -- 예시 파일 복사 필요 --> D[config.ini.example → config.ini]
    C -- 이미 존재 --> E[환경 준비 완료]
    D --> E
    E --> F[testrail_maestro_runner.py 실행]
    F --> G[TestRail에서 테스트케이스 목록 조회]
    G --> H[maestro_flows/ 에서 YAML 플로우 매칭]
    H --> I[Maestro로 테스트 자동 실행]
    I --> J[실행 결과 result/ 및 logs/ 저장]
    I --> K[TestRail에 결과 및 첨부 자동 업로드]
    J --> L[불필요 파일은 .gitignore로 관리]
    K --> M[테스트 완료 보고]
    style L fill:#fff,stroke:#bbb,stroke-width:2px
    style M fill:#fff,stroke:#bbb,stroke-width:2px
```

---

## 설치 및 실행 방법

1. 저장소 클론
   ```bash
   git clone https://github.com/junyong-song1/maestro_qa_test.git
   cd maestro_qa_test
   ```

2. 환경설정 파일 준비  
   - `config.ini.example`을 복사하여 `config.ini`로 이름을 바꾼 뒤, 본인 환경에 맞게 수정하세요.
   - 절대 민감정보(API Key 등)는 Github에 올리지 마세요.

3. 설치 및 실행
   ```bash
   bash install_and_run.sh
   ```

## config.ini 예시

```ini
[TestRail]
url = https://your-testrail-url.com
project_id = 123
username = your_email@example.com
api_key = YOUR_API_KEY
```

## 보안 안내
- `config.ini`에는 절대 민감정보를 포함하여 커밋하지 마세요.
- 예시 파일(`config.ini.example`)만 업로드하세요.

## 기타
- 불필요한 로그, 결과, 임시 파일 등은 .gitignore로 자동 제외됩니다.
- mp4 등 대용량 파일은 직접 삭제해 주세요.

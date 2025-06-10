#!/bin/bash
# 사용법: ./scripts/maestro_run_with_datetime.sh maestro_flows/TC00000_앱시작.yaml

set -e

ORIGINAL_YAML="$1"
if [ -z "$ORIGINAL_YAML" ]; then
  echo "[ERROR] YAML 파일 경로를 인자로 입력하세요."
  exit 1
fi

BASENAME=$(basename "$ORIGINAL_YAML" .yaml)
DATE=$(date +%Y%m%d)
TIME=$(date +%H%M%S)
RESULT_DIR="result/$DATE"
TMP_YAML="${ORIGINAL_YAML%.yaml}_tmp.yaml"

mkdir -p "$RESULT_DIR"

# 1단계: {{DATE}}, {{TIME}} 치환만 먼저 수행
gsed --version >/dev/null 2>&1 && SED=gsed || SED=sed
$SED "s|{{DATE}}|$DATE|g; s|{{TIME}}|$TIME|g" "$ORIGINAL_YAML" > "$TMP_YAML.1"
# 2단계: startRecording 라인에 .mp4를 문자열 내부에 붙임
$SED 's|\(startRecording: ".*\)\(".*\)|\1.mp4\2|' "$TMP_YAML.1" > "$TMP_YAML"
rm "$TMP_YAML.1"

# Maestro 실행
maestro test "$TMP_YAML"

# 임시 YAML 삭제
rm "$TMP_YAML"

echo "[INFO] 녹화 파일 위치: $RESULT_DIR/${BASENAME}_$TIME.mp4" 
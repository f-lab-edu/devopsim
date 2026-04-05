#!/bin/bash
# PostToolUse 훅: Bash 툴 실행 결과를 session-log.md에 기록
# stdin으로 JSON을 받아 command와 output을 추출한다

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
OUTPUT=$(echo "$INPUT" | jq -r '.tool_response | if type == "string" then . else (.stdout // "") end' 2>/dev/null || echo "")
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 출력이 없거나 짧은 명령어는 기록하지 않음
if [ -z "$OUTPUT" ] || [ "$OUTPUT" = "null" ] || [ ${#OUTPUT} -lt 10 ]; then
  exit 0
fi

# git, ls 같은 탐색 명령어는 스킵
case "$COMMAND" in
  git\ log*|git\ status*|git\ diff*|ls*|pwd|echo*|cat*)
    exit 0
    ;;
esac

LOG_FILE=".claude/session-log.md"

# 파일이 없으면 헤더 생성
if [ ! -f "$LOG_FILE" ]; then
  echo "# Session Log" > "$LOG_FILE"
  echo "" >> "$LOG_FILE"
fi

{
  echo "### $TIMESTAMP"
  echo '```bash'
  echo "$ $COMMAND"
  echo "$OUTPUT"
  echo '```'
  echo ""
} >> "$LOG_FILE"

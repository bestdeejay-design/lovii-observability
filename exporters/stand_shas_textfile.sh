#!/usr/bin/env bash
# stand_shas_textfile.sh — SHA задеплоенных стеков на prod-сервере.
# Запускается НА ПРОДЕ по cron (каждую минуту) и пишет Prometheus-textfile
# для node_exporter textfile-collector. Читает только git HEAD в /opt/<stack>
# и /home/deploy/lovii-deploy.log — ничего не меняет, кроме своего .prom-файла.
#
# Развилка (не закрыта): правка cron на проде. Канон «compose/ci.yml только через
# репо» на файлы мониторинга не распространяется (установка мониторинга 11.10
# была ручной), но для аудита А-1 фиксируем: скрипт идёт на прод через
# существующий канал доставки доков, ключей не добавляет.
set -euo pipefail
OUT="${1:-/var/lib/node_exporter/textfile/lovii_stands.prom}"
LOG=/home/deploy/lovii-deploy.log

# app не в /opt (статический бандл) — его SHA экспортит pipeline_exporter
# из публичного version.json; здесь app не пишем.
STACKS="
prod-core /opt/lovii-core
staging-core /opt/lovii-core-staging
prod-b2b /opt/lovii-b2b
staging-b2b /opt/lovii-b2b-staging
prod-admin /opt/lovii-admin
staging-admin /opt/lovii-admin-staging
"

{
  echo "$STACKS" | while read -r stand dir; do
    [ -z "$stand" ] && continue
    if sha=$(git -C "$dir" rev-parse HEAD 2>/dev/null); then
      echo "lovii_stack_sha{stand=\"$stand\",sha=\"$sha\"} 1"
    else
      echo "lovii_stack_sha{stand=\"$stand\",sha=\"unknown\"} 0"
    fi
  done
  # История деплоев: только разобранные поля (ts, stack, sha, event) с валидацией.
  # Сырые строки лога НЕ экспортируем: свободный текст может унести секрет в TSDB.
  tail -n 200 "$LOG" 2>/dev/null | grep -E "START|OK" | tail -n 40 | while read -r line; do
    ts=$(printf %s "$line" | cut -d' ' -f1 | tr -cd '0-9T:Z-')
    event=$(printf %s "$line" | grep -o 'START\|OK' | head -1)
    stack=$(printf %s "$line" | sed -n 's/.*stack=\([A-Za-z0-9_-]*\).*/\1/p')
    sha=$(printf %s "$line"   | sed -n 's/.*sha=\([0-9a-f]\{7,40\}\).*/\1/p')
    [ -n "$ts" ] && [ -n "$event" ] && [ -n "$stack" ] && \
      echo "lovii_deploy_log{ts=\"$ts\",event=\"$event\",stack=\"$stack\",sha=\"${sha:-none}\"} 1"
  done
} > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

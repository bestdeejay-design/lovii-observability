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

declare -A STACKS=(
  [prod-core]=/opt/lovii-core       [staging-core]=/opt/lovii-core-staging
  [prod-b2b]=/opt/lovii-b2b         [staging-b2b]=/opt/lovii-b2b-staging
  [prod-admin]=/opt/lovii-admin     [staging-admin]=/opt/lovii-admin-staging
)
# app не в /opt (статический бандл) — его SHA экспортит pipeline_exporter
# из публичного version.json; здесь app не пишем.

{
  for stand in "${!STACKS[@]}"; do
    dir=${STACKS[$stand]}
    if sha=$(git -C "$dir" rev-parse HEAD 2>/dev/null); then
      echo "lovii_stack_sha{stand=\"$stand\",sha=\"$sha\"} 1"
    else
      echo "lovii_stack_sha{stand=\"$stand\",sha=\"unknown\"} 0"
    fi
  done
  # История деплоев: последние START/OK как info-метрика (аннотации строит Grafana).
  tail -n 200 "$LOG" 2>/dev/null | grep -E "START|OK" | tail -n 40 | while read -r line; do
    ts=${line%% *}; rest=${line#* }   # 2026-10-11T22:40:29Z [staging] START stack=... sha=...
    safe=$(printf %s "$rest" | tr '"' "'")
    echo "lovii_deploy_log{ts=\"$ts\",line=\"$safe\"} 1"
  done
} > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

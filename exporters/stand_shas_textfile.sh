#!/usr/bin/env bash
# stand_shas_textfile.sh — SHA и отставание задеплоенных стеков на prod-сервере.
# Запускается НА ПРОДЕ по cron (каждую минуту) и пишет Prometheus-textfile
# для node_exporter textfile-collector. Читает git в /opt/<stack> и
# /home/deploy/lovii-deploy.log — ничего не меняет, кроме своего .prom-файла.
#
# Гарантии свежести (аудит А-2 P1-1): скрипт ВСЕГДА перезаписывает OUT
# (даже при пустом/отсутствующем логе), пишет lovii_stands_textfile_ok и
# lovii_stands_textfile_timestamp_seconds — алерт на старость ловит смерть cron.
# Ограничение (А-2 P1-6): git HEAD = факт checkout, не факт «что запущено»;
# расхождение HEAD vs контейнер — известное ограничение, backlog.
set -uo pipefail   # без -e: сбор данных лучший-усилие, OUT пишем всегда
OUT="${1:-/var/lib/node_exporter/textfile/lovii_stands.prom}"
LOG=/home/deploy/lovii-deploy.log
TMP="$OUT.tmp"
trap 'rm -f "$TMP"' EXIT

# стенд /opt-каталог | ветка-источник
STACKS="
prod|core|/opt/lovii-core|master
staging|core|/opt/lovii-core-staging|staging
prod|b2b|/opt/lovii-b2b|master
staging|b2b|/opt/lovii-b2b-staging|staging
prod|admin|/opt/lovii-admin|master
staging|admin|/opt/lovii-admin-staging|staging
"

ok=1
{
  while IFS='|' read -r stand repo dir branch; do
    [ -z "$stand" ] && continue
    if sha=$(git -C "$dir" rev-parse HEAD 2>/dev/null); then
      echo "lovii_stack_sha{stand=\"$stand\",repo=\"$repo\",sha=\"$sha\"} 1"
      # отставание стенда от origin-ветки, в коммитах (считает сам экспортер-скрипт,
      # не клиент Grafana — аудит А-2 чек-лист п.1); требует свежего origin/$branch
      if behind=$(git -C "$dir" rev-list --count "HEAD..origin/$branch" 2>/dev/null); then
        echo "lovii_stack_behind{stand=\"$stand\",repo=\"$repo\",branch=\"$branch\"} $behind"
      else
        echo "lovii_stack_behind{stand=\"$stand\",repo=\"$repo\",branch=\"$branch\"} -1"
      fi
    else
      ok=0
      echo "lovii_stack_sha{stand=\"$stand\",repo=\"$repo\",sha=\"unknown\"} 0"
    fi
  done <<< "$STACKS"
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
  echo "lovii_stands_textfile_ok $ok"
  echo "lovii_stands_textfile_timestamp_seconds $(date +%s)"
} > "$TMP" && mv "$TMP" "$OUT"

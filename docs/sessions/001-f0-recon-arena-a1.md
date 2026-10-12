# Сессия 001 — Ф-0 наблюдаемости: рекогнисцировка, каркас, арена А-1

Дата: 2026-10-12. Репо: `bestdeejay-design/lovii-observability` (public).
План: `~/LOVII/НАБЛЮДАЕМОСТЬ-ПЛАН.md`. Арена: `bestdeejay-design/lovii-arena-observability`.

## Сделано

1. Рекогнисцировка прода (read-only SSH): SHA стенда = `git -C /opt/<stack> rev-parse HEAD`;
   история деплоев `/home/deploy/lovii-deploy.log` (START/OK, sha, pb);
   app = публичный `version.json` = `production·<sha>·<date>`;
   деплой = `ssh deploy@host "deploy <stack> <sha> <before>"` → `/home/deploy/bin/lovii-deploy`.
2. Каркас экспортеров: pipeline (GitHub API + app version.json), agents (heartbeat),
   stand_shas textfile (живёт на проде). README с рамками и шагами установки.
3. Арена А-1 (аудит безопасности): **NO-GO с P0** — Grafana admin-пароль утёк в
   публичный арена-репо через копию плана. Устранено: пароль ротирован через
   Grafana API (`/api/admin/users/1/password`, старый = 401, новый в
   PROD-SERVER-AND-MONITORING.md), история арена-репо переписана одним коммитом.
4. P1 закрыты: TTL-кэш (rate-limit GitHub), экранирование лейблов + валидация SHA,
   fix scoping `started`, retention выключен по умолчанию (.trash вместо unlink),
   деплой-лог экспортируется только разобранными полями.
5. Отчёт арены: `arena-репо/reports/A-1-f0-skeleton.md` — вердикт GO на Ф-1.

## Хвосты

- Владелец: fine-grained PAT (read-only, lovii-tech, actions:read+contents:read) → CHUWI.
- Ф-1: scrape-конфиг в Prometheus хаба, systemd-юниты, дашборд Grafana.
- Развилка: cron textfile-скрипта на проде (+ проверить textfile-collector node_exporter).
- P2 арены при установке: непривилегированный юзер, EnvironmentFile 600.

## Урок

Креды в арена-репо не попадают НИКОГДА, даже в копии плана «для контекста» —
перед пушем в публичный репо grep по секретам (выучено на P0-1).

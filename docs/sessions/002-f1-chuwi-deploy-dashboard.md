# Сессия 002 — Ф-1: экспортеры в Prometheus хаба + дашборд Grafana

Дата: 2026-10-12 (день). Токен: fine-grained read-only от владельца (Actions:read +
Contents:read, 4 репо lovii-tech, 90 дней) — лежит на CHUWI `~/monitoring/lovii/exporter.env`
(600, вне git). Проверен: чтение 4/4 репо ✅, запись 403 ✅.

## Сделано
- Экспортеры подняты как контейнеры в compose хаба `~/monitoring` (lovii-pipeline-exporter,
  lovii-agents-exporter; образ python:3.12-alpine, код из публичного репо git-pull-ом,
  env_file, порты наружу НЕ опубликованы — только сеть compose).
- Prometheus: job `lovii-cicd` → targets lovii-*-exporter:9118/9119, оба UP.
- `EXPORTER_BIND` env добавлен в экспортеры (в контейнере 0.0.0.0; грабля: hardcode
  127.0.0.1 внутри контейнера недоступен Prometheus'у).
- Грабля compose: сервисы дописались внутрь секции `volumes:` → validation error;
  вставлять блоки ДО `\nvolumes:` (бэкап docker-compose.yml.bak-20261012-lovii).
- Дашборд Grafana «Lovii — CI/CD и стенды» (uid `lovii-cicd`): таблица последнего
  CI-прогона, статы отставания app-стендов от staging/master, SHA стендов, длительность
  прогонов, возраст HEAD веток. Создан API-ем (admin, пароль после ротации А-1).
- Реестр агентов: `~/agents-registry` на CHUWI смонтирован в lovii-agents-exporter.

## Живые данные (первая проверка)
app staging отстаёт от staging на 1 коммит, от master на 12; prod от staging 13, от
master 15. CI core staging: success.

## Хвосты
- textfile SHA стеков core/b2b/admin на проде — развилка (cron на проде), app уже покрыт.
- Heartbeat-протокол в AGENTS.md воркспейсов — Ф-2 (правило для агентов).
- Алерты Ф-3 (пороги в НАБЛЮДАЕМОСТЬ-ПЛАН.md) — следующий этап; канал уведомлений — развилка.
- Арена: issue №1 (А-2) теперь готова к запуску владельцем.

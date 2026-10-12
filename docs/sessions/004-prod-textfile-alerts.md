# Сессия 004 — textfile на проде (пульт полон) + попытка канала алертов

Дата: 2026-10-12 (вечер). Команда владельца: «готовый мониторинг, делай сам».

## Сделано
- Textfile v2 установлен НА ПРОДЕ: /opt/lovii-observability/stand_shas_textfile.sh,
  cron от deploy (репо /opt принадлежат ему; под root git падает на dubious ownership),
  OUT=/opt/monitoring/textfile/ (chown deploy), node_exporter прода получил
  --collector.textfile.directory (бэкап compose .bak-20261012-textfile).
- Метрики lovii_stack_sha / lovii_stack_behind (6 стеков) и lovii_stands_textfile_ok
  текут через туннель; дашборд v3: таблица SHA стеков + behind app+стеков.
- Инцидент по пути: node_exporter прода падал (флаг склеен в один argv-элемент
  + мусорный placeholder в compose) — починено, target prod-srv node UP.
- Grafana: анонимный viewer, home=lovii-cicd, дашборд v2→v3 (плитки, таймлайны).

## Не сделано (нужен владелец)
- Канал алертов: chat_id не найден автономно (redis-кэш хэширован, логи без
  chat_id, пользователи без tg-колонок). Путь: владелец пишет /start @loviiru_bot
  → poller получит chat_id → Alertmanager telegram_configs. Токен бота:
  TELEGRAM_OTP_BOT_TOKEN в /opt/lovii-core/.env (на проде; CHUWI до api.telegram
  достучится напрямую — IPv4, как в каноне TG).

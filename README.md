# lovii-observability

Экспортеры наблюдаемости CI/CD и ИИ-агентов платформы lovii.
Материнский план: `~/LOVII/НАБЛЮДАЕМОСТЬ-ПЛАН.md` (копия — в
`bestdeejay-design/lovii-arena-observability`). Канон размещения: CHUWI,
рядом с Prometheus-хабом; прод подтянут существующим SSH-туннелем.

## Жёсткие рамки

- Всё read-only: никаких кнопок, никаких деплоев отсюда.
- Ни один экспортер не держит кредов прод-сервера: SHA прода отдаёт
  textfile-скрипт, который сам живёт на проде и пишет в node_exporter.
- GitHub API — только через отдельный fine-grained read-only токен
  (`GITHUB_TOKEN`, scope actions:read + contents:read на lovii-tech/*).
- Порты слушают только 127.0.0.1 на CHUWI; в Prometheus попадают через
  существующую topology хаба.

## Состав

| Файл | Что | Статус |
|---|---|---|
| `exporters/pipeline_exporter.py` | CI-прогоны/тайминги/SHA веток (GitHub API) + app version.json | скелет, Ф-1 |
| `exporters/agents_exporter.py` | heartbeat-реестр ИИ-агентов | скелет, Ф-2 |
| `exporters/stand_shas_textfile.sh` | SHA стеков прода/staging (textfile, живёт на проде) | скелет, ⚠️ нужна установка cron (развилка) |
| `grafana/` | дашборды | пусто, Ф-1 |
| `docs/` | сессии, решения | |

## Рекогнисцировка (Ф-0, 2026-10-12)

- app: `version.json` = `{"version":"production·<sha>·<date>"}` — публично, без кредов.
- core/b2b/admin: деплой = `ssh deploy@host "deploy <stack> <sha> <before>"` →
  серверный `/home/deploy/bin/lovii-deploy` делает `git reset --hard $sha` в
  `/opt/<stack>`; SHA стенда = `git -C /opt/<stack> rev-parse HEAD`.
- История деплоев с таймингами: `/home/deploy/lovii-deploy.log` (START/OK, sha, pb).
- GitHub API источник таймингов шагов: `actions/runs` + jobs API (per-page 3 достаточно).

## Установка (после Ф-0-го)

1. Владелец: создать fine-grained PAT (read-only, lovii-tech/*, actions:read,
   contents:read) → `GITHUB_TOKEN` в env экспортера на CHUWI.
2. CHUWI: systemd-юниты для pipeline/agents exporter (порт 9118/9119, bind localhost),
   scrape-конфиг в существующий Prometheus.
3. Прод (развилка): cron для stand_shas_textfile.sh + textfile-collector в
   node_exporter (проверить, что он есть в прод-стеке мониторинга).
4. Grafana: дашборд «CI/CD — пайплайны и стенды» (Ф-1), «Агенты сейчас» (Ф-2).

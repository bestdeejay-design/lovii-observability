#!/usr/bin/env python3
"""agents-exporter — реестр ИИ-агентов для Prometheus.

Источник: ~/LOVII/agents-registry/<agent>.json (пишут сами агенты по протоколу
heartbeat из НАБЛЮДАЕМОСТЬ-ПЛАН.md, Ф-2):
  {"agent":"zcode","repo":"lovii-core","branch":"feat/x","task":"SZ-xxx",
   "status":"working|done|blocked","started_at":"ISO8601","updated_at":"ISO8601"}

Метрики:
  lovii_agent_active{agent,repo,branch,task,status}   — 1, если updated_at < STALE_SEC
  lovii_agent_stale_seconds{agent}                    — возраст последнего heartbeat
Файлы старше 24ч со status=done чистятся экспортером (retention).
Запуск: systemd timer, раз в 30с, порт :9119 (bind 127.0.0.1).
"""
import os, time, json, glob

REGISTRY = os.environ.get("AGENTS_REGISTRY", os.path.expanduser("~/LOVII/agents-registry"))
STALE_SEC = int(os.environ.get("AGENT_STALE_SEC", "1800"))  # 30 мин
RETENTION_SEC = int(os.environ.get("AGENT_RETENTION_SEC", "86400"))
PORT = int(os.environ.get("EXPORTER_PORT", "9119"))

def esc(s): return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

def collect():
    lines, now = [], time.time()
    for f in sorted(glob.glob(os.path.join(REGISTRY, "*.json"))):
        try:
            with open(f) as fh:
                d = json.load(fh)
        except Exception:
            continue
        updated = d.get("updated_at", "")
        try:
            from datetime import datetime
            age = now - datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        agent = esc(d.get("agent", os.path.basename(f)[:-5]))
        status = esc(d.get("status", "unknown"))
        label = (f'agent="{agent}",repo="{esc(d.get("repo",""))}",'
                 f'branch="{esc(d.get("branch",""))}",task="{esc(d.get("task",""))}",status="{status}"')
        lines.append(f'lovii_agent_stale_seconds{{agent="{agent}"}} {age:.0f}')
        if status != "done" and age < STALE_SEC:
            lines.append(f'lovii_agent_active{{{label}}} 1')
        if status == "done" and age > RETENTION_SEC:
            os.unlink(f)  # retention: закрытые задачи старше суток
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = collect().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()

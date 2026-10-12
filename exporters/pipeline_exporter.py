#!/usr/bin/env python3
"""pipeline-exporter — метрики CI/CD lovii для Prometheus.

Источники (все read-only):
  1. GitHub API: последние прогоны Actions по 4 репо lovii-tech (ветки staging/master),
     SHA веток-источников. Нужен read-only fine-grained токен (env GITHUB_TOKEN).
  2. Публичный version.json стендов app (SHA задеплоенного бандла, без кредов).

Метрики:
  lovii_ci_run_last{repo,branch,run_id,conclusion,status}  — 1 = последний прогон ветки
  lovii_ci_run_duration_seconds{repo,branch,run_id,conclusion,status}
  lovii_ci_run_in_progress{repo,branch,run_id}             — 1 = идёт прямо сейчас
  lovii_ci_run_age_seconds{repo,branch,run_id}             — давность последнего прогона
  lovii_branch_sha_age_seconds{repo,branch,sha}            — age HEAD ветки
  lovii_app_stand_sha{stand,sha}                           — SHA app-стенда (info, 0=ошибка)
  lovii_app_stand_sha_behind{stand,branch}                 — коммитов ветки вперёд от стенда

Сборка данных — с TTL-кэшем (COLLECT_TTL_SEC, по умолчанию 60с): scrape дёргает
сборку максимум раз в TTL (~20 вызовов GitHub API за сборку => ~1200/ч, лимит 5000/ч).
Порт слушает 127.0.0.1 (EXPORTER_PORT, по умолчанию 9118).
"""
import os, re, time, json, threading, urllib.request
from datetime import datetime

REPOS = ["lovii-core", "lovii-app", "lovii-b2b", "lovii-admin"]
BRANCHES = {"staging": "push", "master": "workflow_dispatch"}
APP_STANDS = {"staging": "https://app-staging.lovii.ru/version.json",
              "prod": "https://app.lovii.ru/version.json"}
GH = "https://api.github.com"
TTL = float(os.environ.get("COLLECT_TTL_SEC", "60"))
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

def esc(s: str) -> str:
    """Экранирование значения Prometheus-лейбла (инъекция через внешние строки)."""
    return (str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " "))

def gh(path):
    req = urllib.request.Request(GH + path, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)

def iso_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()

def collect() -> str:
    lines, now = [], time.time()
    for repo in REPOS:
        for branch in BRANCHES:
            br = gh(f"/repos/lovii-tech/{repo}/branches/{branch}")
            sha = br["commit"]["sha"]
            if not SHA_RE.match(sha):
                continue
            age = now - iso_ts(br["commit"]["commit"]["committer"]["date"])
            lines.append(f'lovii_branch_sha_age_seconds{{repo="{repo}",branch="{branch}",sha="{sha}"}} {age:.0f}')
            event = BRANCHES[branch]
            runs = gh(f"/repos/lovii-tech/{repo}/actions/runs?branch={branch}&event={event}&per_page=1").get("workflow_runs", [])
            for run in runs:
                rid = run["id"]
                concl = esc(run.get("conclusion") or "none")
                status = esc(run["status"])
                lbl = f'repo="{repo}",branch="{branch}",run_id="{rid}",conclusion="{concl}",status="{status}",event="{event}"'
                started = iso_ts(run["run_started_at"])
                lines.append(f'lovii_ci_run_last{{{lbl}}} 1')
                lines.append(f'lovii_ci_run_age_seconds{{repo="{repo}",branch="{branch}",run_id="{rid}"}} {now-started:.0f}')
                failed = "1" if concl == "failure" else ("0" if status == "completed" else "")
                if failed:
                    lines.append(f'lovii_ci_run_failed{{repo="{repo}",branch="{branch}"}} {failed}')
                if status == "completed":
                    ended = iso_ts(run["updated_at"])
                    lines.append(f'lovii_ci_run_duration_seconds{{{lbl}}} {ended-started:.0f}')
                elif status == "in_progress":
                    lines.append(f'lovii_ci_run_in_progress{{repo="{repo}",branch="{branch}",run_id="{rid}"}} 1')
                    # текущий шаг застрявшего прогона (jobs API)
                    try:
                        jobs = gh(f"/repos/lovii-tech/{repo}/actions/runs/{rid}/jobs?per_page=30").get("jobs", [])
                        done = sum(1 for j in jobs if j["status"] == "completed")
                        lines.append(f'lovii_ci_run_jobs{{repo="{repo}",branch="{branch}",run_id="{rid}"}} {len(jobs)}')
                        lines.append(f'lovii_ci_run_jobs_done{{repo="{repo}",branch="{branch}",run_id="{rid}"}} {done}')
                        for j in jobs:
                            if j["status"] == "in_progress":
                                steps = [st for st in j.get("steps", []) if st["status"] == "in_progress"]
                                if steps:
                                    lines.append(f'lovii_ci_run_step{{repo="{repo}",branch="{branch}",run_id="{rid}",job="{esc(j["name"])}",step="{esc(steps[0]["name"])}"}} 1')
                    except Exception:
                        pass
    # app-стенды: публичный version.json = {"version":"production·<sha>·<date>"}
    for stand, url in APP_STANDS.items():
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                raw = json.load(r)["version"].split("·")
            stand_sha = raw[1] if len(raw) > 1 else ""
            if not SHA_RE.match(stand_sha):
                raise ValueError("bad sha in version.json")
            lines.append(f'lovii_app_stand_sha{{stand="{stand}",sha="{stand_sha}"}} 1')
            for branch in BRANCHES:
                # Семантика «отставание по коду»: 0, если SHA стенда уже
                # содержится в ветке (включая docs-only скипы деплоя и
                # merge-коммиты релизов). Иначе — коммиты ветки c момента
                # merge-base. Голый compare врёт после переписывания
                # истории (B04) и на docs-only скипах.
                cmp = gh(f"/repos/lovii-tech/lovii-app/compare/{stand_sha}...{branch}")
                merge_base = (cmp.get("merge_base_commit") or {}).get("sha", "")
                behind = 0 if merge_base == stand_sha else len(cmp.get("commits", []))
                lines.append(f'lovii_app_stand_sha_behind{{stand="{stand}",branch="{branch}"}} {behind}')
        except Exception:
            lines.append(f'lovii_app_stand_sha{{stand="{stand}",sha="fetch_error"}} 0')
    return "\n".join(lines) + "\n"

_cache_lock = threading.Lock()
_cache = {"ts": 0.0, "body": b"# collecting\n"}

_last_good = {"body": b"", "ts": 0.0}

def collect_cached() -> bytes:
    """Отдаём последний УДАЧНЫЙ срез + честный статус экспортера.
    При сбое: lovii_exporter_collect_failed=1 (gauge), данные НЕ обновляются и
    age последнего успеха виден по lovii_exporter_last_success_timestamp_seconds."""
    with _cache_lock:
        if time.time() - _cache["ts"] >= TTL:
            try:
                body = collect().encode()
                _last_good["body"] = body
                _last_good["ts"] = time.time()
                failed = b"0"
            except Exception:
                failed = b"1"
            status = (b"lovii_exporter_collect_failed " + failed + b"\n"
                      b"lovii_exporter_last_success_timestamp_seconds "
                      + str(_last_good["ts"]).encode() + b"\n")
            _cache["body"] = _last_good["body"] + status
            _cache["ts"] = time.time()
        return _cache["body"]

if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler
    PORT = int(os.environ.get("EXPORTER_PORT", "9118"))
    BIND = os.environ.get("EXPORTER_BIND", "127.0.0.1")
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(collect_cached())
        def log_message(self, *a): pass
    HTTPServer((BIND, PORT), H).serve_forever()

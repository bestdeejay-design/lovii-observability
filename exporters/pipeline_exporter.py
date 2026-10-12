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
BRANCHES = ["staging", "master"]
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
            runs = gh(f"/repos/lovii-tech/{repo}/actions/runs?branch={branch}&per_page=1").get("workflow_runs", [])
            for i, run in enumerate(runs):
                rid = run["id"]
                concl = esc(run.get("conclusion") or "none")
                status = esc(run["status"])
                lbl = f'repo="{repo}",branch="{branch}",run_id="{rid}",conclusion="{concl}",status="{status}"'
                started = iso_ts(run["run_started_at"])
                if i == 0:
                    lines.append(f'lovii_ci_run_last{{{lbl}}} 1')
                    lines.append(f'lovii_ci_run_age_seconds{{repo="{repo}",branch="{branch}",run_id="{rid}"}} {now-started:.0f}')
                else:
                    lines.append(f'lovii_ci_run_last{{{lbl}}} 0')
                if status == "completed":
                    ended = iso_ts(run["updated_at"])
                    lines.append(f'lovii_ci_run_duration_seconds{{{lbl}}} {ended-started:.0f}')
                else:
                    lines.append(f'lovii_ci_run_in_progress{{repo="{repo}",branch="{branch}",run_id="{rid}"}} 1')
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
                cmp = gh(f"/repos/lovii-tech/lovii-app/compare/{stand_sha}...{branch}")
                lines.append(f'lovii_app_stand_sha_behind{{stand="{stand}",branch="{branch}"}} {len(cmp.get("commits", []))}')
        except Exception:
            lines.append(f'lovii_app_stand_sha{{stand="{stand}",sha="fetch_error"}} 0')
    return "\n".join(lines) + "\n"

_cache_lock = threading.Lock()
_cache = {"ts": 0.0, "body": b"# collecting\n"}

def collect_cached() -> bytes:
    with _cache_lock:
        if time.time() - _cache["ts"] >= TTL:
            try:
                _cache["body"] = collect().encode()
                _cache["ts"] = time.time()
            except Exception as e:
                # держим предыдущий срез, ошибку — служебной метрикой
                prev = _cache["body"]
                _cache["body"] = prev + b'lovii_exporter_collect_failed 1\n'
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

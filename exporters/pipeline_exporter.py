#!/usr/bin/env python3
"""pipeline-exporter — метрики CI/CD lovii для Prometheus.

Источники (все read-only):
  1. GitHub API: последние прогоны Actions по 4 репо lovii-tech (ветки staging/master),
     SHA веток-источников. Нужен read-only fine-grained токен (env GITHUB_TOKEN).
  2. Публичный version.json стендов app (SHA задеплоенного бандла, без кредов).

Метрики:
  lovii_ci_run_last{repo,branch,conclusion,status,run_id}  — 1, если это последний прогон
  lovii_ci_run_duration_seconds{repo,branch,run_id}
  lovii_ci_run_age_seconds{repo,branch}                    — давность последнего прогона
  lovii_ci_run_in_progress{repo,branch,run_id}             — 1 = идёт прямо сейчас
  lovii_branch_sha_seconds{repo,branch}                    — age HEAD ветки
  lovii_app_stand_sha{stand,sha}                           — SHA app-стенда (info)
  lovii_app_stand_sha_behind{stand}                        — ветка ушла вперёд от стенда (коммитов)

Запуск: systemd timer, раз в 30–60с. Слушает :9118 (bind 127.0.0.1).
"""
import os, time, json, urllib.request

REPOS = ["lovii-core", "lovii-app", "lovii-b2b", "lovii-admin"]
BRANCHES = {"lovii-core": ["staging", "master"], "lovii-app": ["staging", "master"],
            "lovii-b2b": ["staging", "master"], "lovii-admin": ["staging", "master"]}
APP_STANDS = {"staging": "https://app-staging.lovii.ru/version.json",
              "prod": "https://app.lovii.ru/version.json"}
PORT = int(os.environ.get("EXPORTER_PORT", "9118"))
GH = "https://api.github.com"

def gh(path):
    req = urllib.request.Request(GH + path, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)

def collect():
    lines, now = [], time.time()
    for repo in REPOS:
        for branch in BRANCHES[repo]:
            br = gh(f"/repos/lovii-tech/{repo}/branches/{branch}")
            sha, ts = br["commit"]["sha"], br["commit"]["commit"]["committer"]["date"]
            from datetime import datetime
            age = now - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            lines.append(f'lovii_branch_sha_seconds{{repo="{repo}",branch="{branch}",sha="{sha}"}} {age:.0f}')
            runs = gh(f"/repos/lovii-tech/{repo}/actions/runs?branch={branch}&per_page=3")
            for run in runs.get("workflow_runs", []):
                rid, concl, status = run["id"], run.get("conclusion") or "none", run["status"]
                dur = (run.get("run_started_at"), run.get("updated_at"))
                started = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00")).timestamp()
                ended = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00")).timestamp() if status == "completed" else now
                label = f'repo="{repo}",branch="{branch}",run_id="{rid}",conclusion="{concl}",status="{status}"'
                lines.append(f'lovii_ci_run_last{{{label}}} 1' if run == runs["workflow_runs"][0]
                             else f'lovii_ci_run_last{{{label}}} 0')
                lines.append(f'lovii_ci_run_duration_seconds{{{label}}} {ended-started:.0f}')
                if status == "in_progress":
                    lines.append(f'lovii_ci_run_in_progress{{repo="{repo}",branch="{branch}",run_id="{rid}"}} 1')
            lines.append(f'lovii_ci_run_age_seconds{{repo="{repo}",branch="{branch}"}} {now-started:.0f}')
    # app-стенды: публичный version.json {"version":"production·<sha>·<date>"}
    for stand, url in APP_STANDS.items():
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                raw = json.load(r)["version"].split("·")
            stand_sha = raw[1] if len(raw) > 1 else "unknown"
            lines.append(f'lovii_app_stand_sha{{stand="{stand}",sha="{stand_sha}"}} 1')
            for repo in ("lovii-app",):
                for branch in ("staging", "master"):
                    br = gh(f"/repos/lovii-tech/{repo}/branches/{branch}")
                    if br["commit"]["sha"].startswith(stand_sha[:7]):
                        behind = sum(1 for c in gh(f"/repos/lovii-tech/{repo}/compare/{stand_sha[:40]}...{branch}").get("commits", []))
                        lines.append(f'lovii_app_stand_sha_behind{{stand="{stand}",branch="{branch}"}} {behind}')
                        break
        except Exception as e:
            lines.append(f'lovii_app_stand_sha{{stand="{stand}",sha="fetch_error"}} 0')
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

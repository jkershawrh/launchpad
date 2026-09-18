#!/usr/bin/env python3
"""Generate the self-contained Launchpad product roadmap dashboard.

The roadmap Markdown owns hierarchy and schedule. The JSON status ledger owns
proof state, evidence links, and rubric points. This generator intentionally
fails closed: a task cannot display GREEN-live unless TDD, EDD, CDD, BDD, and
CBT are all GREEN-live.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "product-delivery-roadmap.md"
STATUS = ROOT / "docs" / "product-roadmap-status.json"
PILOT_POSTMORTEM = ROOT / "docs" / "september-17-pilot-postmortem.json"
OUTPUT = ROOT / "docs" / "product-roadmap-dashboard.html"
METHODS = ("tdd", "edd", "cdd", "bdd", "cbt")
STAGES = ("red", "green-local", "green-integration", "green-live")
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}
MONTHS = {
    month: index
    for index, month in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        start=1,
    )
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip("*")


def _parse_target(value: str) -> tuple[str, str]:
    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?\s*[–-]\s*"
        r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
        value,
    )
    if not match:
        raise ValueError(f"Unsupported roadmap target: {value}")
    start_month, start_day, start_year, end_month, end_day, end_year = match.groups()
    resolved_start_year = int(start_year or end_year)
    return (
        date(resolved_start_year, MONTHS[start_month], int(start_day)).isoformat(),
        date(int(end_year), MONTHS[end_month], int(end_day)).isoformat(),
    )


def parse_roadmap(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    horizons: list[dict[str, Any]] = []
    epics: dict[str, dict[str, Any]] = {}
    stories: dict[str, dict[str, Any]] = {}
    tasks: dict[str, dict[str, Any]] = {}
    current_horizon: dict[str, Any] | None = None
    current_epic: dict[str, Any] | None = None
    current_story: dict[str, Any] | None = None

    story_matches = {
        match.group(1): _clean(match.group(2))
        for match in re.finditer(r"\*\*(LP-S\d{3})\s+—\s+(.+?)\*\*", text, re.DOTALL)
    }

    for line in lines:
        horizon_match = re.match(r"## Horizon (\d+)\s+—\s+(.+)", line)
        if horizon_match:
            current_horizon = {
                "id": f"H{horizon_match.group(1)}",
                "number": int(horizon_match.group(1)),
                "title": _clean(horizon_match.group(2)),
                "target": "",
                "start": "",
                "end": "",
                "epic_ids": [],
            }
            horizons.append(current_horizon)
            current_epic = None
            current_story = None
            continue
        if current_horizon and line.startswith("**Target:**"):
            target = _clean(line.replace("**Target:**", ""))
            current_horizon["target"] = target
            current_horizon["start"], current_horizon["end"] = _parse_target(target)
            continue
        epic_match = re.match(r"### (LP-E\d{3})\s+—\s+(.+)", line)
        if epic_match:
            if not current_horizon:
                raise ValueError(f"Epic {epic_match.group(1)} has no horizon")
            current_epic = {
                "id": epic_match.group(1),
                "title": _clean(epic_match.group(2)),
                "horizon_id": current_horizon["id"],
                "story_ids": [],
                "task_ids": [],
            }
            epics[current_epic["id"]] = current_epic
            current_horizon["epic_ids"].append(current_epic["id"])
            current_story = None
            continue
        story_start = re.match(r"\*\*(LP-S\d{3})\s+—", line)
        if story_start:
            if not current_epic:
                raise ValueError(f"Story {story_start.group(1)} has no epic")
            story_id = story_start.group(1)
            current_story = {
                "id": story_id,
                "title": story_matches[story_id],
                "epic_id": current_epic["id"],
                "horizon_id": current_horizon["id"],
                "task_ids": [],
                "gate": "",
            }
            stories[story_id] = current_story
            current_epic["story_ids"].append(story_id)
            continue
        task_match = re.match(r"- `?(LP-T\d{3})`?\s+(.+)", line)
        if task_match:
            if not current_story or not current_epic or not current_horizon:
                raise ValueError(f"Task {task_match.group(1)} has no story")
            task_id = task_match.group(1)
            task = {
                "id": task_id,
                "title": _clean(task_match.group(2)),
                "story_id": current_story["id"],
                "epic_id": current_epic["id"],
                "horizon_id": current_horizon["id"],
            }
            tasks[task_id] = task
            current_story["task_ids"].append(task_id)
            current_epic["task_ids"].append(task_id)
            continue
        gate_match = re.match(r"- \*\*Gate:\*\*\s+(.+)", line)
        if gate_match and current_story:
            current_story["gate"] = _clean(gate_match.group(1))

    if not all(horizon["start"] and horizon["end"] for horizon in horizons):
        raise ValueError("Every horizon must have a parseable target range")
    return {
        "title": "Launchpad product delivery roadmap",
        "horizons": horizons,
        "epics": epics,
        "stories": stories,
        "tasks": tasks,
        "source": str(path.relative_to(ROOT)),
    }


def load_status(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported status schema_version")
    return data


def normalise_task_status(task_id: str, status: dict[str, Any]) -> dict[str, Any]:
    configured = status.get("tasks", {}).get(task_id, {})
    declared = configured.get("state", "red")
    if declared not in STAGE_RANK:
        raise ValueError(f"Invalid state {declared!r} for {task_id}")
    methods = {}
    for method in METHODS:
        stage = configured.get("methods", {}).get(method, "red")
        if stage not in STAGE_RANK:
            raise ValueError(f"Invalid {method} state {stage!r} for {task_id}")
        methods[method] = stage
    effective_rank = min([STAGE_RANK[declared], *(STAGE_RANK[value] for value in methods.values())])
    effective = STAGES[effective_rank]
    return {
        "declared_state": declared,
        "state": effective,
        "methods": methods,
        "proof_complete": effective == "green-live",
        "evidence": configured.get("evidence", []),
        "note": configured.get("note", ""),
    }


def _inline_svg(path: Path, label: str) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<\?xml[^>]*>\s*", "", raw)
    raw = re.sub(r"<!--.*?-->\s*", "", raw, flags=re.DOTALL)
    raw = raw.replace("<svg ", f'<svg role="img" aria-label="{html.escape(label)}" ' , 1)
    return raw


def render_dashboard(model: dict[str, Any], status: dict[str, Any], root: Path) -> str:
    enriched_tasks = {}
    for task_id, task in model["tasks"].items():
        enriched_tasks[task_id] = {**task, **normalise_task_status(task_id, status)}

    payload = {
        **model,
        "tasks": enriched_tasks,
        "status_updated_at": status.get("updated_at", "unknown"),
        "rubric": status.get("rubric", []),
        "pilot": json.loads(PILOT_POSTMORTEM.read_text(encoding="utf-8")),
        # Keep generation deterministic so CI can prove that the checked-in
        # dashboard matches the roadmap and ledger byte-for-byte.
        "generated_at": status.get("updated_at", "unknown"),
    }
    # Reuse the same approved Red Hat mark as the requester, admin, and trainer
    # experiences. The previous demo-specific file reconstructed the wordmark
    # with SVG text and did not match the official brand asset.
    redhat = _inline_svg(root / "frontend/public/logos/redhat.svg", "Red Hat")
    intel = _inline_svg(root / "demos/frontend/public/intel-logo.svg", "Intel")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__REDHAT_LOGO__", redhat).replace("__INTEL_LOGO__", intel).replace("__DATA__", data)


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#151515">
  <title>Launchpad Product Roadmap</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@500;600;700&family=Red+Hat+Text:wght@400;500;600&display=swap');
    :root{--red:#ee0000;--red-dark:#b80000;--blue:#0068b5;--blue-light:#58a6e7;--green:#3e8635;--green-light:#6ec664;--amber:#f0ab00;--black:#151515;--surface:#212121;--surface-2:#292929;--border:#3c3f42;--muted:#b8bbbe;--quiet:#8a8d90;--white:#fff;--content:1440px}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:#e8e8e8;background:var(--black);font-family:"Red Hat Text",system-ui,sans-serif;line-height:1.5}button,input,select{font:inherit}a{color:var(--blue-light)}h1,h2,h3,h4{color:#fff;font-family:"Red Hat Display",system-ui,sans-serif;line-height:1.15}h1{margin:0 0 18px;font-size:clamp(2.5rem,6vw,4.8rem);letter-spacing:-.045em}h2{margin:0 0 10px;font-size:clamp(1.6rem,3vw,2.3rem)}h3{margin:0;font-size:1.1rem}p{margin:0 0 1rem}
    .topbar{position:sticky;z-index:30;top:0;border-bottom:1px solid #333;background:rgba(21,21,21,.97);backdrop-filter:blur(14px)}.topbar-inner{display:flex;align-items:center;justify-content:space-between;max-width:var(--content);height:68px;margin:auto;padding:0 24px}.brand{display:flex;align-items:center;gap:13px}.logo{display:flex;align-items:center}.logo.rh svg{width:auto;height:29px}.logo.intel svg{width:auto;height:21px}.brand-x{font-weight:700}.brand-name{margin-left:10px;padding-left:18px;border-left:1px solid #444;color:#fff;font-family:"Red Hat Display";font-weight:600}.status{display:flex;align-items:center;gap:8px;color:#b8d9b4;font-size:.78rem;font-weight:600}.status:before{width:8px;height:8px;border-radius:50%;background:var(--green-light);content:""}.rule{display:grid;grid-template-columns:repeat(3,1fr);height:3px}.rule span:nth-child(1){background:var(--red)}.rule span:nth-child(2){background:var(--blue)}.rule span:nth-child(3){background:var(--green)}
    .hero{position:relative;overflow:hidden;border-bottom:1px solid #2e2e2e;background:radial-gradient(circle at 82% 5%,rgba(0,113,197,.36),transparent 30%),radial-gradient(circle at 12% 115%,rgba(238,0,0,.28),transparent 35%),linear-gradient(125deg,#151515 30%,#1d2024 70%,#101b24)}.hero:after{position:absolute;inset:0;opacity:.25;background-image:linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px);background-size:34px 34px;content:"";mask-image:linear-gradient(to right,transparent,black 55%)}.hero-inner{position:relative;z-index:1;max-width:var(--content);margin:auto;padding:68px 24px 58px}.eyebrow{margin-bottom:15px;color:#ff6b6b;font-size:.76rem;font-weight:700;letter-spacing:.17em;text-transform:uppercase}.hero-copy{max-width:850px;color:#d2d2d2;font-size:1.15rem}.meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:25px}.badge{border:1px solid #4b4b4b;border-radius:999px;padding:7px 12px;background:rgba(0,0,0,.18);font-size:.78rem;font-weight:600}
    .shell{max-width:var(--content);margin:auto;padding:36px 24px 80px}.metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border:1px solid var(--border);border-radius:10px;background:var(--surface)}.metric{padding:19px 22px;border-right:1px solid var(--border)}.metric:last-child{border:0}.metric b{display:block;color:#fff;font-family:"Red Hat Display";font-size:1.9rem}.metric span{color:var(--quiet);font-size:.76rem;text-transform:uppercase;letter-spacing:.09em}.tabs{display:flex;gap:6px;margin:34px 0 26px;border-bottom:1px solid var(--border)}.tab{border:0;border-bottom:3px solid transparent;padding:12px 18px;color:var(--muted);background:transparent;cursor:pointer;font-weight:600}.tab:hover,.tab[aria-selected="true"]{color:#fff;border-bottom-color:var(--red)}.view{display:none}.view.active{display:block}.section-head{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:20px}.section-head p{max-width:760px;color:var(--muted)}
    .gantt-shell{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--surface)}.gantt{min-width:980px;padding:24px}.gantt-axis{display:grid;grid-template-columns:260px repeat(8,1fr);padding-bottom:10px;border-bottom:1px solid var(--border);color:var(--quiet);font-size:.72rem;text-transform:uppercase}.gantt-axis span:not(:first-child){text-align:center}.gantt-row{display:grid;grid-template-columns:260px 1fr;align-items:center;min-height:72px;border-bottom:1px solid #333}.gantt-row:last-child{border:0}.gantt-label button{border:0;padding:0;color:#fff;background:none;text-align:left;cursor:pointer;font-weight:600}.gantt-label small{display:block;margin-top:4px;color:var(--quiet)}.track{position:relative;height:34px;background-image:linear-gradient(90deg,transparent calc(12.5% - 1px),#353535 12.5%);background-size:12.5% 100%}.bar{position:absolute;top:4px;height:26px;min-width:3%;border-radius:4px;background:var(--blue);cursor:pointer}.bar:hover{background:var(--blue-light)}.bar .bar-label{overflow:hidden;padding:4px 9px;color:#fff;font-size:.72rem;white-space:nowrap}.today-line{position:absolute;z-index:2;top:0;bottom:0;width:2px;background:var(--red)}
    .horizon-grid{display:grid;gap:16px}.horizon{border:1px solid var(--border);border-radius:10px;background:var(--surface)}.horizon>summary{display:grid;grid-template-columns:76px 1fr auto;align-items:center;gap:16px;padding:20px;cursor:pointer;list-style:none}.horizon>summary::-webkit-details-marker,.epic>summary::-webkit-details-marker{display:none}.h-num{display:grid;width:58px;height:58px;place-items:center;border-radius:8px;background:var(--red);font-family:"Red Hat Display";font-size:1.3rem;font-weight:700}.h-copy small{color:var(--quiet)}.progress{min-width:165px}.progress-line{overflow:hidden;height:7px;border-radius:99px;background:#3a3a3a}.progress-line i{display:block;height:100%;background:var(--green)}.progress small{color:var(--quiet)}.h-body{padding:0 20px 20px}.epic{margin:10px 0;border-top:1px solid var(--border)}.epic>summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 4px;cursor:pointer}.epic-id{color:var(--blue-light);font-size:.74rem;font-weight:700;letter-spacing:.09em}.story{margin:0 0 14px;border:1px solid #3a3a3a;border-radius:7px;padding:16px;background:#1b1b1b}.story-title{font-weight:600}.gate{margin:12px 0 0;padding:10px 12px;border-left:3px solid var(--amber);color:var(--muted);background:#24210f;font-size:.83rem}.task-list{margin:13px 0 0;padding:0;list-style:none}.task-list li{display:grid;grid-template-columns:82px 1fr auto;gap:10px;padding:9px 0;border-top:1px solid #333;font-size:.85rem}.task-id{color:var(--blue-light);font-family:ui-monospace,monospace}.state{display:inline-block;border-radius:99px;padding:3px 8px;font-size:.68rem;font-weight:700;text-transform:uppercase}.red{color:#ffb9b9;background:#591515}.green-local{color:#ffe5a5;background:#5a4300}.green-integration{color:#b9dcff;background:#113a5a}.green-live{color:#c5f1bf;background:#194b19}
    .controls{display:grid;grid-template-columns:minmax(220px,1fr) 210px 210px;gap:10px;margin-bottom:15px}.controls input,.controls select{width:100%;border:1px solid #555;border-radius:6px;padding:10px 12px;color:#fff;background:#181818}.table-wrap{overflow:auto;border:1px solid var(--border);border-radius:9px}.matrix{width:100%;min-width:1100px;border-collapse:collapse;font-size:.8rem}.matrix th{position:sticky;z-index:2;top:0;padding:11px;border-bottom:2px solid #555;color:#fff;background:#181818;text-align:left}.matrix td{padding:10px 11px;border-bottom:1px solid #353535;vertical-align:top}.matrix tr:hover td{background:#242424}.method{text-align:center}.dot{display:inline-grid;width:27px;height:27px;place-items:center;border-radius:50%;font-size:.66rem;font-weight:700}.evidence a{display:block;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.empty{padding:38px;color:var(--quiet);text-align:center}
    .rubric-total{display:grid;grid-template-columns:170px 1fr;gap:24px;align-items:center;margin:24px 0 30px}.score{display:grid;width:150px;height:150px;place-items:center;border-radius:50%;background:conic-gradient(var(--green) var(--score),#333 0)}.score-inner{display:grid;width:116px;height:116px;place-items:center;border-radius:50%;background:var(--surface);text-align:center}.score b{display:block;font-family:"Red Hat Display";font-size:2rem}.rubric-list{display:grid;gap:11px}.rubric-row{display:grid;grid-template-columns:minmax(230px,1fr) 3fr 72px;align-items:center;gap:12px}.rubric-track{height:11px;border-radius:99px;background:#3a3a3a}.rubric-track i{display:block;height:100%;border-radius:99px;background:var(--green)}.rubric-row strong{text-align:right}
    .pilot-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));margin-bottom:24px;border:1px solid var(--border);border-radius:9px;background:var(--surface)}.pilot-metric{padding:17px;border-right:1px solid var(--border)}.pilot-metric:last-child{border:0}.pilot-metric b{display:block;color:#fff;font-family:"Red Hat Display";font-size:1.65rem}.pilot-metric span{color:var(--quiet);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}.post-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:22px 0}.panel{border:1px solid var(--border);border-radius:9px;padding:20px;background:var(--surface)}.panel.wide{grid-column:1/-1}.panel h3{margin-bottom:7px}.panel-copy{color:var(--muted);font-size:.86rem}.bar-list{display:grid;gap:13px;margin-top:18px}.bar-row{display:grid;grid-template-columns:minmax(170px,1fr) 3fr 92px;align-items:center;gap:12px;font-size:.82rem}.bar-track{display:flex;overflow:hidden;height:15px;border-radius:99px;background:#3a3a3a}.bar-claimed{background:var(--blue)}.bar-unused{background:#555}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.post-table{width:100%;border-collapse:collapse;font-size:.8rem}.post-table th{padding:10px;border-bottom:2px solid #555;color:#fff;text-align:left}.post-table td{padding:9px 10px;border-bottom:1px solid #383838}.post-table tbody tr:hover{background:#242424}.telemetry-list{display:grid;gap:9px;margin-top:15px}.telemetry-row{display:grid;grid-template-columns:180px 92px 1fr;align-items:start;gap:11px;padding:10px 0;border-top:1px solid #353535;font-size:.82rem}.coverage{display:inline-block;border-radius:99px;padding:3px 8px;text-align:center;font-size:.67rem;font-weight:700;text-transform:uppercase}.coverage.available{color:#c5f1bf;background:#194b19}.coverage.partial{color:#ffe5a5;background:#5a4300}.coverage.missing{color:#ffb9b9;background:#591515}.finance-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.finance-columns h4{margin:0 0 8px}.finance-columns ul{margin:0;padding-left:1.15rem;color:var(--muted);font-size:.84rem}.finance-columns li{margin-bottom:7px}.estimate-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:28px 0 12px;padding-top:22px;border-top:1px solid var(--border)}.estimate-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.cost-card{border-top:3px solid var(--blue);border-radius:6px;padding:16px;background:#191919}.cost-card b{display:block;margin:5px 0;color:#fff;font-family:"Red Hat Display";font-size:1.5rem}.cost-card small{color:var(--muted)}.basis-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:14px 0;background:var(--border)}.basis-grid div{padding:13px;background:#191919}.basis-grid b{display:block;color:#fff}.basis-grid span{color:var(--quiet);font-size:.7rem;text-transform:uppercase}.formula{margin-top:16px;border-left:3px solid var(--blue);padding:11px 13px;background:#17232c;color:#d8e8f5;font-size:.85rem}.source-links{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.source-links a{border:1px solid #49515a;border-radius:99px;padding:5px 9px;text-decoration:none;font-size:.72rem}
    .callout{display:grid;grid-template-columns:5px 1fr;margin:24px 0;border:1px solid var(--border);border-radius:8px;background:var(--surface)}.callout:before{background:var(--red);content:""}.callout>div{padding:18px 20px}.callout p:last-child{margin:0}.callout.amber:before{background:var(--amber)}.footer{border-top:1px solid #333;padding:28px 24px;color:var(--quiet);background:#111;font-size:.8rem}.footer-inner{display:flex;justify-content:space-between;max-width:var(--content);margin:auto}.footer a{margin-left:18px}
    @media(max-width:900px){.brand-name,.status{display:none}.metrics{grid-template-columns:repeat(2,1fr)}.metric{border-bottom:1px solid var(--border)}.pilot-metrics{grid-template-columns:repeat(3,1fr)}.pilot-metric{border-bottom:1px solid var(--border)}.post-grid{grid-template-columns:1fr}.panel.wide{grid-column:auto}.estimate-grid{grid-template-columns:1fr}.basis-grid{grid-template-columns:repeat(2,1fr)}.controls{grid-template-columns:1fr}.horizon>summary{grid-template-columns:60px 1fr}.progress{grid-column:2}.rubric-total{grid-template-columns:1fr}.rubric-row{grid-template-columns:1fr 2fr 58px}}@media(max-width:560px){.metrics,.pilot-metrics,.basis-grid{grid-template-columns:1fr}.section-head{align-items:start;flex-direction:column}.tabs{overflow:auto}.bar-row,.telemetry-row,.finance-columns{grid-template-columns:1fr}.bar-value{text-align:left}.task-list li{grid-template-columns:72px 1fr}.task-list .state{grid-column:2;justify-self:start}.footer-inner{flex-direction:column;gap:8px}.footer a{margin:0 14px 0 0}}
    @media print{body{color:#222;background:#fff}.topbar{position:static}.hero{background:#151515!important}.tabs,.controls,.footer{display:none}.view{display:block!important;margin-bottom:30px}.shell{max-width:none}.metrics,.horizon,.gantt-shell,.story{color:#222;background:#fff}.horizon h3,.story-title,.gantt-label button{color:#111}.matrix th{position:static;color:#111;background:#eee}}
  </style>
</head>
<body>
  <header class="topbar"><div class="topbar-inner"><div class="brand"><span class="logo rh">__REDHAT_LOGO__</span><span class="brand-x">X</span><span class="logo intel">__INTEL_LOGO__</span><span class="brand-name">Partner AI Launchpad</span></div><span class="status">Evidence-driven roadmap</span></div><div class="rule"><span></span><span></span><span></span></div></header>
  <section class="hero"><div class="hero-inner"><p class="eyebrow">Product delivery · proof-driven execution</p><h1>Launchpad product roadmap</h1><p class="hero-copy">A clickable delivery plan from pilot closeout to a governed production service. Every task moves through TDD, EDD, CDD, BDD, and component-based testing before it is counted as GREEN-live.</p><div class="meta"><span class="badge">September 2026–April 2027</span><span class="badge">Agentic parallel delivery</span><span class="badge">100/100 release gate</span><span class="badge" id="freshness"></span></div></div></section>
  <main class="shell">
    <section class="metrics" aria-label="Roadmap summary"><div class="metric"><b id="m-duration">—</b><span>Delivery window</span></div><div class="metric"><b id="m-epics">—</b><span>Epics</span></div><div class="metric"><b id="m-stories">—</b><span>Stories</span></div><div class="metric"><b id="m-tasks">—</b><span>Tasks</span></div><div class="metric"><b id="m-live">—</b><span>GREEN-live</span></div></section>
    <nav class="tabs" aria-label="Roadmap views"><button class="tab" data-target="overview" aria-selected="true">Delivery plan</button><button class="tab" data-target="pilot" aria-selected="false">September 17 Pilot</button><button class="tab" data-target="gantt" aria-selected="false">Gantt timeline</button><button class="tab" data-target="matrix" aria-selected="false">Proof matrix</button><button class="tab" data-target="rubric" aria-selected="false">Release rubric</button></nav>
    <section id="overview" class="view active" data-view="overview"><div class="section-head"><div><p class="eyebrow">Delivery hierarchy</p><h2>Horizons, epics, stories, and tasks</h2><p>Expand a horizon to inspect its delivery work. A task remains RED until every required proof method reaches the same declared stage.</p></div></div><div id="hierarchy" class="horizon-grid"></div></section>
    <section id="pilot" class="view" data-view="pilot"><div class="section-head"><div><p class="eyebrow">Event postmortem · evidence snapshot</p><h2>September 17 pilot</h2><p id="pilot-scope"></p></div><span class="badge" id="pilot-snapshot"></span></div><div class="pilot-metrics" id="pilot-metrics"></div><div class="callout amber"><div><h3>Completion accounting boundary</h3><p id="completion-statement"></p></div></div><div class="post-grid"><article class="panel"><h3>Claims by lab</h3><p class="panel-copy">Claimed seats versus provisioned-but-unclaimed seats at the snapshot.</p><div class="bar-list" id="catalog-bars"></div></article><article class="panel"><h3>Claims by wave</h3><p class="panel-copy">The three participant cohorts each had 90 provisioned seats.</p><div class="bar-list" id="wave-bars"></div></article><article class="panel wide"><h3>Workshop disposition</h3><p class="panel-copy">All event workshops remained Ready and retained; no event workshop had entered reclaim at the snapshot.</p><div class="table-wrap"><table class="post-table"><thead><tr><th>Wave</th><th>Lab</th><th>Cluster</th><th>Workshop</th><th>Claims</th><th>State</th><th>Expiration (UTC)</th></tr></thead><tbody id="workshop-body"></tbody></table></div></article><article class="panel wide"><h3>Cluster and runtime state</h3><p class="panel-copy">Readiness is infrastructure evidence, not participant-completion evidence.</p><div class="table-wrap"><table class="post-table"><thead><tr><th>Cluster</th><th>Seats</th><th>Claims</th><th>Pods ready</th><th>Routes admitted</th><th>Restarts</th><th>Interpretation</th></tr></thead><tbody id="cluster-body"></tbody></table></div><div id="model-summary" class="source-links"></div></article><article class="panel"><h3>Issue and improvement inventory</h3><div id="issue-summary"></div></article><article class="panel"><h3>Telemetry coverage</h3><div class="telemetry-list" id="telemetry-list"></div></article><article class="panel wide"><h3>Financial readiness</h3><p class="panel-copy">Financials are intentionally separated into known consumption facts and the rates or measurements still required for defensible chargeback.</p><div id="financial-summary"></div></article><article class="panel wide"><h3>Evidence sources</h3><p class="panel-copy">This tab is a dated evidence view. Reclaim results and later participant outcomes must append new evidence rather than rewrite the snapshot.</p><div class="source-links" id="pilot-sources"></div></article></div></section>
    <section id="gantt" class="view" data-view="gantt"><div class="section-head"><div><p class="eyebrow">Project management view</p><h2>Delivery Gantt</h2><p>Calendar windows overlap intentionally. Agentic work compresses build effort; infrastructure, soak, security, and human acceptance remain elapsed-time gates.</p></div></div><div class="gantt-shell"><div class="gantt" id="gantt-chart"></div></div></section>
    <section id="matrix" class="view" data-view="matrix"><div class="section-head"><div><p class="eyebrow">Red / green evidence</p><h2>TDD · EDD · CDD · BDD · CBT matrix</h2><p>Filter the 94 tasks by horizon or effective proof state. Evidence links are repository-relative and contain no secrets.</p></div></div><div class="controls"><input id="task-search" type="search" placeholder="Search task, epic, or story"><select id="horizon-filter"><option value="">All horizons</option></select><select id="state-filter"><option value="">All proof states</option><option value="red">RED</option><option value="green-local">GREEN-local</option><option value="green-integration">GREEN-integration</option><option value="green-live">GREEN-live</option></select></div><div class="table-wrap"><table class="matrix"><thead><tr><th>Task</th><th>Outcome</th><th>Effective state</th><th class="method">TDD</th><th class="method">EDD</th><th class="method">CDD</th><th class="method">BDD</th><th class="method">CBT</th><th>Evidence</th></tr></thead><tbody id="matrix-body"></tbody></table></div></section>
    <section id="rubric" class="view" data-view="rubric"><div class="section-head"><div><p class="eyebrow">Release decision</p><h2>Release rubric</h2><p>Production release requires 100/100, every critical matrix cell GREEN-live, zero unresolved critical/high findings, and repeatable cleanup evidence.</p></div></div><div class="rubric-total"><div class="score" id="score-ring"><div class="score-inner"><div><b id="score-value">0</b><span>/ 100</span></div></div></div><div><h3 id="score-decision">Not release-ready</h3><p id="score-copy" style="color:var(--muted)"></p></div></div><div class="rubric-list" id="rubric-list"></div><div class="callout"><div><h3>Fail-closed release rule</h3><p>Declared completion is never enough. The dashboard computes the effective state from all five proof methods. Missing evidence stays RED.</p></div></div></section>
  </main>
  <footer class="footer"><div class="footer-inner"><span>Generated from product-delivery-roadmap.md and product-roadmap-status.json</span><span><a href="product-delivery-roadmap.md">Roadmap source</a><a href="product-roadmap-status.json">Status ledger</a></span></div></footer>
  <script id="roadmap-data" type="application/json">__DATA__</script>
  <script>
    const data=JSON.parse(document.getElementById('roadmap-data').textContent);const methods=['tdd','edd','cdd','bdd','cbt'];const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const label=s=>s.replaceAll('-',' ');const tasks=Object.values(data.tasks);const live=tasks.filter(t=>t.state==='green-live').length;const pilot=data.pilot;
    document.getElementById('m-duration').textContent='7½ months';document.getElementById('m-epics').textContent=Object.keys(data.epics).length;document.getElementById('m-stories').textContent=Object.keys(data.stories).length;document.getElementById('m-tasks').textContent=tasks.length;document.getElementById('m-live').textContent=`${live} / ${tasks.length}`;document.getElementById('freshness').textContent=`Status ${data.status_updated_at.slice(0,10)}`;
    document.getElementById('pilot-scope').textContent=pilot.scope;document.getElementById('pilot-snapshot').textContent=`Snapshot ${pilot.snapshot_at.replace('T',' ').replace(':00Z',' UTC')}`;document.getElementById('completion-statement').textContent=`${pilot.completion.statement} ${pilot.completion.available_proof}`;
    const ps=pilot.summary;const pilotMetrics=[[ps.waves,'Participant waves'],[ps.workshops_ordered,'Workshop orders'],[ps.seats_provisioned,'Seats provisioned'],[ps.seats_claimed,'Seats claimed'],[ps.seats_unclaimed,'Seats unclaimed'],[`${ps.claim_utilization_percent}%`,'Claim utilization']];document.getElementById('pilot-metrics').innerHTML=pilotMetrics.map(([v,l])=>`<div class="pilot-metric"><b>${v}</b><span>${esc(l)}</span></div>`).join('');
    const po=pilot.post_snapshot_observations.at(-1),pos=po.summary,participantPanel=document.createElement('article');participantPanel.className='panel wide';participantPanel.innerHTML=`<h3>Participant journey correlation</h3><p class="panel-copy">A dated, privacy-safe observation appended after the immutable event snapshot.</p><div class="source-links"><span class="badge">Observed ${esc(po.observed_at.replace('T',' ').replace('Z',' UTC'))}</span><span class="coverage available">PII excluded</span></div><div class="pilot-metrics" style="grid-template-columns:repeat(6,1fr);margin:16px 0"><div class="pilot-metric"><b>${pos.seat_entitlements}</b><span>Claims observed</span></div><div class="pilot-metric"><b>${pos.unique_participant_identities}</b><span>Unique identities</span></div><div class="pilot-metric"><b>${pos.all_three_catalogs}</b><span>All three catalogs</span></div><div class="pilot-metric"><b>${pos.participants_reentering_same_workshop}</b><span>Same-workshop returns</span></div><div class="pilot-metric"><b>${pos.participants_in_multiple_waves}</b><span>Multiple waves</span></div><div class="pilot-metric"><b>${pos.activity_after_event_day}</b><span>Next-day activity</span></div></div><div class="finance-columns"><div><h4>Catalog paths</h4><div class="telemetry-list">${po.catalog_paths.map(x=>`<div class="telemetry-row"><strong>${esc(x.path)}</strong><span class="coverage available">${x.identities}</span><span>pseudonymous identities</span></div>`).join('')}</div></div><div><h4>Interpretation boundary</h4><p class="panel-copy">${esc(po.interpretation)}</p><p class="panel-copy">${esc(po.limitations)}</p><p class="panel-copy">${esc(po.privacy_boundary)}</p></div></div>`;document.querySelector('#pilot .post-grid').prepend(participantPanel);
    const barRows=items=>items.map(item=>`<div class="bar-row"><span>${esc(item.name||`Wave ${item.wave}`)}</span><span class="bar-track" title="${item.claimed} claimed; ${item.unclaimed} unclaimed"><i class="bar-claimed" style="width:${item.claim_percent}%"></i><i class="bar-unused" style="width:${100-item.claim_percent}%"></i></span><span class="bar-value">${item.claimed}/${item.ordered} · ${item.claim_percent}%</span></div>`).join('');document.getElementById('catalog-bars').innerHTML=barRows(pilot.catalogs);document.getElementById('wave-bars').innerHTML=barRows(pilot.waves);
    document.getElementById('workshop-body').innerHTML=pilot.workshops.map(w=>`<tr><td>${w.wave}</td><td>${esc(w.catalog)}</td><td>${esc(w.cluster)}</td><td><span class="task-id">${esc(w.workshop)}</span></td><td>${w.claimed}/${w.ordered}</td><td>${esc(w.state)}</td><td>${esc(w.expires.replace('T',' ').replace(':00Z',''))}</td></tr>`).join('');
    document.getElementById('cluster-body').innerHTML=pilot.clusters.map(c=>`<tr><td>${esc(c.name)}</td><td>${c.seats}</td><td>${c.claimed}/${c.seats}</td><td>${c.pods_ready}/${c.pods_total}</td><td>${c.routes_admitted}/${c.routes_total}</td><td>${c.restarts}</td><td>${esc(c.note)}</td></tr>`).join('');document.getElementById('model-summary').innerHTML=pilot.models.map(m=>`<span class="badge">${esc(m.name)} · ${m.ready}/${m.desired} ready</span>`).join('');
    const pi=pilot.issues;document.getElementById('issue-summary').innerHTML=`<div class="pilot-metrics" style="grid-template-columns:repeat(3,1fr);margin-top:14px"><div class="pilot-metric"><b>${pi.defects_and_performance}</b><span>Defect / performance items</span></div><div class="pilot-metric"><b>${pi.open}</b><span>Open</span></div><div class="pilot-metric"><b>${pi.mitigated}</b><span>Mitigated</span></div><div class="pilot-metric"><b>${pi.severity_s1}</b><span>S1 participant-critical</span></div><div class="pilot-metric"><b>${pi.severity_s2}</b><span>S2 degraded</span></div><div class="pilot-metric"><b>${pi.features_planned}</b><span>Features planned</span></div></div><p class="panel-copy">${esc(pi.statement)}</p>`;
    document.getElementById('telemetry-list').innerHTML=pilot.telemetry.map(t=>`<div class="telemetry-row"><strong>${esc(t.area)}</strong><span class="coverage ${esc(t.state)}">${esc(t.state)}</span><span>${esc(t.detail)}</span></div>`).join('');
    const pf=pilot.financials,pe=pf.estimate,rb=pe.resource_basis;document.getElementById('financial-summary').innerHTML=`<div class="pilot-metrics" style="grid-template-columns:repeat(4,1fr);margin-top:16px"><div class="pilot-metric"><b>${ps.seats_provisioned}</b><span>Provisioned seats</span></div><div class="pilot-metric"><b>${pf.ttl_hours}h</b><span>Reservation TTL</span></div><div class="pilot-metric"><b>${pf.reserved_seat_hours.toLocaleString()}</b><span>Reserved seat-hours</span></div><div class="pilot-metric"><b>${pf.unclaimed_reserved_seat_hours_if_unchanged.toLocaleString()}</b><span>Potential unclaimed seat-hours</span></div></div><div class="finance-columns"><div><h4>What can be allocated now</h4><ul>${pf.known.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div><h4>What is required for measured dollars</h4><ul>${pf.required.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></div><div class="formula"><strong>${esc(pf.state)}.</strong> ${esc(pf.formula)}</div><div class="estimate-title"><div><h3>Planning estimate</h3><p class="panel-copy">${esc(pe.status)} · confidence: ${esc(pe.confidence)}</p></div><span class="coverage partial">Estimated</span></div><div class="basis-grid"><div><b>${rb.minimum_known_cpu_requests}</b><span>Known CPU requested</span></div><div><b>${rb.minimum_known_memory_gib_requests} GiB</b><span>Known memory requested</span></div><div><b>${rb.minimum_known_vcpu_hours.toLocaleString()}</b><span>Known vCPU-hours</span></div><div><b>${rb.minimum_known_gib_hours.toLocaleString()}</b><span>Known GiB-hours</span></div></div><p class="panel-copy">${esc(rb.note)}</p><h4>September 17 event cost scenarios</h4><div class="estimate-grid">${pe.event_scenarios.map(x=>`<div class="cost-card"><small>${esc(x.name)}</small><b>${esc(x.range)}</b><small>${esc(x.includes)}</small></div>`).join('')}</div><div class="pilot-metrics" style="grid-template-columns:repeat(3,1fr);margin:16px 0"><div class="pilot-metric"><b>${esc(pe.event_unit_costs.per_provisioned_seat)}</b><span>Per provisioned seat</span></div><div class="pilot-metric"><b>${esc(pe.event_unit_costs.per_claimed_seat)}</b><span>Per claimed seat</span></div><div class="pilot-metric"><b>${esc(pe.event_unit_costs.potential_unclaimed_infrastructure_share)}</b><span>Potential unclaimed infra share</span></div></div><p class="panel-copy">${esc(pe.event_unit_costs.note)}</p><h4>Development and replacement estimate</h4><div class="estimate-grid">${pe.development.map(x=>`<div class="cost-card"><small>${esc(x.name)}</small><b>${esc(x.range)}</b><small>${esc(x.basis)}</small></div>`).join('')}</div><div class="finance-columns" style="margin-top:18px"><div><h4>Assumptions</h4><ul>${pe.assumptions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div><h4>External benchmarks</h4><div class="source-links">${pe.external_references.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a>`).join('')}</div></div></div>`;
    document.getElementById('pilot-sources').innerHTML=pilot.sources.map(s=>`<a href="../${esc(s)}">${esc(s.split('/').pop())}</a>`).join('');
    document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected','false'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));btn.setAttribute('aria-selected','true');document.getElementById(btn.dataset.target).classList.add('active');location.hash=btn.dataset.target;}));
    const statePill=s=>`<span class="state ${esc(s)}">${esc(label(s))}</span>`;function rollup(ids){const list=ids.map(id=>data.tasks[id]);return {live:list.filter(t=>t.state==='green-live').length,total:list.length,pct:list.length?Math.round(list.filter(t=>t.state==='green-live').length/list.length*100):0}}
    document.getElementById('hierarchy').innerHTML=data.horizons.map((h,hi)=>{const hTaskIds=h.epic_ids.flatMap(id=>data.epics[id].task_ids),p=rollup(hTaskIds);const epics=h.epic_ids.map(eid=>{const e=data.epics[eid],ep=rollup(e.task_ids);const stories=e.story_ids.map(sid=>{const s=data.stories[sid];const rows=s.task_ids.map(tid=>{const t=data.tasks[tid];return `<li><span class="task-id">${tid}</span><span>${esc(t.title)}</span>${statePill(t.state)}</li>`}).join('');return `<article class="story"><div class="story-title"><span class="epic-id">${sid}</span> ${esc(s.title)}</div><ul class="task-list">${rows}</ul>${s.gate?`<div class="gate"><strong>Evidence gate:</strong> ${esc(s.gate)}</div>`:''}</article>`}).join('');return `<details class="epic"><summary><h3><span class="epic-id">${eid}</span> ${esc(e.title)}</h3><span>${ep.live}/${ep.total} live</span></summary>${stories}</details>`}).join('');return `<details class="horizon" ${hi===0?'open':''}><summary><span class="h-num">H${h.number}</span><span class="h-copy"><h3>${esc(h.title)}</h3><small>${esc(h.target)} · ${h.epic_ids.length} epics · ${p.total} tasks</small></span><span class="progress"><span class="progress-line"><i style="width:${p.pct}%"></i></span><small>${p.pct}% GREEN-live</small></span></summary><div class="h-body">${epics}</div></details>`}).join('');
    const allStart=new Date(Math.min(...data.horizons.map(h=>new Date(h.start))));const allEnd=new Date(Math.max(...data.horizons.map(h=>new Date(h.end))));const total=allEnd-allStart;const months=['Sep 2026','Oct','Nov','Dec','Jan 2027','Feb','Mar','Apr'];const axis=`<div class="gantt-axis"><span>Delivery horizon</span>${months.map(m=>`<span>${m}</span>`).join('')}</div>`;const rows=data.horizons.map(h=>{const left=(new Date(h.start)-allStart)/total*100,width=(new Date(h.end)-new Date(h.start))/total*100;return `<div class="gantt-row"><div class="gantt-label"><button data-h="${h.id}">${h.id} · ${esc(h.title)}</button><small>${esc(h.target)} · ${h.epic_ids.length} epics</small></div><div class="track"><span class="bar" style="left:${left}%;width:${Math.max(width,4)}%"><span class="bar-label">${esc(h.title)}</span></span></div></div>`}).join('');document.getElementById('gantt-chart').innerHTML=axis+rows;document.querySelectorAll('[data-h]').forEach(b=>b.addEventListener('click',()=>{document.querySelector('[data-target="overview"]').click();const details=[...document.querySelectorAll('.horizon')].find(x=>x.querySelector('.h-num').textContent===b.dataset.h);if(details){details.open=true;details.scrollIntoView({behavior:'smooth'})}}));
    const hf=document.getElementById('horizon-filter');data.horizons.forEach(h=>hf.insertAdjacentHTML('beforeend',`<option value="${h.id}">${h.id} · ${esc(h.title)}</option>`));function renderMatrix(){const q=document.getElementById('task-search').value.toLowerCase(),h=hf.value,s=document.getElementById('state-filter').value;const filtered=tasks.filter(t=>{const hay=[t.id,t.title,data.epics[t.epic_id].title,data.stories[t.story_id].title].join(' ').toLowerCase();return(!q||hay.includes(q))&&(!h||t.horizon_id===h)&&(!s||t.state===s)});document.getElementById('matrix-body').innerHTML=filtered.length?filtered.map(t=>`<tr><td><span class="task-id">${t.id}</span><br><small>${t.epic_id} · ${t.story_id}</small></td><td>${esc(t.title)}${t.note?`<br><small style="color:var(--quiet)">${esc(t.note)}</small>`:''}</td><td>${statePill(t.state)}${t.declared_state!==t.state?`<br><small>declared ${esc(label(t.declared_state))}</small>`:''}</td>${methods.map(m=>`<td class="method"><span class="dot ${t.methods[m]}" title="${m.toUpperCase()}: ${label(t.methods[m])}">${t.methods[m]==='red'?'R':'G'}</span></td>`).join('')}<td class="evidence">${t.evidence.length?t.evidence.map(e=>`<a href="../${esc(e)}">${esc(e.split('/').pop())}</a>`).join(''):'<span style="color:var(--quiet)">Required</span>'}</td></tr>`).join(''):`<tr><td colspan="9" class="empty">No tasks match these filters.</td></tr>`}['task-search','horizon-filter','state-filter'].forEach(id=>document.getElementById(id).addEventListener('input',renderMatrix));renderMatrix();
    const earned=data.rubric.reduce((n,r)=>n+r.earned,0),weight=data.rubric.reduce((n,r)=>n+r.weight,0);document.getElementById('score-value').textContent=earned;document.getElementById('score-ring').style.setProperty('--score',`${earned/weight*100}%`);document.getElementById('score-decision').textContent=earned===weight?'Release-ready':'Not release-ready';document.getElementById('score-copy').textContent=earned===weight?'All rubric points are earned; final independent approval is still required.':`${weight-earned} points remain. Points are awarded only from linked, accepted evidence.`;document.getElementById('rubric-list').innerHTML=data.rubric.map(r=>`<div class="rubric-row"><span>${esc(r.label)}</span><span class="rubric-track"><i style="width:${r.weight?r.earned/r.weight*100:0}%"></i></span><strong>${r.earned} / ${r.weight}</strong></div>`).join('');
    if(location.hash&&document.querySelector(`[data-target="${location.hash.slice(1)}"]`))document.querySelector(`[data-target="${location.hash.slice(1)}"]`).click();
  </script>
</body>
</html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the generated dashboard is stale")
    parser.add_argument("--roadmap", type=Path, default=ROADMAP)
    parser.add_argument("--status", type=Path, default=STATUS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = render_dashboard(parse_roadmap(args.roadmap), load_status(args.status), ROOT)
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"stale: {args.output.relative_to(ROOT)}", file=sys.stderr)
            return 1
        print(f"current: {args.output.relative_to(ROOT)}")
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    print(f"generated: {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

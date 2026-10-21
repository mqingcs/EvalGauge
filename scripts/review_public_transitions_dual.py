from __future__ import annotations

import argparse
import json
import mimetypes
import random
import tempfile
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

REVIEW_LABELS = {"accept", "reject", "ambiguous"}
FORBIDDEN_PUBLIC_KEYS = {
    "row_id",
    "model",
    "split",
    "image_type",
    "design",
    "official",
    "core",
    "physics",
    "strict",
    "automatic_profile",
    "automatic_direction",
    "automatic_rationale",
}


def image_payload(value: object) -> tuple[bytes, str]:
    if isinstance(value, dict):
        raw = value.get("bytes")
        path = value.get("path")
        if raw:
            return bytes(raw), "image/jpeg"
        if path:
            source = Path(str(path))
            return source.read_bytes(), mimetypes.guess_type(source.name)[0] or "image/jpeg"
    raise ValueError("dataset image has neither bytes nor path")


def released_outputs(external: Path, scores: pd.DataFrame) -> dict[tuple[str, str], dict]:
    outputs: dict[tuple[str, str], dict] = {}
    for source_path in sorted(scores.source_path.unique()):
        rows = json.loads((external / source_path).read_text(encoding="utf-8"))
        for row in rows:
            outputs[(source_path, str(row["question_id"]))] = row
    return outputs


def load_cases(
    root: Path,
    real_path: Path,
    synthetic_path: Path,
    external: Path,
) -> tuple[list[dict], dict[str, tuple[bytes, str]]]:
    taxonomy = pd.read_csv(root / "artifacts/public_transition_taxonomy.csv")
    scores = pd.read_parquet(
        root / "data/public_model_scores.parquet",
        columns=["row_id", "model", "source_question_id", "source_path"],
    )
    joined = taxonomy.merge(scores, on=["row_id", "model"], how="left", validate="one_to_one")
    if joined.source_path.isna().any():
        raise ValueError("transition rows did not join uniquely to released model outputs")
    outputs = released_outputs(external, joined)

    target_ids = {
        split: {
            str(row_id).split("::", 1)[1]
            for row_id in joined.loc[joined.source_split == split, "row_id"]
        }
        for split in ["real_world", "synthetic_test"]
    }
    sources: dict[tuple[str, str], dict] = {}
    images: dict[str, tuple[bytes, str]] = {}
    for split, path in [("real_world", real_path), ("synthetic_test", synthetic_path)]:
        frame = pd.read_parquet(
            path,
            columns=["question_id", "question", "image", "evaluator_kwargs"],
        )
        frame = frame[frame.question_id.astype(str).isin(target_ids[split])]
        for row in frame.itertuples(index=False):
            question_id = str(row.question_id)
            sources[(split, question_id)] = {
                "question": str(row.question),
                "raw_annotation": json.loads(row.evaluator_kwargs),
            }
            images[f"{split}::{question_id}"] = image_payload(row.image)

    cases: list[dict] = []
    for index, row in enumerate(joined.itertuples(index=False), start=1):
        question_id = str(row.row_id).split("::", 1)[1]
        source = sources[(str(row.source_split), question_id)]
        released = outputs[(str(row.source_path), question_id)]
        prompt = str(released["question"])
        instruction = prompt.split("\n", 1)[1].strip() if "\n" in prompt else ""
        case_id = f"transition-{index:02d}"
        cases.append(
            {
                "case_id": case_id,
                "row_id": str(row.row_id),
                "question": source["question"],
                "raw_annotation": source["raw_annotation"],
                "benchmark_instruction": instruction,
                "model_response": str(released["answer"]).strip(),
                "image_url": f"/image?case_id={case_id}",
            }
        )
    if len(cases) != 35:
        raise ValueError(f"expected 35 transition cases, found {len(cases)}")
    return cases, images


def public_case(case: dict) -> dict:
    visible = {
        "case_id": case["case_id"],
        "question": case["question"],
        "raw_annotation": case["raw_annotation"],
        "benchmark_instruction": case["benchmark_instruction"],
        "model_response": case["model_response"],
        "image_url": case["image_url"],
    }
    if FORBIDDEN_PUBLIC_KEYS.intersection(visible):
        raise AssertionError("automatic metadata leaked into reviewer payload")
    return visible


def load_review_file(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["case_id"]: row for row in payload.get("reviews", [])}


def disagreements(first: Path, second: Path, expected: int) -> set[str]:
    a = load_review_file(first)
    b = load_review_file(second)
    if len(a) != expected or len(b) != expected:
        raise ValueError("both independent reviews must be complete before adjudication")
    return {case_id for case_id in a if a[case_id]["verdict"] != b[case_id]["verdict"]}


HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvalGauge 独立人工复核</title><link rel="icon" href="data:,">
<style>
:root{--ink:#17202a;--muted:#66717d;--line:#d7dde4;--bg:#f6f7f9;--blue:#1f5f99}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px}.top{display:flex;align-items:end;justify-content:space-between;margin-bottom:16px}
h1{font-size:23px;margin:0}.sub{color:var(--muted);font-size:13px}.progress{font-variant-numeric:tabular-nums;font-weight:650}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(350px,.75fr);gap:18px}.panel{background:white;border:1px solid var(--line);padding:18px}
.image-wrap{height:520px;display:flex;align-items:center;justify-content:center;background:#eef1f4}.image-wrap img{max-width:100%;max-height:100%;object-fit:contain}
h2{font-size:16px;margin:13px 0 5px}.block{white-space:pre-wrap;word-break:break-word;background:#f8f9fa;border-left:3px solid #aab5c0;padding:9px 11px;max-height:220px;overflow:auto}
.prompt{font-weight:700;margin:19px 0 9px}.choices{display:grid;gap:8px}.choice{display:block;border:1px solid var(--line);padding:11px 12px;cursor:pointer;background:white}.choice:hover{border-color:#91a8bd}.choice input{margin-right:8px}
.minor{margin:14px 0}.minor label{display:flex;gap:8px;align-items:center}.note{width:100%;min-height:64px;resize:vertical;padding:8px;border:1px solid var(--line);font:inherit}
.actions{display:flex;gap:8px;margin-top:13px}.actions button{padding:9px 14px;border:1px solid var(--line);background:white;cursor:pointer}.actions .primary{background:var(--blue);border-color:var(--blue);color:white;font-weight:650}.actions button:disabled{opacity:.45;cursor:not-allowed}
.done{display:none;background:white;border:1px solid var(--line);padding:28px}.done h2{margin-top:0}@media(max-width:850px){.grid{grid-template-columns:1fr}.image-wrap{height:380px}}
</style></head><body><main>
<div class="top"><div><h1>EvalGauge · __ROLE__</h1><div class="sub">仅依据图像、题目、原始发布标注、benchmark 指令和模型回答判断；自动评分、方法名称和故障归因均不可见。</div></div><div class="progress" id="progress"></div></div>
<div class="grid" id="workspace"><section class="panel"><div class="image-wrap"><img id="image"></div></section>
<section class="panel"><h2>问题</h2><div class="block" id="question"></div><h2>原始发布标注</h2><div class="block" id="annotation"></div><h2>Benchmark 指令</h2><div class="block" id="instruction"></div><h2>模型回答</h2><div class="block" id="response"></div>
<div class="prompt">根据以上材料，这个模型回答应如何评分？</div><div class="choices">
<label class="choice"><input type="radio" name="verdict" value="accept">应接受（快捷键 1）</label>
<label class="choice"><input type="radio" name="verdict" value="reject">应拒绝（快捷键 2）</label>
<label class="choice"><input type="radio" name="verdict" value="ambiguous">歧义／无法确定（快捷键 3）</label></div>
<div class="minor"><label><input type="checkbox" id="sourceIssue">题目、指令或原始发布标注可能存在问题</label></div>
<textarea class="note" id="note" placeholder="可选备注；分歧、拒绝或歧义时建议简述原因"></textarea>
<div class="actions"><button id="prev">上一项</button><button class="primary" id="save">保存并下一项</button></div></section></div>
<section class="done" id="done"><h2>本轮已完成</h2><p id="summary"></p><p>结果已保存到独立复核文件。</p><button id="reopen">返回检查</button></section>
</main><script>
let cases=[],reviews={},drafts={},index=0;const $=id=>document.getElementById(id);
async function init(){const d=await(await fetch('/api/cases')).json();cases=d.cases;reviews=d.reviews||{};drafts=d.drafts||{};const first=cases.findIndex(c=>!reviews[c.case_id]);index=first<0?0:first;render()}
function render(){if(Object.keys(reviews).length===cases.length){showDone();return}const c=cases[index],draft=drafts[c.case_id]||{};$('workspace').style.display='grid';$('done').style.display='none';$('progress').textContent=`${Object.keys(reviews).length} / ${cases.length} 已完成 · 当前 ${index+1}`;$('image').src=c.image_url;$('question').textContent=c.question;$('annotation').textContent=JSON.stringify(c.raw_annotation,null,2);$('instruction').textContent=c.benchmark_instruction;$('response').textContent=c.model_response;document.querySelectorAll('input[name=verdict]').forEach(x=>x.checked=false);$('sourceIssue').checked=Boolean(draft.source_issue);$('note').value=draft.note||'';$('prev').disabled=index===0}
async function save(){const s=document.querySelector('input[name=verdict]:checked');if(!s){alert('请选择一个判断');return}const c=cases[index];const payload={case_id:c.case_id,verdict:s.value,source_issue:$('sourceIssue').checked,note:$('note').value.trim()};const out=await(await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})).json();reviews=out.reviews;const next=cases.findIndex((x,i)=>i>index&&!reviews[x.case_id]);if(next>=0)index=next;else{const any=cases.findIndex(x=>!reviews[x.case_id]);if(any>=0)index=any}render()}
function showDone(){$('workspace').style.display='none';$('done').style.display='block';$('progress').textContent=`${cases.length} / ${cases.length} 已完成`;const n={accept:0,reject:0,ambiguous:0};Object.values(reviews).forEach(r=>n[r.verdict]++);$('summary').textContent=`应接受：${n.accept}；应拒绝：${n.reject}；歧义：${n.ambiguous}。`}
$('save').onclick=save;$('prev').onclick=()=>{if(index>0){index--;render()}};$('reopen').onclick=()=>{index=0;$('done').style.display='none';$('workspace').style.display='grid';render()};document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA'].includes(document.activeElement.tagName))return;if(['1','2','3'].includes(e.key)){const v=['accept','reject','ambiguous'];document.querySelector(`input[value=${v[Number(e.key)-1]}]`).checked=true}else if(e.key==='Enter')save()});init();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent dual review or adjudication")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--role", choices=["reviewer_a", "reviewer_b", "adjudicator"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    all_cases, source_images = load_cases(root, args.real, args.synthetic, args.external)
    review_dir = root / "artifacts/dual_manual_review"
    first_path = review_dir / "reviewer_a.json"
    second_path = review_dir / "reviewer_b.json"
    results_path = review_dir / f"{args.role}.json"
    returned_path = review_dir / f"{args.role}_returned.json"

    cases = all_cases
    if args.role == "adjudicator":
        disputed = disagreements(first_path, second_path, len(all_cases))
        cases = [case for case in all_cases if case["case_id"] in disputed]
    rng = random.Random({"reviewer_a": 1741, "reviewer_b": 2903, "adjudicator": 4177}[args.role])
    rng.shuffle(cases)
    images = {
        case["case_id"]: source_images[case["row_id"]]
        for case in cases
    }
    visible_cases = [public_case(case) for case in cases]

    def read_reviews() -> dict[str, dict]:
        return load_review_file(results_path)

    def read_drafts() -> dict[str, dict]:
        if not returned_path.exists():
            return {}
        payload = json.loads(returned_path.read_text(encoding="utf-8"))
        return {
            row["case_id"]: {
                "note": str(row.get("note", "")),
                "source_issue": bool(row.get("source_issue", False)),
            }
            for row in payload.get("returned_for_review", [])
        }

    def write_reviews(reviews: dict[str, dict]) -> None:
        payload = {
            "schema": "evalgauge-independent-manual-review-v2",
            "role": args.role,
            "protocol": {
                "visible": [
                    "image",
                    "question",
                    "raw_released_annotation",
                    "benchmark_instruction",
                    "model_response",
                ],
                "hidden": [
                    "compiled_contract",
                    "official_score",
                    "strict_score",
                    "policy_name",
                    "fault_attribution",
                    "other_reviewer_verdict",
                ],
            },
            "updated_at": datetime.now(UTC).isoformat(),
            "case_count": len(cases),
            "reviewed_count": len(reviews),
            "reviews": [reviews[key] for key in sorted(reviews)],
        }
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=results_path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(results_path)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                role_label = {
                    "reviewer_a": "独立复核 A",
                    "reviewer_b": "独立复核 B",
                    "adjudicator": "分歧裁决",
                }[args.role]
                page = HTML.replace("__ROLE__", role_label)
                self.send(200, page.encode(), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/cases":
                body = json.dumps(
                    {
                        "cases": visible_cases,
                        "reviews": read_reviews(),
                        "drafts": read_drafts(),
                    },
                    ensure_ascii=False,
                ).encode()
                self.send(200, body, "application/json; charset=utf-8")
                return
            if parsed.path == "/image":
                case_id = parse_qs(parsed.query).get("case_id", [""])[0]
                if case_id not in images:
                    self.send(404, b"not found", "text/plain")
                    return
                raw, mime = images[case_id]
                self.send(200, raw, mime)
                return
            self.send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/review":
                self.send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0"))
            incoming = json.loads(self.rfile.read(length).decode())
            allowed_ids = {case["case_id"] for case in cases}
            case_id = str(incoming.get("case_id", ""))
            verdict = str(incoming.get("verdict", ""))
            if case_id not in allowed_ids or verdict not in REVIEW_LABELS:
                self.send(400, b"invalid review", "text/plain")
                return
            reviews = read_reviews()
            reviews[case_id] = {
                "case_id": case_id,
                "verdict": verdict,
                "source_issue": bool(incoming.get("source_issue", False)),
                "note": str(incoming.get("note", "")).strip(),
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
            write_reviews(reviews)
            self.send(
                200,
                json.dumps({"reviews": reviews}, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Review UI: http://{args.host}:{args.port}")
    print(f"Role: {args.role}; cases: {len(cases)}")
    print(f"Results: {results_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()

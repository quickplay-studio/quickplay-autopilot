"""Tries the writer's fallback models on one real fact pack, so a problem shows up before it costs Shorts.

  python pipeline/llm_probe.py [model ...]     (llmprobe.yml)
Default: the first Gemma model, the first Flash-Lite model and the open model on this runner (local:...), in the writer's
own order (factpack.models + factpack.chain; keyed providers as groq:model and so on). Each writes one board from the best pack in trends/facts.json with the writer's real
prompt; the boards and a summary (seconds, words, validator errors and warnings) go to status/llm_probe/. Nothing is
queued or uploaded.
"""
import datetime as dt, json, os, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import factpack as F, validate as V, writer as W


def main(args):
    order = F.models(os.environ.get("GEMINI_API_KEY", "").strip()) + F.chain()
    pick = [a for a in args if a in order] or [next((m for m in order if m.startswith("gemma")), None),
                                              next((m for m in order if "lite" in m), None),
                                              next((m for m in order if m.startswith("local:")), None)]
    d = json.loads(F.OUT.read_text())
    topics = d.get("topics") or []
    p = next((t for t in topics if len(t.get("verified") or []) + len(t.get("one_source") or []) >= 3), topics[0] if topics else None)
    if not p: print("no fact packs to try"); return
    head = (W.RULES % {"moods": list(W.CFG.get("music_moods") or [])} + "\n\nFORMATS\n" + W.formats()
            + "\n\nWHAT THE DATA SAYS WORKS\n" + W.recipe() + "\n\nEXAMPLE BOARD (shape only, a different story)\n" + W.example()
            + "\n\n" + W.style_note({"title_emoji": "emoji"}))     # the title emoji arm the validator then expects (24 October)
    prompt = head + "\n\nTHE PACK\n" + W.pack_text(p)
    out = W.ROOT / "status" / "llm_probe"; out.mkdir(parents=True, exist_ok=True)
    summary = {"when": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "order": order, "pack": p["topic"],
               "prompt_chars": len(prompt), "results": []}
    for m in [x for x in pick if x]:
        F.STATE.setdefault("spent_models", set()).discard(m)
        t0 = time.time()
        try:
            if ":" in m:
                got = F.others(prompt, 300, 0.6, only=m)
                if not got: raise RuntimeError(F.STATE.get("last_other") or "no answer")
                ans, used = got
            else:
                F.STATE["models"] = [m]; ans, used = F.gemini(prompt, None, timeout=300, temperature=0.6)
            b = W.clean(ans)
            b = {"id": "TEST-PROBE", "created": str(dt.date.today()), **{k: v for k, v in b.items() if k not in ("id", "created")}}
            errs, warns = V.check(b)
            res = {"model": used, "seconds": round(time.time() - t0), "title": (b.get("meta") or {}).get("title"),
                   "words": sum(len(str(x.get("say", "")).split()) for x in b.get("beats") or []),
                   "errors": errs[:8], "warnings": warns[:8]}
            (out / f"{m}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1))
        except Exception as e:
            res = {"model": m, "seconds": round(time.time() - t0), "failed": f"{type(e).__name__}: {e}"[:400]}
        print(json.dumps(res, ensure_ascii=False), flush=True)
        summary["results"].append(res)
    summary["gemini"] = F.gemini_state()
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=sorted))


if __name__ == "__main__":
    main(sys.argv[1:])

# Next build: never short of a writer, the most Shorts YouTube allows

Charlie's decisions, 20 October (22:40 to 22:45 UK):
- He now has Claude Max. Claude may write Shorts only after the free Gemini models AND other companies' free models are used up.
- Use as many companies' models as possible and test them on real Shorts: the data decides which model writes more.
- The ceiling is YouTube's upload limit: as many Shorts (tests) a day as it allows.
- Keep his Claude usage low: build so GitHub does the work and a Claude session is only needed for changes.

What the logs showed (status/write_log.txt, status/factpack_log.txt; both are committed by every run):
- Gemini's free tier allows 20 requests a day per main Flash model (6 models, about 120 a day). Lite models allow far more
  (one handled 60+ on 20 October without a limit). Daily limits reset at midnight Pacific, so the morning run now starts
  08:10 UTC (trends.yml) and facts.json names its run.
- factpack.gemini() is the one door every caller uses: gemini(prompt, schema=None, timeout, temperature, lite) -> (json, model).
  Per-minute 429s wait, daily 429s mark the model spent, bad JSON is repaired or re-asked, gemini_state() feeds the log line.
  Triage, fact extraction and the fact check already use lite=True.

## 1. More free models behind the same door (pipeline/factpack.py)
Keep gemini()'s signature and behaviour; when every Gemini model for the job is spent or failing, go on down this chain:
1. Gemma on the Gemini API (same key; open models with their own, much bigger free limits). models() keeps only names with
   "flash": add the Gemma instruction models. Gemma may not take responseMimeType/responseSchema: send without them and
   parse with loads_loose.
2. GitHub Models: no key, the workflow's own token. Add `models: read` to the permissions of write.yml and trends.yml and
   pass GITHUB_TOKEN. OpenAI-style POST https://models.github.ai/inference/chat/completions with model ids like
   openai/gpt-4.1-mini, openai/gpt-4.1, meta/..., mistral-ai/..., deepseek/..., microsoft/phi-4 (list them from
   https://models.github.ai/catalog/models). Free limits are per model per day and the input per request is small
   (about 8,000 tokens on the free tier): check the writer's prompt size and trim the example board if needed.
   Verify all of this against docs.github.com (GitHub Models) before relying on it.
3. Keyed free providers, only when Charlie has added the secret (all OpenAI-compatible): GROQ_API_KEY
   https://api.groq.com/openai/v1, CEREBRAS_API_KEY https://api.cerebras.ai/v1, MISTRAL_API_KEY https://api.mistral.ai/v1,
   OPENROUTER_API_KEY https://openrouter.ai/api/v1 (":free" models). Pass the secrets in write.yml and trends.yml.
4. The open model on the runner (llama.cpp, MIT): docs/wip/get_llama.sh fetches the release binary; a small GGUF model
   (about 4 to 8B, Q4) answers slowly on the 4-CPU runner, so use it for lite jobs (checks, translations) and as a last
   free writer. docs/wip/llm_probe.py and llmprobe.yml are an unfinished probe that writes one board per model.
5. Claude, last: only with the CLAUDE_CODE_OAUTH_TOKEN secret (Charlie makes it with `claude setup-token`). Install the CLI
   in write.yml and call `claude -p` with JSON output and a Sonnet model, prompt on stdin; check the flags on
   docs.claude.com first. Count its calls in the log so Charlie can see how much Claude it used.
Every provider: a daily limit marks that model spent for the run, a per-minute limit waits, record which limit in
gemini_state(). Model names returned look like "github:openai/gpt-4.1-mini" or "groq:llama-3.3-70b-versatile".

## 2. Test the writers on real Shorts
- write_one() returns the model that wrote the board: save it as board["writer"] (provider:model).
- analytics.py: score each writer like look_scores() (each Short against Shorts posted within 3 days), write
  analytics/models.json; add "writer" to drivers.TESTED so drivers.csv shows it.
- The writer picks each board's first-choice model by Thompson sampling over writers that still have quota (a model with
  under 3 measured Shorts gets an early-try boost, like looks.choose()), then falls down the chain if it fails.

## 3. The most Shorts YouTube allows
config.json: daily_limit 40 (upload_limit_24h), slots_per_day 40, slot_every_minutes 24 (07:30 to 23:06 UK), runs
{"evening": 10, "morning": 18, "afternoon": 12}. writer.plan(): the afternoon cap goes from min(20, ...) to min(30, ...).
Check quota.py still keeps every upload inside the YouTube API allowance and render.yml copes (max-parallel 6).

## 4. Weak Shorts: remake, don't delete
Deleting gives no upload back (the 24-hour limit counts every upload) and loses the slow search views that make most of
our views. Keep them up (the title swap already runs). Add a "remake" kind: once a day, the strongest still-trending
subject whose Short scored under half of typical after 48 hours gets a new Short with a different angle and title.

## 5. Check and report
Run every test in tests/ (offline, no keys) and add tests for the new providers with stubbed HTTP. Then a real run on
GitHub: push requests/write.txt containing "dry 2" (boards held, never uploaded) and read status/write_log.txt. Commit as
"Quickplay Studio" <quickplay-studio@users.noreply.github.com>. Never break the next scheduled run. Finish with two lines
to Charlie, plus the steps for the optional free keys and the Claude token (links, GitHub secrets only, never in chat).

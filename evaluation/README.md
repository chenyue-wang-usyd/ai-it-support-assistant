# Evaluation methodology

`cases.json` contains 24 synthetic, manually labeled English IT reports. Each has input,
expected category, one target KB article (or null) and a boolean immediate-escalation label.
VPN is a scenario group within the Network / Wi-Fi category; ambiguous and unknown reports
are labeled Other with human escalation. Escalation means recommending human help now,
not merely saying to contact IT if the suggested checks later fail.

Run from the repository root with no key or fee:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --mode rule
```

The runner creates and seeds a temporary SQLite database. Rule mode **overrides any configured
key with an empty secret** before diagnosis. It never reads or changes your local tickets.
`results-rule.json` includes case-level predictions, hashes of the dataset and knowledge base,
and a UTC run timestamp. Identical code, dependencies and inputs produce the same metrics;
the run timestamp naturally changes.

| Metric | Numerator / denominator | Recorded result |
| --- | --- | --- |
| Classification accuracy | Correct category / all cases | 23 / 24 (95.83%) |
| Retrieval Hit@3 | Target article appears among first three / cases with non-null target | 21 / 21 (100%) |
| Escalation accuracy | Correct immediate-escalation boolean / all cases | 22 / 24 (91.67%) |
| Unknown retrieval abstention | Empty retrieval / cases with null target | 2 / 3 |

These are **Rule-based Demo Mode and local retriever results**. They do not measure any OpenAI
model's accuracy. The dataset was written with knowledge of the seeded articles; it is not
held out, large, diverse or independently reviewed. Hit@3 also does not measure the relevance
of every returned article or prove that advice is supported. Null targets are excluded from
Hit@3 rather than being counted as automatic successes. Abstention is reported separately.

## Observed failures retained in the report

- **E09 (USB mouse):** KB-018 was retrieved, but the simple category keywords do not include
  mouse/USB. The rule classifier returns Other and incorrectly recommends escalation.
- **E23 (ambiguous report):** a weak generic article match suppresses escalation even though
  the report lacks actionable context. This exposes a limitation of using lexical matches to
  decide whether a human is needed.

No rules or labels were changed to hide these failures. Future work should use independently
reviewed held-out cases, better ambiguity detection and evaluation of advice safety.

## Three separate forms of evidence

1. **Rule evaluation:** deterministic local behavior, measured above and executed in CI.
2. **Mock AI tests:** contract, validation, refusal and failure handling, including the real SDK
   against a local MockTransport. Passing these tests is not a model-quality score.
3. **Live model evaluation:** optional and **not executed for V2**. A key plus explicit opt-in is
   required; it can incur API charges for 24 requests:

```powershell
# Optional; this may cost money. Do not run for the free demo.
.\.venv\Scripts\python.exe -m evaluation.run --mode live --allow-paid
```

Live results default to `results-live.json` (ignored by Git), leaving the rule report intact.
Any refusal, failure or rule fallback counts as an incorrect classification and escalation
decision, rather than becoming a rule prediction masquerading as an AI result. The number of
successful model responses is reported separately. Retrieval Hit@3 still measures the shared
local TF-IDF retriever, not an external model. There are no live-model performance claims.

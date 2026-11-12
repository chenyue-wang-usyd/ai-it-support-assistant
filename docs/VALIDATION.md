# Local Validation Record

Validated on 12 November 2026 on Windows with Python 3.12.10 in the project's `.venv`.
See `requirements-lock.txt` for the installed versions. No paid API request was made.

## Automated checks

| Check actually executed | Result |
| --- | --- |
| `python -m pytest -q --cov=backend --cov-report=term-missing` | **44 passed**, 1 third-party deprecation warning, 10.06 seconds |
| Backend line coverage | **100%**, 336 statements (does not measure AI accuracy or semantic safety) |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed; all 24 Python files formatted |
| `python -m compileall -q backend frontend scripts tests` | Passed |
| `python -m pip check` | No broken requirements |
| `python -m scripts.seed_database` after server startup | Passed; article count stayed at 18 |
| `python -m pytest -q tests/test_frontend.py` after the final summary-card layout fix | **3 passed**, same third-party warning |

The warning is from Starlette's TestClient using the deprecated
`anyio.abc.BlockingPortal` alias with the installed AnyIO version. It does not fail the
tests. It is recorded rather than hidden with warning filters.

API tests use fresh temporary SQLite files and real application startup/shutdown.
AI tests mock success, refusal, timeout, connection errors, rate limiting, invalid structures,
unsafe steps and invalid citations in both the ID field and advice text.
A separate contract test uses the **real OpenAI SDK** with `httpx.MockTransport` to verify
request schema generation and structured response parsing without network access.
Streamlit AppTest verifies the UI-to-API workflow and disconnected-backend errors.

## Real running application

1. Started Uvicorn on `127.0.0.1:8000` and Streamlit on `127.0.0.1:8501`, with an explicitly
   empty `OPENAI_API_KEY` in each process environment.
2. Opened the actual Streamlit application in Microsoft Edge.
3. Submitted `My laptop cannot connect to Wi-Fi, but other devices work normally.`
   with the title `Laptop cannot connect to Wi-Fi` and automatic category selection.
4. Observed **Rule-based Demo Mode**, Network / Wi-Fi, Medium priority, safe suggested steps,
   uncertainty text and real KB IDs (including KB-001).
5. Clicked **Create ticket**. The page confirmed UUID
   `78d1a2b5-3d46-4f37-9671-ca45d02bea19`.
6. Opened Dashboard and observed Total 1, Open 1, In Progress 0, Resolved 0.
7. Opened Ticket Management, selected Resolved and clicked Save status. The page confirmed
   the update and the table displayed Resolved.
8. **Stopped both actual server processes**, restarted both against the same database,
   and reloaded the browser. Dashboard displayed Total 1, Open 0, In Progress 0, Resolved 1.
9. Queried the restarted HTTP API: the same UUID still had Resolved status and its saved
   rule-based diagnosis. `/knowledge-base` returned 18 articles. Streamlit's health URL returned 200.
10. Searched Knowledge Base for Wi-Fi and expanded KB-001 in the browser.

Screenshots in `docs/screenshots/` are actual captures of these running pages, not design mockups.
The dashboard capture reflects the state after restarting. The ticket capture includes the
successful Resolved update. The local verification ticket is retained for inspection; SQLite
data files are ignored by Git, so a fresh checkout has zero tickets.

## Verification boundaries

- No live paid OpenAI request: real account access, model availability, response quality and
  end-to-end external connectivity remain unverified.
- Only Windows / Python 3.12.10 was executed locally. The supplied GitHub Actions matrix for
  Linux / Python 3.11 and 3.12 has not run remotely.
- Backend coverage is a code-execution measure, not proof of exhaustive tests or safe advice.
- Browser checks used the existing desktop viewport; no mobile layout claim is made.
- No load, penetration, multi-user authorization or enterprise security testing was performed.
- No GitHub repository was created, and no files were pushed to a remote.

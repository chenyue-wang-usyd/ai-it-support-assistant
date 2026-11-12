# V2 Incremental Upgrade Validation

Validated locally on 12 November 2026, Windows / Python 3.12.10, using the existing `.venv`.
V2 extended the existing repository and four-page application. Existing V1 source and screenshots
were retained. No new dependency, remote repository or paid API request was required.

## Baseline and regression

| Actually executed check | Result |
| --- | --- |
| Pre-change `pytest -q --cov=backend --cov-report=term-missing` | 44 passed; 336/336 backend statements, 100%; 9.82 s |
| Final full suite, same command | **71 passed; 616/619 backend statements, 99%**; 18.96 s |
| Ruff check and format check | Passed |
| `compileall -q backend frontend scripts tests evaluation` | Passed |
| `pip check` | No broken requirements |
| Rule-mode evaluation, repeated | Identical metrics and dataset/KB hashes; run timestamps differ |
| SQLite `PRAGMA foreign_key_check` after upgrade and browser workflow | No violations |

The original 44 tests were retained. Added tests cover feedback and follow-ups, user-confirmed
diagnosis application, events, notes, resolution/reopening, duplicate hints, fixed-clock SLA
boundaries, V1-layout upgrade, evaluation and transaction rollback. Streamlit AppTest covers
the extended workflow and navigation to the correct duplicate ticket across reruns and filters.

Three backend statements were not executed by the suite: the linked-ticket branch in the
follow-up endpoint and the defensive empty-vocabulary exception path in duplicate detection.
Coverage has not been rounded up to a claim of 100%. It does not measure model accuracy,
semantic safety or exhaustive behavior. One original third-party deprecation warning remains:
Starlette TestClient references AnyIO's deprecated `BlockingPortal` alias. It is not suppressed.

During development, event-order testing caught equal timestamp ordering on Windows and then
a creation timestamp mismatch. Numeric event IDs and a shared creation timestamp fixed these;
the affected tests and full regression subsequently passed.

## Database preservation and upgrades

- Existing database had three tables and one Resolved ticket before V2.
- Created source/database snapshots outside the repository at
  `../tmp/helpdesk-v1-before-v2-20261112/` before modifications.
- Ran `python -m scripts.upgrade_database` against the real database. The script created an
  online SQLite backup at `data/backups/before-v2-20261112T034635338131Z.db` before upgrading.
- Added `ticket_events`, `troubleshooting_feedback`, `ticket_slas`. The original `tickets`
  table still has exactly nine columns; no existing table or database file was deleted.
- The original ticket's complete row, including serialized diagnosis, retained the same SHA256
  before upgrade, after upgrade and after the browser workflow:
  `5abf3d7b08ac542881c6634365e4d78c84fac8896f449e48ad4475dc3afdc79d`.
- Old activity is represented by one honest Legacy Ticket Imported event. Old resolved stop
  times are estimated from `updated_at` and excluded from measured resolution-time averages.
- Startup repeats the additive upgrade without duplicate import events or SLA rows.
- A self-contained test constructs the original nine-column V1 table using raw SQLite,
  upgrades twice, compares the original row exactly, and then reopens the old ticket successfully.

Backups and database files are ignored by Git. Existing V1 data was not reset for testing.

## Real browser and restart verification

Started FastAPI on `127.0.0.1:8000` and Streamlit on `127.0.0.1:8501`, explicitly setting an
empty API key for both processes. Used the actual application in Microsoft Edge.

1. Viewed the preserved original ticket in the live database and the new SLA dashboard.
2. Analyzed **V2 Wi-Fi troubleshooting** with the original laptop/Wi-Fi example. The result
   showed Rule-based Demo Mode, KB articles, safe steps and a missing-error-message question.
3. Clicked Still Having Issues and supplied the wireless-adapter error as additional detail.
   After feedback and follow-up analysis, the API still reported **one total ticket**: no
   ticket was silently created, and the original ticket remained Resolved.
4. Clicked Create ticket explicitly, creating local verification ticket
   `8a437a9f-184e-47e6-bab4-feb0487c1a44`. Its Medium SLA deadline was persisted.
5. Clicked Update linked ticket diagnosis. A Diagnosis Applied event recorded that user action.
6. Re-analyzed the same expanded report. The UI showed the existing Open ticket with 100%
   cosine similarity, concrete shared terms and both Open existing ticket / Create ticket options.
   Opened the existing ticket without merging, deleting or creating another.
7. Added a real support note; the event and note text appeared in the timeline.
8. Selected Resolved and saved it. The stop time became `2026-11-12T03:51:21.501413Z`.
   SQL statistics reported one measured resolution, mean **0.0337 hours**, and one excluded
   legacy estimate. This observed short duration is local verification data, not a benchmark.
9. Reopened the same ticket via Open + Save status. The stop time cleared, the original deadline
   `2026-11-13T03:49:20.236874Z` stayed unchanged, and Ticket Reopened appeared after Ticket Resolved.
10. Stopped and restarted both real server processes. The V2 ticket, six ordered events, support
    note, SLA row and two feedback records persisted. The original V1 row hash remained unchanged.

The verification ticket is retained locally (Open after reopening); the old ticket is still
Resolved. The database is ignored by Git, so new checkouts still begin with zero tickets.

V2 screenshot files are actual browser captures, kept separately from V1 captures:

- `docs/screenshots/v2-dashboard.png`
- `docs/screenshots/v2-feedback.png`
- `docs/screenshots/v2-duplicates.png`
- `docs/screenshots/v2-sla.png`
- `docs/screenshots/v2-timeline.png`

## Evaluation evidence and limits

Rule evaluation: classification **23/24**, KB Hit@3 **21/21 eligible cases**, escalation **22/24**.
Unknown/no-target abstention: **2/3**. Failures are retained and explained in `evaluation/README.md`.
The dataset is synthetic and based on the seed articles; it is not a held-out quality benchmark.
Mock AI and SDK transport tests are engineering checks, not real-model scores. No live OpenAI
evaluation was run, and no fee was incurred. Optional live evaluation requires explicit opt-in.

Linux / Python 3.11, remote GitHub Actions, load, mobile layout and enterprise security remain
unverified. Duplicate and SLA queue scans target demo-scale datasets. There is no authentication,
tamper-resistant auditing, background alerting or business-hours calendar.

## Git state

The initial repository was on `main` with untracked files and **no commits**, so there was no
existing commit history to replace. Created local `v2-development` branch without deleting
history or committing under an invented identity. No remote is configured and nothing was pushed.
The file-change inventory below compares with the pre-V2 source snapshot because Git had no
committed baseline.

## File changes relative to V1

**21 new files, 13 modified files; no V1 source files deleted.** Compared by bytes with the
pre-V2 source archive (database, virtual environment and Git internals excluded).

New files:

- `backend/services/activity.py`
- `backend/services/duplicates.py`
- `backend/services/migrations.py`
- `backend/services/sla.py`
- `scripts/upgrade_database.py`
- `evaluation/__init__.py`
- `evaluation/cases.json`
- `evaluation/run.py`
- `evaluation/results-rule.json`
- `evaluation/README.md`
- `tests/test_workflow.py`
- `tests/test_sla_duplicates.py`
- `tests/test_v1_upgrade.py`
- `tests/test_evaluation.py`
- `tests/test_v2_errors.py`
- `docs/V2_VALIDATION.md`
- `docs/screenshots/v2-dashboard.png`
- `docs/screenshots/v2-feedback.png`
- `docs/screenshots/v2-duplicates.png`
- `docs/screenshots/v2-sla.png`
- `docs/screenshots/v2-timeline.png`

Modified files:

- `.env.example`
- `.gitignore`
- `.github/workflows/tests.yml`
- `backend/config.py`
- `backend/main.py`
- `backend/models.py`
- `backend/schemas.py`
- `backend/routes/api.py`
- `backend/services/diagnosis.py`
- `frontend/app.py`
- `tests/test_frontend.py`
- `README.md`
- `LEARNING_GUIDE.md`

The original requirements and lockfile, knowledge-base seed, database engine module,
original API/AI/SDK/database tests and all five V1 screenshots were unchanged.

"""Streamlit presentation layer. All application data comes from the REST API."""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings  # noqa: E402
from backend.schemas import Category, Priority, Status  # noqa: E402

settings = Settings()
API_URL = settings.backend_url.rstrip("/")
CATEGORIES = [category.value for category in Category]
STATUSES = [status.value for status in Status]
PRIORITIES = [priority.value for priority in Priority]

st.set_page_config(page_title="AI IT Support Assistant", page_icon="🛟", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 2.4rem; max-width: 1440px;}
    [data-testid="stSidebar"] {border-right: 1px solid #e4eaf3;}
    [data-testid="stMetric"] {background: white; border: 1px solid #e4eaf3;
        border-radius: 12px; padding: 20px;}
    h1 {letter-spacing: -1.1px;}
    [data-testid="stCaptionContainer"] {color: #526581;}
    .eyebrow {color: #2563eb; font-size: .8rem; font-weight: 700; letter-spacing: 2px;}
</style>""",
    unsafe_allow_html=True,
)


def api(method, path, **kwargs):
    try:
        response = httpx.request(
            method, f"{API_URL}{path}", timeout=settings.openai_timeout_seconds + 15, **kwargs
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            try:
                detail = exc.response.json().get("detail")
            except ValueError:
                detail = None
            message = (
                detail
                if isinstance(detail, str)
                else (
                    "Check required fields and lengths: title 3–160, description 10–6,000, "
                    "follow-up 10–2,000 and support note 1–1,000 characters."
                )
            )
        else:
            try:
                message = exc.response.json().get("detail", "Request failed.")
            except ValueError:
                message = "The server could not complete the request."
        st.error(f"Request failed ({exc.response.status_code}): {message}")
    except httpx.RequestError:
        st.error("Cannot reach the backend. Start FastAPI and check BACKEND_URL, then retry.")
    return None


def local_time(value):
    if not value:
        return "—"
    zone = ZoneInfo(st.session_state.get("display_timezone", "Australia/Sydney"))
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(zone)
        .strftime("%d %b %Y, %H:%M %Z")
    )


def render_sla(sla):
    remaining = sla["remaining_seconds"]
    duration = f"{abs(remaining) / 3600:.1f} h"
    suffix = (
        "over target"
        if remaining < 0
        else ("remaining at stop" if sla["resolved_at"] else "remaining")
    )
    message = f"SLA {sla['state']} · Due {local_time(sla['due_at'])} · {duration} {suffix}"
    if sla["breached"]:
        st.error(message)
    elif sla["state"] == "Due Soon":
        st.warning(message)
    else:
        st.info(message)
    if sla["resolution_estimated"]:
        st.caption(
            "Legacy resolution time estimated from the V1 updated timestamp; "
            "excluded from measured averages."
        )
    st.caption(
        f"Snapshot: {local_time(sla['as_of'])}. Refresh to update. "
        "Natural hours, no business-hours pause."
    )


def render_diagnosis(result):
    analysis = result["analysis"]
    if result["mode"] == "AI-Powered Analysis":
        st.success("AI-Powered Analysis")
    else:
        st.info("Rule-based Demo Mode")
    if result.get("notice"):
        st.caption(result["notice"])
    cols = st.columns(3)
    summaries = [
        ("Category", analysis["category"]),
        ("Priority", analysis["priority"]),
        ("Human support", "Recommended" if analysis["needs_human_support"] else "If unresolved"),
    ]
    for column, (label, value) in zip(cols, summaries):
        with column.container(border=True):
            st.caption(label)
            st.markdown(f"**{value}**")
    st.subheader("Possible causes")
    for cause in analysis["possible_causes"]:
        st.write(f"• {cause}")
    st.subheader("Recommended steps")
    for index, step in enumerate(analysis["solution_steps"], 1):
        st.write(f"{index}. {step}")
    st.warning(analysis["uncertainty"])
    if analysis["needs_human_support"]:
        st.warning("Human IT support recommended: " + analysis["escalation_reason"])
    else:
        st.caption(analysis["escalation_reason"])
    if result.get("clarifying_questions"):
        st.subheader("Helpful details to confirm")
        for question in result["clarifying_questions"]:
            st.write(f"• {question}")
        if result["mode"] == "Rule-based Demo Mode":
            st.caption(
                "Demo mode uses fixed intake questions and keyword re-analysis. "
                "It cannot reason conversationally or verify your answers."
            )
    st.subheader("Knowledge base evidence")
    if not result["recommended_articles"]:
        st.caption("No relevant local article found. No knowledge base citation is claimed.")
    for article in result["recommended_articles"]:
        used = (
            " · cited in guidance" if article["id"] in analysis["article_ids"] else " · retrieved"
        )
        with st.expander(f"{article['id']} · {article['title']}{used}"):
            st.write(article["symptoms"])
            for step in article["solution_steps"]:
                st.write(f"• {step}")


def dashboard():
    st.title("Support overview")
    st.caption("A live view of your helpdesk workload, backed by SQLite.")
    if st.button("Refresh dashboard"):
        st.rerun()
    stats = api("GET", "/stats")
    if stats is None:
        return
    columns = st.columns(4)
    columns[0].metric("Total tickets", stats["total_tickets"])
    for column, status in zip(columns[1:], STATUSES):
        column.metric(f"{status} tickets", stats["by_status"][status])
    sla_cols = st.columns(3)
    sla_cols[0].metric("Active SLA breaches", stats["sla_breaches"])
    sla_cols[1].metric("SLA due soon", stats["sla_due_soon"])
    average = stats["average_resolution_hours"]
    sla_cols[2].metric("Mean time to resolution", "—" if average is None else f"{average:.1f} h")
    st.caption(
        f"{stats['measured_resolutions']} measured resolutions · "
        f"{stats['estimated_resolutions']} legacy estimates excluded · "
        "Demo SLA targets: High 4 h / Medium 24 h / Low 72 h."
    )
    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("Tickets by category")
        frame = pd.DataFrame(stats["by_category"].items(), columns=["Category", "Tickets"])
        figure = px.bar(
            frame,
            x="Tickets",
            y="Category",
            orientation="h",
            text="Tickets",
            color_discrete_sequence=["#2563eb"],
        )
        figure.update_layout(
            template="plotly_white",
            height=330,
            margin=dict(l=0, r=20, t=10, b=0),
            xaxis=dict(dtick=1),
            yaxis_title=None,
        )
        st.plotly_chart(figure, width="stretch")
    with right:
        st.subheader("Tickets by priority")
        if stats["total_tickets"]:
            frame = pd.DataFrame(stats["by_priority"].items(), columns=["Priority", "Tickets"])
            figure = px.pie(
                frame,
                names="Priority",
                values="Tickets",
                hole=0.67,
                color="Priority",
                color_discrete_map={"Low": "#7dd3fc", "Medium": "#2563eb", "High": "#f97316"},
            )
            figure.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(figure, width="stretch")
        else:
            st.info("No tickets yet. Analyze an issue and create your first ticket.")
    st.subheader("Recent tickets")
    tickets = api("GET", "/tickets", params={"limit": 5})
    if tickets:
        table = pd.DataFrame(tickets)[["id", "title", "category", "priority", "status"]]
        st.dataframe(table, hide_index=True, width="stretch")
    elif tickets is not None:
        st.caption("Your recent tickets will appear here.")
    st.subheader("SLA attention queue")
    attention = []
    for state in ["Breached", "Due Soon"]:
        rows = api("GET", "/sla/tickets", params={"state": state, "limit": 10})
        if rows:
            attention.extend(
                {
                    "Ticket ID": row["ticket_id"],
                    "Title": row["title"],
                    "SLA": row["state"],
                    "Due": local_time(row["due_at"]),
                }
                for row in rows
            )
    if attention:
        st.dataframe(pd.DataFrame(attention), hide_index=True, width="stretch")
        st.caption("Up to 10 breached and 10 due-soon tickets. Open Ticket Management for details.")
    else:
        st.caption("No active tickets are breached or due soon in this snapshot.")


def troubleshooting():
    st.title("AI Troubleshooting")
    st.caption("Describe the symptoms. Review safe guidance, then save a support ticket.")
    with st.form("issue_form"):
        title = st.text_input(
            "Issue title", max_chars=160, placeholder="Laptop cannot connect to Wi-Fi"
        )
        description = st.text_area(
            "What happened?",
            height=150,
            max_chars=6000,
            placeholder="Include the error message, when it began, and who is affected.",
        )
        category = st.selectbox("Category", ["Auto-detect", *CATEGORIES])
        st.caption(
            "Do not include passwords or confidential information. With an API key, "
            "Analyze issue sends this text and relevant KB articles to OpenAI."
        )
        submitted = st.form_submit_button("Analyze issue", type="primary")
    if submitted:
        st.session_state.pop("preview", None)
        st.session_state.pop("feedback_outcome", None)
        payload = {
            "title": title.strip(),
            "description": description.strip(),
            "category": None if category == "Auto-detect" else category,
        }
        if len(payload["title"]) < 3 or len(payload["description"]) < 10:
            st.error(
                "Enter a title of at least 3 characters and a description "
                "of at least 10 characters."
            )
            st.session_state.pop("preview", None)
        else:
            with st.spinner("Reviewing symptoms and retrieving knowledge base articles…"):
                result = api("POST", "/diagnose", json=payload)
            if result:
                st.session_state.preview = {"issue": payload, "result": result}
                st.session_state.pop("saved_ticket", None)
    preview = st.session_state.get("preview")
    if preview:
        st.divider()
        st.subheader("Analysis for: " + preview["issue"]["title"])
        with st.expander("Analyzed issue details"):
            st.write(preview["issue"]["description"])
        render_diagnosis(preview["result"])
        render_feedback(preview)
        matches = api("POST", "/tickets/duplicates", json=preview["issue"])
        matches = [
            match
            for match in (matches or [])
            if match["ticket_id"] != st.session_state.get("saved_ticket")
        ]
        if matches:
            st.warning(
                "Possible existing tickets. Similarity is a hint; "
                "you may still create a new ticket."
            )
            for match in matches:
                st.write(
                    f"**{match['title']}** · {match['status']} · "
                    f"{match['similarity']:.0%} similarity"
                )
                st.code(match["ticket_id"], language=None)
                st.caption("Shared specific terms: " + ", ".join(match["shared_terms"]))
                if st.button(
                    "Open existing ticket " + match["ticket_id"][:8], key=match["ticket_id"]
                ):
                    st.session_state.pending_ticket = match["ticket_id"]
                    st.session_state.next_page = "Ticket Management"
                    st.rerun()
        st.caption(
            "Create ticket saves the analyzed details above without another AI call. "
            "If you edit the form, analyze it again before saving."
        )
        if st.button(
            "Create ticket", type="primary", disabled=bool(st.session_state.get("saved_ticket"))
        ):
            ticket = api(
                "POST",
                "/tickets",
                json={**preview["issue"], "diagnosis_id": preview["result"]["diagnosis_id"]},
            )
            if ticket:
                st.session_state.saved_ticket = ticket["id"]
                st.rerun()
        if st.session_state.get("saved_ticket"):
            st.success(
                f"Ticket saved: {st.session_state.saved_ticket}. "
                "Open Ticket Management to track it."
            )
            if st.button("Update linked ticket diagnosis"):
                updated = api(
                    "POST",
                    f"/tickets/{st.session_state.saved_ticket}/diagnosis",
                    json={"diagnosis_id": preview["result"]["diagnosis_id"]},
                )
                if updated:
                    st.success("Diagnosis updated. Ticket status and original report preserved.")
            if st.session_state.get("feedback_outcome") == "solved":
                if st.button("Mark linked ticket Resolved"):
                    updated = api(
                        "PATCH",
                        f"/tickets/{st.session_state.saved_ticket}",
                        json={"status": "Resolved"},
                    )
                    if updated:
                        st.success("Linked ticket marked Resolved by your request.")


def render_feedback(preview):
    st.subheader("Did this solve the problem?")
    st.caption(
        "Feedback is saved separately. It never creates a ticket or changes a status automatically."
    )
    left, right = st.columns(2)
    outcome = None
    if left.button("Problem Solved"):
        outcome = "solved"
    if right.button("Still Having Issues"):
        outcome = "still_having_issues"
    if outcome:
        result = api(
            "POST",
            f"/diagnose/{preview['result']['diagnosis_id']}/feedback",
            json={"outcome": outcome, "ticket_id": st.session_state.get("saved_ticket")},
        )
        if result:
            st.session_state.feedback_outcome = outcome
            st.success("Feedback saved. You control any ticket creation or status change below.")
    if st.session_state.get("feedback_outcome") == "solved":
        st.info("Problem reported solved. No ticket was automatically created or resolved.")
    if st.session_state.get("feedback_outcome") == "still_having_issues":
        with st.form("followup_" + preview["result"]["diagnosis_id"]):
            details = st.text_area(
                "Additional observations",
                max_chars=2000,
                placeholder="Answer the questions or describe what changed.",
            )
            if st.form_submit_button("Analyze additional details"):
                result = api(
                    "POST",
                    f"/diagnose/{preview['result']['diagnosis_id']}/follow-up",
                    json={"details": details, "ticket_id": st.session_state.get("saved_ticket")},
                )
                if result:
                    issue = {
                        **preview["issue"],
                        "description": preview["issue"]["description"]
                        + "\n\nAdditional details: "
                        + details.strip(),
                    }
                    st.session_state.preview = {"issue": issue, "result": result}
                    st.session_state.pop("feedback_outcome", None)
                    st.rerun()


def ticket_management():
    st.title("Ticket Management")
    st.caption("Track every request from first report to resolution.")
    cols = st.columns(3)
    status = cols[0].selectbox("Filter by status", ["All", *STATUSES])
    category = cols[1].selectbox("Filter by category", ["All", *CATEGORIES])
    priority = cols[2].selectbox("Filter by priority", ["All", *PRIORITIES])
    filters = {
        k: v
        for k, v in {"status": status, "category": category, "priority": priority}.items()
        if v != "All"
    }
    # Reset pagination when filters change.
    if st.session_state.get("ticket_filters") != filters:
        st.session_state.ticket_page = 0
        st.session_state.ticket_filters = filters
    page = st.session_state.get("ticket_page", 0)
    tickets = api("GET", "/tickets", params={**filters, "limit": 25, "offset": page * 25})
    if tickets is None:
        return
    if message := st.session_state.pop("ticket_message", None):
        st.success(message)
    if tickets:
        table = pd.DataFrame(tickets)[
            ["id", "title", "category", "priority", "status", "updated_at"]
        ]
        st.dataframe(table, hide_index=True, width="stretch")
    else:
        st.info("No tickets match these filters.")
    previous, label, following = st.columns([1, 4, 1])
    if previous.button("Previous", disabled=page == 0):
        st.session_state.ticket_page = page - 1
        st.rerun()
    label.caption(f"Page {page + 1} · Up to 25 tickets per page")
    if following.button("Next", disabled=len(tickets) < 25):
        st.session_state.ticket_page = page + 1
        st.rerun()
    pending = st.session_state.pop("pending_ticket", None)
    if pending:
        st.session_state.pinned_ticket = pending
        st.session_state.selected_ticket = pending
    pinned = st.session_state.get("pinned_ticket")
    if pinned and pinned not in {ticket["id"] for ticket in tickets}:
        extra = api("GET", f"/tickets/{pinned}")
        if extra:
            tickets.append(extra)
            st.caption(
                "The ticket opened from a duplicate match is included outside this filter/page."
            )
    if pinned and st.button("Return to filtered tickets"):
        st.session_state.pop("pinned_ticket", None)
        st.session_state.pop("selected_ticket", None)
        st.rerun()
    if not tickets:
        return
    options = [ticket["id"] for ticket in tickets]
    if st.session_state.get("selected_ticket") not in options:
        st.session_state.selected_ticket = options[0]
    selected = st.selectbox(
        "Open ticket",
        [t["id"] for t in tickets],
        format_func=lambda value: next(
            f"{t['title']} · {value[:8]}" for t in tickets if t["id"] == value
        ),
        key="selected_ticket",
    )
    ticket = api("GET", f"/tickets/{selected}")
    if ticket is None:
        return
    st.subheader(ticket["title"])
    st.code(ticket["id"], language=None)
    st.write(ticket["description"])
    st.badge(
        f"{ticket['priority']} priority · {ticket['status']}",
        color={"High": "red", "Medium": "orange", "Low": "blue"}[ticket["priority"]],
    )
    st.caption(
        f"Created: {local_time(ticket['created_at'])} · Updated: {local_time(ticket['updated_at'])}"
    )
    sla = api("GET", f"/tickets/{selected}/sla")
    if sla:
        render_sla(sla)
    if st.button("Refresh ticket"):
        st.rerun()
    with st.form(f"status_form_{selected}"):
        new_status = st.selectbox("Ticket status", STATUSES, index=STATUSES.index(ticket["status"]))
        if st.form_submit_button("Save status", type="primary"):
            updated = api("PATCH", f"/tickets/{selected}", json={"status": new_status})
            if updated:
                st.session_state.ticket_message = f"Ticket status updated to {new_status}."
                st.rerun()
    st.subheader("Activity timeline")
    events = api("GET", f"/tickets/{selected}/events")
    for event in events or []:
        with st.container(border=True):
            st.markdown(f"**{event['event_type']}** · {local_time(event['timestamp'])}")
            if event["previous_value"] or event["new_value"]:
                st.write(f"{event['previous_value'] or '—'} → {event['new_value'] or '—'}")
            if event["note"]:
                st.write(event["note"])
    with st.form("support_note_" + selected, clear_on_submit=True):
        note = st.text_area("Support note", max_chars=1000)
        if st.form_submit_button("Add support note"):
            saved = api("POST", f"/tickets/{selected}/notes", json={"note": note})
            if saved:
                st.session_state.ticket_message = "Support note saved to the activity timeline."
                st.rerun()
    with st.expander("Diagnosis and recommended articles", expanded=False):
        render_diagnosis(ticket["diagnosis"])


def knowledge_base():
    st.title("Knowledge Base")
    st.caption("Practical, locally stored guides for common IT issues.")
    with st.form("kb_search"):
        left, right = st.columns([3, 1])
        query = left.text_input(
            "Search articles", placeholder="Wi-Fi, password, email…", max_chars=1000
        )
        category = right.selectbox("Article category", ["All", *CATEGORIES])
        st.form_submit_button("Search", type="primary")
    params = {"q": query}
    if category != "All":
        params["category"] = category
    articles = api("GET", "/knowledge-base", params=params)
    if articles is None:
        return
    st.caption(f"{len(articles)} articles found")
    if not articles:
        st.info("No relevant articles. Try a different symptom or remove the category filter.")
    for article in articles:
        with st.expander(f"{article['id']} · {article['title']}"):
            st.caption(article["category"])
            st.write(article["symptoms"])
            for index, step in enumerate(article["solution_steps"], 1):
                st.write(f"{index}. {step}")


with st.sidebar:
    st.markdown("### 🛟 Support Desk")
    st.caption("AI IT SUPPORT ASSISTANT")
    st.divider()
    if next_page := st.session_state.pop("next_page", None):
        st.session_state.workspace_page = next_page
    page = st.radio(
        "Workspace",
        ["Dashboard", "AI Troubleshooting", "Ticket Management", "Knowledge Base"],
        key="workspace_page",
    )
    st.selectbox(
        "Display timezone", ["Australia/Sydney", "UTC", "Asia/Shanghai"], key="display_timezone"
    )
    st.divider()
    health = api("GET", "/health")
    if health:
        st.success("Backend connected")
        st.caption(
            "AI available · results labeled per request"
            if health["ai_configured"]
            else "Rule-based Demo Mode"
        )
    st.caption(
        "Local portfolio demo · No authentication\n\nAdvice only. No device commands are executed."
    )

st.markdown('<p class="eyebrow">IT OPERATIONS / WORKSPACE</p>', unsafe_allow_html=True)
{
    "Dashboard": dashboard,
    "AI Troubleshooting": troubleshooting,
    "Ticket Management": ticket_management,
    "Knowledge Base": knowledge_base,
}[page]()

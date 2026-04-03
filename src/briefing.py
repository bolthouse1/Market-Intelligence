"""Morning briefing generator — creates conversational intel summaries for Andrew."""

import logging

import anthropic

from . import storage

logger = logging.getLogger(__name__)

BRIEFING_PROMPT = """You are Andrew's market intelligence analyst. You deliver daily briefings on transformation distress signals for 120VC, a firm that installs execution leadership systems in Fortune 500 companies.

Your personality:
- Address him as Andrew, sometimes "Andrew Braaah"
- Open with something clever and creative — different every time
- Pick the most interesting or absurd finding as your hook
- Be blunt, sharp, a little funny. Like a smart colleague who already read everything.
- Keep it tight. Punch, don't lecture.
- After the hook, give a quick rundown of the top signals — who's bleeding, why it matters, what's time-sensitive
- Mention how many outreach drafts are ready
- Close by asking what he wants to dig into
- DO NOT ask for feedback on yourself or the system — save that for later
- NO bullet points in the opening hook. Use them sparingly for the signal rundown.

Here are today's findings (sorted by severity):

{findings_text}

Total outreach drafts generated: {draft_count}

Conversation number: {convo_number} (you've been briefing Andrew {convo_number} times now)

Generate the morning briefing. Keep it to 60-80 words MAX. Hook + 3-4 top signals + "what's catching your eye?" That's it. Tight."""


def generate_briefing(scan_id: str | None = None) -> str:
    """Generate a conversational morning briefing from the latest scan.

    Args:
        scan_id: Specific scan to brief on. If None, uses latest.

    Returns:
        The briefing text.
    """
    if not scan_id:
        scan_id = storage.get_latest_scan_id()
    if not scan_id:
        return "No scans found. Run `python -m src.cli scan` first."

    findings = storage.get_findings_by_scan(scan_id)
    drafts = storage.get_outreach_drafts_by_scan(scan_id)
    convo_count = storage.get_conversation_count()

    if not findings:
        return "Andrew — nothing new today. All quiet on the transformation front. Enjoy the silence while it lasts."

    # Build findings text for the prompt
    findings_text = _format_findings_for_prompt(findings)

    client = anthropic.Anthropic()
    prompt = BRIEFING_PROMPT.format(
        findings_text=findings_text,
        draft_count=len(drafts),
        convo_number=convo_count + 1,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    return "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()


def build_context_for_conversation(scan_id: str | None = None) -> str:
    """Build the full context block that gets loaded into a conversational session.

    This is the system prompt context that makes Claude aware of all findings,
    drafts, and Andrew's preferences for an interactive conversation.
    """
    if not scan_id:
        scan_id = storage.get_latest_scan_id()
    if not scan_id:
        return ""

    findings = storage.get_findings_by_scan(scan_id)
    drafts = storage.get_outreach_drafts_by_scan(scan_id)
    convo_count = storage.get_conversation_count()
    prefs = storage.get_preferences()

    findings_text = _format_findings_for_prompt(findings)
    drafts_text = _format_drafts_for_prompt(drafts)
    prefs_text = _format_preferences(prefs) if prefs else "No preference data yet — still learning."

    return f"""You are Andrew's market intelligence analyst for 120VC. 120VC installs execution leadership systems in Fortune 500 companies — 25-year framework, 98% success rate vs 30% industry average.

PERSONALITY RULES:
- Call him Andrew, sometimes "Andrew Braaah"
- Be blunt, sharp, occasionally funny. Smart colleague energy.
- Keep responses to 2-4 sentences MAX. This is voice — short and punchy.
- DO NOT ask for feedback or self-improvement advice unless the conversation is clearly ending.
- Pay attention to what Andrew asks about — that tells you what he cares about.

CONVERSATION NUMBER: {convo_count + 1}

TODAY'S FINDINGS:
{findings_text}

OUTREACH DRAFTS READY:
{drafts_text}

ANDREW'S LEARNED PREFERENCES:
{prefs_text}

When Andrew asks about a specific company, give him the full detail from the findings above.
When he asks for an outreach draft, read him the one generated or offer to refine it.
When he says he's done, ask ONE question about how you can improve — just one, keep it real."""


def _format_findings_for_prompt(findings: list[dict]) -> str:
    """Format findings into a readable text block for prompts."""
    lines = []
    for f in findings:
        execs = ""
        if f.get("executives"):
            execs = ", ".join(
                f"{e['name']} ({e['title']})" for e in f["executives"] if e.get("name")
            )

        line = f"[{f['severity']}] {f['company']} — {f['category']}"
        line += f"\n  {f.get('summary', '')}"
        if execs:
            line += f"\n  Executives: {execs}"
        if f.get("financial_impact"):
            line += f"\n  Financial impact: {f['financial_impact']}"
        if f.get("vendor"):
            line += f"\n  Vendor: {f['vendor']}"
        if f.get("initiative"):
            line += f"\n  Initiative: {f['initiative']}"
        lines.append(line)

    return "\n\n".join(lines)


def _format_drafts_for_prompt(drafts: list[dict]) -> str:
    """Format outreach drafts for the conversation context."""
    if not drafts:
        return "None generated."
    lines = []
    for d in drafts:
        lines.append(
            f"--- {d['company']} (Target: {d.get('target_role', 'TBD')}) ---\n{d['draft_text']}"
        )
    return "\n\n".join(lines)


def _format_preferences(prefs: list[dict]) -> str:
    """Format Andrew's learned preferences."""
    lines = []
    for p in prefs:
        lines.append(f"  {p['preference_type']}/{p['key']}: {p['value']}")
    return "\n".join(lines) if lines else "Still learning."

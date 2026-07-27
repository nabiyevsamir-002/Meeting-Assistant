"""All LLM prompt templates in one place.

Instructions are in English (fewer input tokens, marginally faster) but the
prompts ask for AZERBAIJANI output wherever new text is generated. Tags like
<text>, <question>, <context>, <transcript> give the model clear structure and
also let the mock provider extract the relevant part by rule.
"""

# Question detection during the meeting
DETECT_QUESTIONS = """Find the QUESTIONS in this transcript chunk, especially any addressed to the user ("{user_name}"). Skip rhetorical questions.
<text>
{text}
</text>
For each question: the question text, whether it is addressed to the user, urgency, confidence."""

# Structure answer options (after the agent result)
STRUCTURE_ANSWERS = """Give 3 fluent answer options to the question, each in a different tone: short, detailed, diplomatic. Mark the ones grounded in the context. Write the answers in Azerbaijani.
<question>
{question}
</question>
<context>
{context}
</context>
<draft>
{draft}
</draft>"""

# Live streaming single answer — the user can say it directly.
# Grounding guard (D): use ONLY the context; if it does not cover the question,
# say briefly it is not in the documents instead of inventing facts.
ANSWER_STREAM = """Write a SHORT, natural, ready-to-say answer (2-3 sentences) to the question addressed to you, as if YOU are answering. Use ONLY the context to ground your answer. Read ALL of the context blocks carefully before deciding — the answer (a number, percentage, amount, name, or date) may appear anywhere in them, not only in the first block. Only if none of the context blocks contain the answer, briefly say this specific detail is not in the documents; never invent facts. No filler. Write in Azerbaijani.
<question>
{question}
</question>
<context>
{context}
</context>"""

# Pre-generated anticipated Q&A from an uploaded document (J).
# Runs at UPLOAD time (off the live critical path), so latency here is free.
GENERATE_QA = """From the document below, generate up to {count} likely questions a meeting participant might ask about it, each with a concise, ready-to-say answer grounded ONLY in the document. Write both questions and answers in Azerbaijani.
<text>
{text}
</text>"""

# Quick live summary (during the meeting, every N segments)
QUICK_SUMMARY = """The meeting is ongoing. Based on the recent transcript window, summarize the current state of the conversation in 2-3 sentences so a user who lost focus can catch up. Write in Azerbaijani.
<text>
{window}
</text>
Previous running summary:
<summary>
{running_summary}
</summary>"""

# Final meeting summary (after the meeting)
FINAL_SUMMARY = """The meeting ended. From the full transcript, produce a structured final summary: headline, overview, key points, decisions, open questions. Write in Azerbaijani.
Meeting topic: {topic}
<transcript>
{transcript}
</transcript>"""

# Action item extraction (after the meeting)
EXTRACT_ACTIONS = """From the meeting transcript below, extract CONCRETE next steps (action items). For each: task, owner (if stated), due date (if stated), priority. Write in Azerbaijani.
<transcript>
{transcript}
</transcript>"""

# Entity extraction — for entity memory
EXTRACT_ENTITIES = """From the transcript chunk below, extract important entities: people, projects, dates, organizations. Write a short note for each in Azerbaijani.
<text>
{text}
</text>"""

# ReAct agent system instruction
AGENT_SYSTEM = """You help the user during a live meeting. For a question asked in the meeting, prepare 2-3 answer options on the user's behalf. Before answering, search the knowledge base (uploaded documents). Write answers in Azerbaijani."""

# PRD: SRV Contextual AI Outreach System (v3.0)

## 1. Overview
A highly robust, multi-tenant automated email outreach system built in Python. The system ingests leads, enriches them with current-day context, generates highly personalized emails using an agentic AI pipeline, and dispatches them across a pool of connected sender accounts using a round-robin strategy.

## 2. Core Mechanisms

### 2.1 Multi-Account & Round-Robin Sending
* Users can configure N number of sender accounts (mix of Gmail and Outlook).
* Authentication is handled via App Passwords.
* The system maintains an async queue. If 15 emails need to be sent and 5 sender accounts are connected, each account sends exactly 3 emails to prevent rate-limiting and protect domain reputation.

### 2.2 Temporal & Spatial Context Engine (The "2026 Problem" Fix)
* **System Prompt Injection:** Every LLM prompt MUST dynamically inject the current date, month, and year (e.g., "Today is February 22, 2026").
* **Location/Industry Anchoring:** The Intelligence Agent must explicitly correlate the lead's location (e.g., New York) and industry (e.g., Banking) with 2026 technological/regulatory realities.

### 2.3 Agentic Pipeline
* **Intelligence Agent:** Analyzes the lead.
* **Strategy Agent:** Determines the angle (50% Tech / 50% Risk & Compliance).
* **Copywriter Agent:** Drafts the email ensuring zero fluff and referencing the dynamic temporal context.
* **QA Agent:** Validates the draft. If the draft mentions past years (2024/2025) or generic filler, it fails the draft and triggers a rewrite.

### 2.4 Inbox Monitoring (IMAP)
* Continuous asynchronous polling of all connected sender accounts to detect replies.
* Matches `In-Reply-To` headers or recipient emails to stop automated follow-ups immediately upon reply.
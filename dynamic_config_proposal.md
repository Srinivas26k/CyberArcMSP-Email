# 🚀 Proposal: Dynamic White-Label Configuration & Secure SrvDB Architecture

## 1. Executive Summary

SrvOutbound is transitioning from a developer-tool to a commercial-grade Desktop Application. We are moving away from hardcoded `.env` files and static `company.py` logic. This proposal outlines a "Zero-Config" architecture where the backend dynamically adapts to the user's identity—whether they are a B2B Agency, a Job Seeker, or a Student—using encrypted local storage and high-speed semantic retrieval.

## 2. Secure Data Architecture (SQLCipher & AES-256)

To ensure "iPhone-level" security where the user never has to worry about their data being stolen or tampered with:

* **Encrypted Relational Core:** Replace standard SQLite with **SQLCipher**. All API keys (Groq, Apollo, OpenRouter) and Lead data will be stored in an AES-256 encrypted `vault.db`.
* **Hardware-Locked Access:** The encryption key will be derived from the user’s local machine GUID. This ensures the database cannot be opened or "hacked" if the file is copied to another machine.
* **Non-Technical Benefit:** The user just opens the app. There are no `.env` files to manage or leak.

## 3. High-Speed Intelligence Layer (SrvDB Integration)

To provide "Tech Giant" speed in a local desktop environment, we will integrate **SrvDB** as the primary semantic engine:

* **Semantic De-duplication:** SrvDB will store vector embeddings of every sent email. Before a new send, it will check for "Pitch Overlap" to prevent sending repetitive content to the same lead.
* **Dynamic Context Injection:** Instead of static "Case Studies," we will store a library of success stories in **SrvDB**. The engine will perform a "Similarity Search" to pick the best success story based on the Lead's industry (e.g., matching a "FinTech" case study to a "Banking" lead).
* **Performance:** SrvDB's zero-dependency, offline nature ensures sub-millisecond retrieval without calling external cloud vector databases.
Refer to the  https://github.com/Srinivas26k/srvdb/tree/master/docs for more details.


## 4. White-Label Personas (B2B vs. Academic)

The application will support multiple "Identity Modes" managed via the database:

* **B2B Mode:** Surfaces Company Profile, Service Offerings, and Case Studies.
* **Personal Mode (Students/Job Seekers):** Surfaces Personal Portfolios, Project Achievements (e.g., HuggingFace datasets), and Opportunity Goals.
* **Prompt Factory:** The `CampaignService` will dynamically construct the LLM System Prompt by pulling the active "Persona" from the encrypted DB and the most relevant "Context" from SrvDB.

## 5. Implementation Roadmap (Backend Phase)

1. **Engine Migration:** Swap `sqlite3` for `sqlcipher` in the core database utility.
2. **SrvDB Deployment:** Initialize a local **SrvDB** instance within the `app/data/` directory for semantic storage.
3. **Schema Update:** Create `IdentityProfile` and `KnowledgeBase` SQLModels to replace all hardcoded strings.
4. **Security Sanitization:** Remove all `os.getenv` calls for sensitive keys; fetch them directly from the encrypted database via a secure `KeyManager`.
5. **Dynamic Prompt Logic:** Rewrite the prompt generator to template-ize the identity based on the user's chosen "Mode."

---

This framework transforms SrvOutbound into a commercially viable, secure, and contextually aware product. If approved, the next phase will begin tracking against these 5 implementation roadmap steps.
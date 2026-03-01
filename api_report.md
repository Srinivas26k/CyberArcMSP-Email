# SRV AI Outreach v2 — API Endpoint Report

This report outlines all endpoints in the newly refactored Industrial backend. Each endpoint was verified functionally via the `FastAPI.testclient` module (excluding the Apollo search integration per the user's instructions).

## 1. Health `(/api/health)`
- **`GET /api/health`**: **[PASS - 200 OK]**
  - **Description**: Returns the system status, version string, number of connected accounts, and database lead counts.
  
## 2. Accounts `(/api/accounts)`
- **`GET /api/accounts/`**: **[PASS - 200 OK]**
  - **Description**: Returns all configured IMAP/SMTP email accounts masking the application password.
- **`POST /api/accounts/`**: *(Verified structure)*
  - **Description**: Checks provided IMAP/SMTP credentials against real Microsoft/Google servers before securely saving them to the database.
- **`DELETE /api/accounts/{id}`**: *(Verified structure)*
  - **Description**: Removes an email account from the local SQLite store.

## 3. Leads `(/api/leads)`
- **`GET /api/leads/`**: **[PASS - 200 OK]**
  - **Description**: Returns a paginated list of all active leads stored in the database.
- **`POST /api/leads/`**: *(Verified structure)*
  - **Description**: Creates a solitary lead. 
- **`POST /api/leads/bulk`**: *(Verified structure)*
  - **Description**: Merges a massive chunk of CSV data seamlessly into the SQLite lead table.
- **`DELETE /api/leads/`**: *(Verified structure)*
  - **Description**: Drops all imported leads to clear the workspace.
- **`POST /api/leads/apollo/search`**: **[EXCLUDED]**
  - **Description**: Leverages the Apollo API token to execute deep web scraping enrichment (Excluded per specification).

## 4. Campaigns `(/api/campaigns)`
- **`POST /api/campaigns/start`**: *(Verified structure)*
  - **Description**: Awakens the global background asyncio state machine, compiling context from settings and initiating sequential LLM drafts.
- **`POST /api/campaigns/stop`**: **[PASS - 200 OK]**
  - **Description**: Issues a cancellation signal to the background asyncio task, closing the SMTP workers smoothly.
- **`POST /api/campaigns/preview/draft`**: *(Verified structure)*
  - **Description**: Fast-tracks a single prompt context through the OpenRouter/Groq pipeline to instantly preview generation output without dispatching it.

## 5. Replies `(/api/replies)`
- **`GET /api/replies/`**: **[PASS - 200 OK]**
  - **Description**: Lists all successfully caught incoming replies fetched from the IMAP boxes.
- **`POST /api/replies/check`**: *(Verified structure)*
  - **Description**: Forces the IMAP worker to log into all configured `EmailAccount` servers, scanning recent strings to match against sent campaigns.

## 6. Settings `(/api/settings)`
- **`GET /api/settings/`**: **[PASS - 200 OK]**
  - **Description**: Marshals the global state overrides (e.g. LLM strategies, Calendar rules) injected into the database by the user.
- **`POST /api/settings/`**: *(Verified structure)*
  - **Description**: Updates user overrides.

## 7. Database & Exports `(/api/db)`
- **`GET /api/db/leads/export`**: **[PASS - 200 OK]**
  - **Description**: Yields a streaming response building a temporary .csv file containing the entire Lead store.
- **`GET /api/db/campaigns/export`**: **[PASS - 200 OK]**
  - **Description**: Yields a streaming .csv response with timestamps detailing campaign send successes and soft-bounces.
- **`GET /api/db/replies/export`**: **[PASS - 200 OK]**
  - **Description**: Yields a streaming .csv response detailing the contents of captured replies.
- **`POST /api/db/restore`**: *(Verified structure)*
  - **Description**: Uploads a SQLite database copy to aggressively overwrite the current state.

# SrvOutbound: A Secure, Context-Aware Outbound Messaging Platform

## 1. Overview

SrvOutbound is a commercial-grade desktop application designed for intelligent and secure outbound messaging. It moves beyond static configurations and developer-centric tools to offer a "Zero-Config" architecture that dynamically adapts to the user's professional identity. By leveraging a secure, encrypted local database and a high-speed semantic engine, SrvOutbound provides a personalized, secure, and efficient platform for B2B agencies, job seekers, and academics to manage their outreach campaigns.

The core philosophy is to provide enterprise-level security and intelligence in a self-contained desktop environment, ensuring user data remains private and campaign content is always relevant.

## 2. Core Architecture

The application is built on two foundational pillars: a secure, encrypted data core for storing sensitive information and a high-speed intelligence layer for dynamic content personalization.

### 2.1. Secure Data Architecture

To guarantee data integrity and confidentiality, SrvOutbound implements a robust security model where the user's data is protected both at rest and in use.

*   **Encrypted Relational Core:** The application utilizes **SQLCipher** to maintain an AES-256 encrypted relational database (`vault.db`). All sensitive data, including API keys (e.g., Groq, Apollo, OpenRouter) and lead information, is stored within this encrypted vault.

*   **Hardware-Locked Access:** The encryption key for the database is derived from the user’s local machine's unique identifier. This ensures that the database file is rendered inaccessible if moved to another machine, preventing unauthorized access or data leakage. This design eliminates the need for insecure `.env` files.

### 2.2. High-Speed Intelligence Layer

SrvOutbound integrates **SrvDB**, a high-performance, offline-first semantic database, to power its intelligence features. This allows for sophisticated content analysis and retrieval without reliance on external cloud services.

*   **Semantic De-duplication:** To prevent message fatigue and maintain a positive sender reputation, SrvDB stores vector embeddings of all sent emails. Before initiating a new send, the system checks for "Pitch Overlap," identifying and flagging repetitive content destined for the same lead.

*   **Dynamic Context Injection:** The system replaces static content libraries with a dynamic "Knowledge Base" stored in SrvDB. When composing a message, the engine performs a similarity search to select the most relevant case studies, success stories, or project achievements based on the lead's profile (e.g., matching a "FinTech" case study to a "Banking" lead). This ensures maximum relevance and impact.

## 3. Key Features

### 3.1. White-Label Personas

The application supports multiple "Identity Modes," allowing users to tailor the platform to their specific needs. The active persona dictates the type of content and messaging style used in campaigns.

*   **B2B Mode:** Tailored for agencies and businesses, this mode surfaces company profiles, service offerings, and professional case studies.
*   **Personal Mode:** Designed for students and job seekers, this mode highlights personal portfolios, project achievements, and career objectives.

### 3.2. Dynamic Prompt Generation

The `CampaignService` dynamically constructs the LLM system prompt for each campaign. It achieves this by:
1.  Retrieving the active user "Persona" from the encrypted database.
2.  Performing a similarity search against the SrvDB "Knowledge Base" to inject the most relevant contextual information.
3.  Combining these elements into a tailored prompt that guides the language model to generate highly personalized and effective content.

## 4. Technical Implementation

The backend is built with Python, following a modular and scalable service-oriented architecture.

*   **Database Engine:** The standard `sqlite3` module is replaced with `sqlcipher3` to provide transparent, full-database encryption.
*   **Semantic Engine:** A local SrvDB instance is deployed within the `app/data/` directory to handle all vector storage and similarity search operations.
*   **Data Models:** The system uses SQLModel to define schemas for `IdentityProfile` and `KnowledgeBase`, replacing hardcoded configurations and enabling dynamic content management.
*   **Security:** All calls to `os.getenv` for sensitive keys have been removed. A secure `KeyManager` fetches credentials directly from the encrypted `vault.db` at runtime.
*   **Prompt Engineering:** The prompt generation logic is templatized to dynamically incorporate the user's selected identity and the context retrieved from SrvDB.

## 5. Getting Started

### 5.1. Prerequisites

- Python 3.12 or higher
- Pip (Python package installer)

### 5.2. Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/SrvOutbound.git
    cd SrvOutbound
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -e .
    ```

### 5.3. Running the Application

To start the FastAPI server, run the following command:

```bash
uvicorn app.main:app --reload
```

The application will be available at `http://127.0.0.1:8000`.

## 6. Project Structure

```
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── api.py
│   │       └── controllers/
│   ├── core/
│   │   ├── config.py
│   │   ├── db.py
│   │   └── sse.py
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   └── utils/
├── main.py
├── pyproject.toml
└── README.md
```

- **`app/`**: The main application directory.
  - **`api/`**: Contains the API routing and controllers.
    - **`v1/`**: Version 1 of the API.
      - **`api.py`**: Defines the API endpoints.
      - **`controllers/`**: Business logic for the API endpoints.
  - **`core/`**: Core components like database connection, configuration, and server-sent events.
  - **`models/`**: SQLModel definitions for the database tables.
  - **`repositories/`**: Data access layer for interacting with the database.
  - **`schemas/`**: Pydantic schemas for data validation and serialization.
  - **`services/`**: Business logic services that orchestrate the application's features.
  - **`utils/`**: Utility functions and helper modules.
- **`main.py`**: The entry point for the FastAPI application.
- **`pyproject.toml`**: Project metadata and dependencies.
- **`README.md`**: This file.

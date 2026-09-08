# User Flows — The Archivist (Hermes)

End-to-end interaction paths through the system, from user action to final rendered result.

---

## 1. New Session Flow

```mermaid
flowchart TD
    U["User opens app"] -->|"GET /"| R1["Server redirect (307)"]
    R1 -->|"GET /chat"| NP["New Chat Page"]
    NP -->|"generates UUID"| RP["router.replace(/chat/uuid)"]
    RP -->|"mounts HermesApp"| HA["HermesApp (empty state)"]
    HA -->|"fetches session (404)"| EMPTY["Empty chat view"]
    HA -->|"fetches session list"| SB["Sidebar populated"]
    EMPTY --> READY["Ready for input"]
```

**What happens:**
1. User navigates to `http://localhost:3000/`
2. Server-side redirect sends them to `/chat`
3. `HermesApp` mounts without an `initialSessionId`, generates a UUID
4. `router.replace` updates the URL to `/chat/<new-uuid>` (no history entry)
5. Backend returns 404 for the new session ID (expected — no turns yet)
6. User sees an empty chat with suggested queries

---

## 2. Ask a Question Flow

```mermaid
flowchart TD
    U["User types question"] --> SUB["Submit"]
    SUB --> OPT["Optimistic UI: add pending turn"]
    OPT --> SSE["POST /api/ask/stream"]

    SSE --> S1["SSE: status (guardrail)"]
    S1 --> S2["SSE: status (planning)"]
    S2 --> S3["SSE: status (retrieving)"]
    S3 --> META1["SSE: metadata (sources, figures)"]
    META1 --> S4["SSE: status (arbitrating)"]
    S4 --> META2["SSE: metadata (contradictions)"]
    META2 --> S5["SSE: status (synthesizing)"]
    S5 --> TOK["SSE: token stream"]
    TOK --> DONE["SSE: done"]

    DONE --> PERSIST["Backend persists session"]
    DONE --> RENDER["Frontend renders complete answer"]
    RENDER --> REFRESH["Sidebar refreshes session list"]
```

**What the user sees in real-time:**
1. Status indicator cycles through: "Validating input..." → "Formulating search plan..." → "Searching archive..." → "Arbitrating claims..." → "Synthesizing answer..."
2. Source cards appear when metadata arrives (before the answer)
3. Answer text streams token-by-token
4. Reasoning trace populates with each node's findings

---

## 3. Conversational Greeting Flow (Fast Path)

```mermaid
flowchart TD
    U["User types 'hello'"] --> SUB["Submit"]
    SUB --> SSE["POST /api/ask/stream"]
    SSE --> GR["Guardrail: is_conversational = true"]
    GR -->|"skips planner, retriever, arbitrator"| SY["Synthesizer"]
    SY --> TOK["SSE: tokens (greeting response)"]
    TOK --> DONE["SSE: done"]
    DONE --> RENDER["Greeting rendered (no sources)"]
```

**Key difference from research flow:**
- Only 2 nodes execute (guardrail + synthesizer)
- No embedding, no database query, no Redis lookup
- Single LLM call for the greeting response
- No source cards or reasoning trace displayed

---

## 4. Load Existing Session Flow

```mermaid
flowchart TD
    U["User clicks session in sidebar"] --> LINK["next/link → /chat/session-id"]
    LINK --> DYN["Dynamic route [sessionId]/page.tsx"]
    DYN --> MOUNT["HermesApp mounts with initialSessionId"]
    MOUNT --> FETCH["GET /api/sessions/session-id"]

    FETCH -->|"200 OK"| LOAD["Load turns into state"]
    FETCH -->|"404"| EMPTY["Empty chat (new session)"]

    LOAD --> RENDER["Render full conversation history"]
    RENDER --> READY["Ready for follow-up questions"]
```

**What happens:**
1. Sidebar items are `<Link>` elements → client-side navigation (no full reload)
2. Next.js extracts `sessionId` from URL params, passes to `HermesApp` as prop
3. Component fetches session details from backend
4. All previous turns render immediately (not streamed — already persisted)
5. User can ask follow-up questions that resolve pronouns against history

---

## 5. Follow-Up Question Flow (Pronoun Resolution)

```mermaid
flowchart TD
    U["User asks 'What war did they win?'"] --> GR["Guardrail: research query"]
    GR --> PL["Planner"]

    PL -->|"messages > 1"| LLM["LLM: rewrite with context"]
    LLM --> RQ["Rewritten: 'What war did The Silent Choir win?'"]

    RQ --> RT["Retriever: search rewritten query"]
    RT --> AR["Arbitrator: check evidence"]
    AR --> SY["Synthesizer: answer with full context"]
    SY --> DONE["Streamed answer about The War of Drowned Light"]
```

**Key behaviour:**
- Planner sees `messages > 1` and invokes the LLM to resolve "they" → "The Silent Choir" from prior turns
- Search queries use the rewritten standalone form
- This costs an extra LLM call (planner) compared to a first-turn question

---

## 6. Contradiction Detection Flow

```mermaid
flowchart TD
    RT["Retriever returns 5 chunks"] --> CHECK["Arbitrator: check authority weights"]

    CHECK -->|"all weights equal"| SKIP["Skip LLM — 0 contradictions"]
    CHECK -->|"mixed weights (codex + novel)"| LLM["LLM: analyze for conflicts"]

    LLM --> FOUND["Contradiction found"]
    LLM --> NONE["No contradictions"]

    FOUND --> META["SSE: metadata with contradictions array"]
    META --> BANNER["UI: amber contradiction banner"]
    BANNER --> DETAIL["Lists conflicting sources and topic"]

    SKIP --> CLEAN["No contradiction banner shown"]
    NONE --> CLEAN
```

**What triggers an LLM call:**
- At least 2 distinct `epistemic_weight` values in the retrieved chunks
- AND the minimum weight is below 0.8 (meaning a non-wiki/non-codex source is present)

---

## 7. Session Management Flows

### 7a. New Chat

```mermaid
flowchart LR
    BTN["Click 'New Chat'"] --> NAV["router.push('/chat')"]
    NAV --> UUID["Generate new UUID"]
    UUID --> REPLACE["router.replace('/chat/new-uuid')"]
    REPLACE --> EMPTY["Empty chat view"]
```

### 7b. Delete Session

```mermaid
flowchart LR
    BTN["Click delete icon"] --> API["DELETE /api/sessions/id"]
    API --> REMOVE["Remove from sidebar list"]
    REMOVE -->|"deleted active session"| NEW["Navigate to /chat"]
    REMOVE -->|"deleted other session"| STAY["Stay on current session"]
```

### 7c. Direct URL Access

```mermaid
flowchart LR
    URL["Navigate to /chat/some-uuid"] --> FETCH["GET /api/sessions/some-uuid"]
    FETCH -->|"200: session exists"| LOAD["Render conversation history"]
    FETCH -->|"404: not found"| EMPTY["Empty chat (treat as new session)"]
```

---

## 8. Retrieval Cache Flow

```mermaid
flowchart TD
    Q["Incoming query"] --> HASH["SHA-256 hash of normalized query"]
    HASH --> REDIS["Redis GET cache:retrieval:hash"]

    REDIS -->|"HIT"| CACHED["Return cached chunks"]
    REDIS -->|"MISS"| EMBED["Voyage AI: embed query"]
    REDIS -->|"REDIS DOWN"| EMBED

    EMBED --> SEARCH["pgvector: hybrid search (top 50)"]
    SEARCH --> RERANK["Cross-encoder rerank → top 5"]
    RERANK --> STORE["Redis SET with TTL"]
    STORE --> RETURN["Return chunks"]
    CACHED --> RETURN
```

---

## 9. Rate Limiting Flow

```mermaid
flowchart TD
    REQ["Incoming request"] --> CHECK["Redis: INCR rate:ip-address"]

    CHECK -->|"count ≤ 30"| ALLOW["Allow request"]
    CHECK -->|"count > 30"| REJECT["429 Too Many Requests"]
    CHECK -->|"Redis down"| ALLOW

    ALLOW --> HANDLER["Route handler executes"]
    REJECT --> MSG["'Rate limit exceeded. Try again later.'"]
```

- Window: 60 seconds (sliding)
- Limit: 30 requests per IP
- Fail-open: if Redis is unavailable, all requests are allowed

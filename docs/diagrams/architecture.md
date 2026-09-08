# Architecture Diagrams

Source of truth is `docs/architecture.md` sections 2-3. These are the same
diagrams kept here as standalone files per the required submission structure.

## System Diagram

```mermaid
flowchart TD
    subgraph Client["Client Layer"]
        FE["Next.js Frontend<br/>(App Router, SSE)"]
    end

    subgraph Backend["Backend API — FastAPI"]
        MW["Rate Limit Middleware<br/>(Redis sliding window)"]
        SVC["Agent Service<br/>(SSE streaming)"]

        subgraph Graph["LangGraph Agent Pipeline"]
            GR["Guardrail<br/>(regex intent classifier)"]
            PL["Planner<br/>(query rewriter)"]
            RT["Retriever<br/>(hybrid search + reranker)"]
            AR["Arbitrator<br/>(contradiction detector)"]
            SY["Synthesizer<br/>(answer generator)"]
        end
    end

    subgraph Data["Data Layer"]
        PG[("PostgreSQL<br/>pgvector + sessions")]
        RD[("Redis<br/>cache + rate limits")]
        VY["Voyage AI<br/>(embeddings)"]
        GM["Gemini<br/>(LLM)"]
    end

    subgraph Offline["Offline Pipeline (run once)"]
        ING["Ingestion Script"]
        CORPUS[("Ashen Era Archive<br/>415 docs")]
    end

    FE -->|"POST /api/ask/stream"| MW --> SVC
    SVC --> GR

    GR -->|"is_conversational=true"| SY
    GR -->|"is_conversational=false"| PL
    PL --> RT
    RT --> AR
    AR --> SY

    RT -->|"embed query"| VY
    RT -->|"hybrid search"| PG
    RT <-->|"retrieval cache"| RD

    PL -->|"rewrite query"| GM
    AR -->|"detect contradictions"| GM
    SY -->|"generate answer"| GM

    SY -->|"SSE tokens"| FE
    SVC -->|"persist session"| PG

    CORPUS --> ING -->|"chunks + embeddings"| PG
```

## Agent Graph (Conditional Routing)

```mermaid
flowchart LR
    START(("START")) --> GR["Guardrail"]

    GR -->|"greeting / chitchat"| SY["Synthesizer"]
    GR -->|"research query"| PL["Planner"]

    PL --> RT["Retriever"]
    RT --> AR["Arbitrator"]
    AR --> SY

    SY --> END_(("END"))
```

## Request Flow (Research Query)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as Backend
    participant GR as Guardrail
    participant PL as Planner
    participant RT as Retriever
    participant AR as Arbitrator
    participant SY as Synthesizer
    participant PG as PostgreSQL
    participant RD as Redis
    participant GM as Gemini

    U->>FE: Submit question
    FE->>API: POST /api/ask/stream
    API->>GR: Classify intent
    GR-->>API: research query

    API->>PL: Plan search
    PL->>GM: Rewrite query (if follow-up)
    API->>RT: Retrieve evidence
    RT->>RD: Check cache
    RT->>PG: Hybrid search
    API-->>FE: SSE: metadata

    API->>AR: Arbitrate evidence
    AR->>GM: Detect contradictions (if mixed authority)
    API-->>FE: SSE: metadata update

    API->>SY: Synthesize answer
    SY->>GM: Stream generation
    loop Token streaming
        API-->>FE: SSE: token
    end

    API->>PG: Persist session
    API-->>FE: SSE: done
```

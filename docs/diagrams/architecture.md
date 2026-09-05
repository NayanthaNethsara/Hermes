# Architecture Diagrams

Source of truth is `docs/architecture.md` sections 2-3 — these are the same
two diagrams, kept here as standalone files per the required submission
structure (`CLAUDE.md`, challenge doc section 5.2). Update both places
together if the design changes.

## System diagram

```mermaid
flowchart TD
    subgraph Client
        FE[Web Frontend - React]
        TG[Telegram Bot]
    end

    subgraph Backend["Backend API - FastAPI"]
        ORCH[Orchestrator]
        PLAN[Planner Agent]
        CRIT[Critic Agent]
        SYN[Synthesizer Agent]
    end

    subgraph Retrieval["Retrieval Layer"]
        VEC[(Chroma - Vector DB)]
        GRAPH[(NetworkX - Knowledge Graph)]
        TRUST[Trust Tagger]
    end

    subgraph Offline["Offline - runs once before the demo"]
        ING[Ingestion Script]
        GBUILD[Graph Builder Script]
        CORPUS[(Ashen Era Archive)]
    end

    FE --> ORCH
    TG --> ORCH
    ORCH --> PLAN
    PLAN --> VEC
    PLAN --> GRAPH
    VEC --> TRUST
    GRAPH --> TRUST
    TRUST --> CRIT
    CRIT -->|not enough / conflict| PLAN
    CRIT -->|enough evidence| SYN
    SYN --> ORCH
    ORCH --> FE
    ORCH --> TG

    CORPUS --> ING --> VEC
    CORPUS --> GBUILD --> GRAPH
```

## Request flow (one question, step by step)

```mermaid
sequenceDiagram
    participant U as User
    participant API as Backend API
    participant P as Planner
    participant R as Retriever (Vector + Graph)
    participant C as Critic
    participant S as Synthesizer

    U->>API: POST /api/ask {question}
    API->>P: What should we search first?
    P->>R: search query 1
    R-->>P: chunks + trust tags
    P->>C: evaluate evidence so far
    C-->>P: not enough, or contradiction found
    P->>R: search query 2 (refined)
    R-->>P: more chunks
    P->>C: evaluate again
    C-->>API: enough evidence, proceed
    API->>S: write final answer from all evidence
    S-->>API: answer + sources + trust tags + contradictions
    API-->>U: JSON response (see architecture.md section 6)
```

Max hops per question: **5** (hard limit, prevents infinite loops and
runaway API usage). If the agent hits 5 hops without being confident, it
answers with what it has and says so honestly — see `orchestrator.py`'s
`UNCERTAINTY_NOTE`.

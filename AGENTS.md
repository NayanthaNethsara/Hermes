# AGENTS.md

## Code Style and Engineering Principles

- **Folder Structure**: Keep code organized strictly within the defined repository structure.
- **Self-Explanatory Code**: Use clear, descriptive names and small, single-responsibility functions so code is readable without external explanation.
- **Minimal Commenting**: Do not add comments or docstrings. Omit comments on functions, classes, and modules unless strictly necessary for a non-obvious requirement or hardware constraint.
- **No Unnecessary Abstractions**: Do not introduce speculative or future-proofing code. Build only what is explicitly requested.
- **No Dead Code**: Eliminate unused functions, unused imports, unreferenced variables, and dead code paths.
- **Design Principles**: Apply KISS, DRY, and SOLID principles to maintain clean, reusable implementations without added complexity.
- **Semantic Styling**: In frontend code, use semantic color tokens (`bg-success`, `text-destructive`, `border-border`, etc.) rather than raw colors.
- **Consistent Visual Language**: Maintain one color language per visual signal. Do not reuse the same palette for distinct meanings in the same view.

---

## Repository Structure

```
.
├── .env
├── Makefile
├── ai_usage/
├── configuration-example/
├── data/
├── docker-compose.yml
├── docs/
├── sample_questions.json
├── sample_questions_1b_1c.json
└── src/
    ├── backend/
    │   ├── Dockerfile
    │   ├── pyproject.toml
    │   └── requirements.txt
    └── frontend/
        ├── Dockerfile
        └── package.json
```


# Context Map

This repo uses **multi-context** domain docs.

| Context | Path | Scope |
|---------|------|-------|
| System (root) | `CONTEXT.md` | AI Trading Desk — global terminology, market concepts, trading strategies |
| Backend | `backend/CONTEXT.md` | FastAPI services, data pipelines, agent orchestration, tool definitions |
| Frontend | `frontend/CONTEXT.md` | Vue 3 components, chat UI, state management, composables |

When a skill needs domain context, read the `CONTEXT.md` relevant to the module being modified. For cross-cutting concerns, read all applicable contexts.

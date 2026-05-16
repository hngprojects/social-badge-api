# Backend Team Community Guidelines

> Standards for all Pull Requests. Keeps our codebase high-performance, secure, and maintainable.

---

## 1. Async & Performance

FastAPI is built for speed — don't block the event loop.

| Rule | Detail |
|---|---|
| No blocking I/O in `async def` | Replace `time.sleep()` → `anyio.sleep()`, `requests` → `httpx` |
| Offload CPU-bound work | Use Background Tasks or a worker queue — never run heavy computation in an endpoint |
| Use async-native libraries | `motor` over PyMongo, `asyncpg` over psycopg2, etc. |

---

## 2. Pydantic & Data Integrity

- Use a shared `BaseModel` with `extra='forbid'` for consistent validation across all models.
- Always set `response_model` on route decorators — never construct responses manually.
- Validation logic goes in `@field_validator`, not in route functions. Keep routes skinny.

---

## 3. Dependency Injection & DB Management

- **Connections:** Use a `get_db` dependency yielding from a pool — no new connections per endpoint.
- **Lifespan:** Use `@asynccontextmanager` lifespan events to manage pool startup/shutdown.
- **Guards:** Use dependencies for common pre-checks (e.g. "does this user exist?") before main logic runs.

---

## 4. Security & Environment

- **Secrets:** Load via Pydantic `BaseSettings` from `.env`. Add `.env` to `.gitignore` immediately. No hardcoding.
- **Production:** Disable `/docs` and `/redoc` in production.
- **CORS:** Explicitly whitelist allowed origins. `allow_origins=["*"]` is banned in production.

---

## 5. Clean Code & Logging

- No `print()` — use the standard `logging` library.
- All function signatures must have type hints. Non-negotiable for FastAPI.
- All code must be formatted with **Black** and pass **Ruff/Flake8** before opening a PR.

---

## 6. Git & Collaboration

**Branch naming:** `feature:description-of-task` or `fix:issue-description`

**Commits:** Small and atomic — one logical change per commit.

**PR checklist:**
- [ ] All `pytest` tests pass
- [ ] Code is linted and formatted
- [ ] `response_model` is explicitly defined on every route

---

## 7. Documentation & Naming

- **No `# TODO`s** — incomplete features don't get merged to main.
- **No vague names** — `user_profile_json` not `data`; `payment_status_code` not `result`.
- **Docstrings required** on every route, service, and Pydantic model (populates Swagger `/docs` automatically).
- **Comments explain *why*, not *what*** — document business rules, not obvious mechanics.

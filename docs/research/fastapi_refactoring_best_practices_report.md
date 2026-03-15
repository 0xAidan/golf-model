# FastAPI Large Application Refactoring: Best Practices Report

**Research Date:** February 28, 2026  
**Scope:** Refactoring a 1700+ line monolithic FastAPI application into a modular, maintainable architecture

---

## Executive Summary

Refactoring a large FastAPI application requires moving from a monolithic flat structure to a **modular, domain-driven architecture**. The key principles are: (1) use `APIRouter` to split endpoints by feature, (2) implement layered architecture (routers → services → repositories), (3) centralize dependencies and shared state, and (4) refactor incrementally without breaking existing functionality.

---

## 1. Recommended Project Directory Structure

### Option A: Feature-Based (Domain-Driven) — Recommended for Large Apps

```
fastapi-project/
├── src/                          # or app/
│   ├── __init__.py
│   ├── main.py                   # Application entry point
│   ├── config.py                 # Pydantic Settings
│   ├── database.py               # DB connection, session factory
│   ├── dependencies.py           # Shared dependency injection
│   │
│   ├── auth/                     # Feature module
│   │   ├── __init__.py
│   │   ├── router.py             # APIRouter + endpoints
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── models.py             # SQLAlchemy/ORM models (if DB)
│   │   ├── service.py            # Business logic
│   │   ├── repository.py         # Data access (optional)
│   │   └── dependencies.py       # Feature-specific deps (optional)
│   │
│   ├── users/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── repository.py
│   │
│   ├── payments/
│   │   └── ...
│   │
│   ├── shared/                   # Cross-cutting utilities
│   │   ├── __init__.py
│   │   ├── exceptions.py         # Custom exception classes
│   │   ├── middleware.py        # Shared middleware
│   │   └── utils.py
│   │
│   └── internal/                 # Internal/admin routes (optional)
│       ├── __init__.py
│       └── admin.py
│
├── tests/
│   ├── conftest.py               # Pytest fixtures
│   ├── test_auth/
│   ├── test_users/
│   └── ...
│
├── alembic/                      # DB migrations
├── docker/
├── .env
├── pyproject.toml
└── README.md
```

### Option B: Router-Centric (Simpler, Official FastAPI Style)

```
app/
├── __init__.py
├── main.py
├── dependencies.py
├── config.py
├── database.py
├── routers/
│   ├── __init__.py
│   ├── users.py
│   ├── items.py
│   ├── auth.py
│   └── payments.py
├── services/
│   ├── user_service.py
│   ├── item_service.py
│   └── ...
├── models/                       # ORM models
├── schemas/                       # Pydantic schemas (or colocate in routers)
└── internal/
    ├── __init__.py
    └── admin.py
```

### Key Structural Principles

| Principle | Description |
|-----------|-------------|
| **Feature-based organization** | Group by domain (auth, users, payments) rather than by technical type (all routers, all models). Reduces merge conflicts and clarifies boundaries. |
| **Separation of concerns** | Routers handle HTTP only; services contain business logic; repositories handle data access. |
| **`__init__.py` everywhere** | Required for Python packages. Enables `from app.routers import users`. |
| **Shared vs feature-specific** | Put cross-cutting code (DB, config, auth) in `dependencies.py` or `shared/`. Feature-specific logic stays in feature modules. |

---

## 2. How APIRouter Works & Recommended Architecture

### Core Concept

`APIRouter` is FastAPI's tool for grouping related endpoints into separate modules—similar to Flask Blueprints. It behaves like a "mini FastAPI" class: you declare path operations the same way, and all options (dependencies, tags, responses) are supported.

### Basic APIRouter Usage

```python
# app/routers/users.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/users/", tags=["users"])
async def read_users():
    return [{"username": "Rick"}, {"username": "Morty"}]

@router.get("/users/me", tags=["users"])
async def read_user_me():
    return {"username": "fakecurrentuser"}

@router.get("/users/{username}", tags=["users"])
async def read_user(username: str):
    return {"username": username}
```

### APIRouter with prefix, tags, dependencies, responses

```python
# app/routers/items.py
from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_token_header

router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def read_items():
    return fake_items_db

@router.get("/{item_id}")
async def read_item(item_id: str):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"name": fake_items_db[item_id]["name"], "item_id": item_id}
```

**Important:** Path operations must start with `/`. The prefix should NOT include a trailing `/` (e.g., `/items` not `/items/`).

### Including Routers in main.py

```python
# app/main.py
from fastapi import Depends, FastAPI
from .dependencies import get_query_token, get_token_header
from .internal import admin
from .routers import items, users

app = FastAPI(dependencies=[Depends(get_query_token)])

# Include routers
app.include_router(users.router)
app.include_router(items.router)
app.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_token_header)],
    responses={418: {"description": "I'm a teapot"}},
)

@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}
```

### Key APIRouter Features

| Feature | Usage |
|---------|-------|
| **prefix** | Path prefix for all routes: `prefix="/api/v1"` |
| **tags** | OpenAPI tags for documentation |
| **dependencies** | Applied to ALL routes in the router (e.g., auth) |
| **responses** | Default responses for all routes |
| **include_router params** | Can override prefix/tags/deps when including, without modifying the router |

### Advanced: Nested Routers

```python
# Include an APIRouter in another APIRouter
router.include_router(other_router)
# Do this BEFORE including router in the main FastAPI app
```

### Advanced: Same Router, Multiple Prefixes

```python
# Expose same API under /api/v1 and /api/latest
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/latest")
```

### Avoid Name Collisions

Import submodules, not the `router` variable directly:

```python
# ✅ Correct
from .routers import items, users
app.include_router(users.router)
app.include_router(items.router)

# ❌ Wrong — second import overwrites first
from .routers.items import router
from .routers.users import router  # overwrites items.router
```

---

## 3. Sharing Dependencies Across Routers

### Database Sessions (Generator Pattern)

```python
# app/dependencies.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Type alias for cleaner injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
```

Usage in routers:

```python
@router.get("/users/")
async def list_users(db: DbSession):
    ...
```

### Configuration (Singleton with @lru_cache)

```python
# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MyApp"
    DATABASE_URL: str
    SECRET_KEY: str

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Layered Dependency Injection

Recommended pattern for scalable DI:

1. **Repository layer** — Data access (use `Protocol` for loose coupling)
2. **Service layer** — Business logic, depends on repositories
3. **Handler/endpoint layer** — HTTP handlers, depends on services

```python
# Wire using Depends; use @lru_cache for singletons
def get_user_service() -> UserService:
    return UserService(get_user_repository())

@router.get("/users/{id}")
async def get_user(id: int, service: UserService = Depends(get_user_service)):
    return await service.get_by_id(id)
```

### Global Dependencies

Apply to the entire app or specific routers:

```python
# App-level
app = FastAPI(dependencies=[Depends(get_query_token)])

# Router-level
app.include_router(admin.router, dependencies=[Depends(get_token_header)])
```

### Dependency Resolution Order

1. Router-level dependencies (from `include_router`)
2. Path operation decorator dependencies
3. Parameter dependencies (Depends in function signature)

---

## 4. Shared Middleware, Error Handlers, and CORS

### Middleware (App-Level)

Middleware is registered on the main `FastAPI` app and applies to all routes (including those from routers):

```python
# app/main.py
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Shared State: app.state vs request.state

| Mechanism | Use Case |
|-----------|----------|
| **app.state** | Global resources (DB pool, HTTP clients) that persist for app lifetime. Access via `request.app.state` |
| **request.state** | Request-scoped state. Often populated from lifespan context |

### Lifespan Context Manager (Recommended for Startup/Shutdown)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    client = NotificationClient()
    app.state.global_notifier = client
    yield
    # Shutdown
    client.close()

app = FastAPI(lifespan=lifespan)

# In endpoint or router
@router.get("/")
async def root(request: Request):
    notifier = request.app.state.global_notifier
```

### Global Exception Handlers

Register on the main app—they apply to all routes:

```python
# app/main.py
from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "error_code": exc.error_code}
    )
```

### Catching All Unhandled Exceptions

Use middleware (exception handlers may not catch everything in all cases):

```python
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(e)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

---

## 5. Step-by-Step Refactoring Approach

### Phase 1: Preparation (No Behavior Change)

1. **Add tests** — Ensure you have integration/API tests for critical paths.
2. **Create directory structure** — Add `routers/`, `services/`, `dependencies.py`, etc.
3. **Extract dependencies** — Move DB session, config, and shared logic into `dependencies.py`.
4. **Extract config** — Move env vars into Pydantic Settings.

### Phase 2: Extract First Router

1. **Pick a low-risk, self-contained domain** (e.g., health check, a simple CRUD module).
2. **Create `app/routers/health.py`** (or equivalent).
3. **Move related endpoints** from `main.py` into the new router.
4. **Include router** in `main.py` with `app.include_router(health.router)`.
5. **Run tests** — Verify behavior is unchanged.
6. **Commit** — Small, atomic commits.

### Phase 3: Extract Services

1. **Identify business logic** in the router that doesn't belong in HTTP layer.
2. **Create `app/services/`** (or feature-specific `service.py`).
3. **Move logic** into service functions/classes.
4. **Inject services** via `Depends` in router endpoints.
5. **Test** and commit.

### Phase 4: Extract Remaining Routers Incrementally

1. **Prioritize by domain** — One feature at a time (auth, users, payments, etc.).
2. **For each domain:**
   - Create router file
   - Move endpoints
   - Extract services if needed
   - Include router in main
   - Test and commit
3. **Avoid big-bang refactors** — Keep the app runnable after each step.

### Phase 5: Cleanup

1. **Remove dead code** from `main.py`.
2. **Standardize error handling** — Use custom exceptions and global handlers.
3. **Add OpenAPI tags** for better documentation.
4. **Review and consolidate** shared code.

### Migration from Legacy (e.g., Django)

- **Run both in parallel** — Use reverse proxy (Nginx/Traefik) to route by path.
- **Start with read-only, IO-heavy endpoints** — Lower risk.
- **Share database initially** — Move to bounded contexts later if needed.
- **Prioritize by traffic, latency, error rates** — Migrate high-value endpoints first.

---

## 6. Before/After Examples

### Before: Monolithic main.py (Simplified)

```python
# main.py — 1700+ lines
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

app = FastAPI()

# Dozens of endpoints mixed together
@app.get("/users/")
async def read_users(db: Session = Depends(get_db)):
    ...

@app.get("/users/{id}")
async def read_user(id: int, db: Session = Depends(get_db)):
    ...

@app.get("/items/")
async def read_items(db: Session = Depends(get_db)):
    ...

@app.post("/payments/")
async def create_payment(...):
    ...

# Middleware, CORS, exception handlers all in same file
app.add_middleware(CORSMiddleware, ...)
```

### After: Modular Structure

```python
# main.py — ~30 lines
from fastapi import Depends, FastAPI
from .dependencies import get_query_token
from .routers import users, items, payments

app = FastAPI(dependencies=[Depends(get_query_token)])
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(items.router, prefix="/items", tags=["items"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])

@app.get("/")
async def root():
    return {"message": "Hello"}
```

```python
# routers/users.py
from fastapi import APIRouter, Depends
from ..dependencies import get_db
from ..services.user_service import UserService

router = APIRouter()

@router.get("/")
async def read_users(service: UserService = Depends()):
    return await service.list_users()

@router.get("/{id}")
async def read_user(id: int, service: UserService = Depends()):
    return await service.get_by_id(id)
```

---

## 7. Common Pitfalls and How to Avoid Them

| Pitfall | Problem | Solution |
|---------|---------|----------|
| **Putting everything in routers** | Routers swell to 300+ lines; DB logic, business rules, and HTTP mixed together | Use layered architecture: routers → services → repositories. Routers only validate input and return responses. |
| **Treating FastAPI like Flask** | Blocking I/O, improper async usage, single-threaded deployment | Use async endpoints, async DB drivers, proper async/await. Deploy with Uvicorn/Gunicorn+Uvicorn workers. |
| **Circular imports** | `from app.x import y` and `from app.y import x` | Use dependency injection; avoid importing routers from each other. Keep shared code in `dependencies.py` or `shared/`. |
| **Scattered database logic** | Queries in routers, services, and utils | Centralize in repository layer. Use `Depends` to inject repositories. |
| **No tests before refactoring** | Refactor breaks behavior; no way to verify | Add integration tests first. Run after every extraction. |
| **Big-bang refactor** | Rewriting everything at once; long periods of broken state | Extract one router/feature at a time. Keep app runnable. |
| **Hardcoded config** | Secrets and env vars in code | Use Pydantic Settings; load from `.env`. |
| **Ignoring prefix trailing slash** | `prefix="/items/"` causes path issues | Use `prefix="/items"` (no trailing slash). Path ops use `/` or `/{id}`. |
| **Forgetting __init__.py** | Import errors in packages | Add `__init__.py` to every package directory. |
| **Overusing app.state** | Mutating shared state incorrectly | Prefer `request.state` for request-scoped data. Use lifespan for startup/shutdown only. |

---

## 8. Summary Checklist

- [ ] Use **feature-based** or **router-centric** project structure
- [ ] Create **APIRouter** per domain; use `prefix`, `tags`, `dependencies`
- [ ] **Include routers** in `main.py` with `app.include_router()`
- [ ] Centralize **dependencies** (DB, config, auth) in `dependencies.py`
- [ ] Use **layered architecture**: routers → services → repositories
- [ ] Share **middleware, CORS, exception handlers** on main app
- [ ] Use **lifespan** for startup/shutdown; **app.state** for global resources
- [ ] Refactor **incrementally** — one router/feature at a time
- [ ] **Test after every step**; avoid big-bang refactors
- [ ] Avoid **circular imports** and **fat routers**

---

## References

- [FastAPI: Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) (official docs)
- [FastAPI APIRouter Reference](https://fastapi.tiangolo.com/tr/reference/apirouter/)
- FastAPI Project Structure for Large Applications (Medium, 2026)
- Practical FastAPI × Clean Architecture Guide (blog.greeden.me)
- Organizing Large FastAPI Projects: Modular Routers (codingeasypeasy.com)
- FastAPI Dependency Injection 2026 Playbook (thelinuxcode.com)
- FastAPI State Variables: app.state vs request.state (Medium, sqlpey.com)
- 9 FastAPI Refactors That Make Legacy APIs Feel Like New (python.plainenglish.io)
- Common FastAPI Anti-Patterns (python.plainenglish.io)

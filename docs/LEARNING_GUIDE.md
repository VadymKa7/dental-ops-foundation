# Learning guide

This guide walks the code in this repository. It assumes you have shipped Kotlin or Java, Android, Flutter, Docker, and some IoT or video work, and you are new to Python backends. It does not introduce a second example. Every path below is a file you can open.

Read `docs/ARCHITECTURE.md` after this if you want the rules without the tour. Read `docs/ROADMAP.md` to see what this repository is refusing to pretend it already does.

## 1. Install and run one test before reading further

From the repository root:

```bash
uv sync
uv run pytest -m "not integration" -q
```

`uv sync` reads `pyproject.toml` and `uv.lock`, creates `.venv`, and installs FastAPI, SQLAlchemy, Alembic, and the test tools into that environment. You do not activate the virtualenv by hand. `uv run` uses it.

That pytest command runs the unit tests. They do not need Docker. Integration tests are marked `integration` and skip themselves until you export `TEST_DATABASE_URL`.

If `uv run pytest` fails on import with a missing `DATABASE_URL`, you imported `app.main` outside pytest. The module builds settings on import. Copy `.env.example` to `.env` or export the variable. Pytest avoids that trap in `tests/conftest.py`, which sets a placeholder URL before any test file imports the app. The placeholder is not contacted by the unit tests.

## 2. Names you already know

| You have used | In this repository |
| --- | --- |
| `build.gradle` / Maven POM | `pyproject.toml` for dependencies, `uv.lock` for the resolved set |
| A module or a package | A directory with `__init__.py`, for example `app/modules/users/` |
| Spring Boot application class | `create_app` in `app/main.py` |
| `application.yml` | `Settings` in `app/core/config.py`, filled from environment variables |
| `@RestController` | Functions on `router` in `app/modules/users/router.py` |
| A request DTO | `UserCreate` in `app/modules/users/schemas.py` |
| A response DTO | `UserRead` in the same file |
| `@Service` | `UserService` in `app/modules/users/service.py` |
| `@Repository` + Spring Data | `UserRepository` in `app/modules/users/repository.py`. The queries are written out. There is no base class that invents them. |
| JPA entity | `User` in `app/modules/users/models.py` |
| Flyway or Liquibase | Alembic, in `migrations/` |
| `@Autowired`, Dagger, Hilt | `Depends` parameters on the route functions |
| `suspend` function / Dart `async` | `async def` and `await` |
| JUnit + Mockito | `pytest` in `tests/unit/` and `tests/integration/` |
| Docker Compose | `docker-compose.yml` |

Python will not stop you from calling a private function or constructing an object the type checker dislikes. `mypy` is the compile-time check. Pydantic is the runtime check at the HTTP boundary. The service checks its own invariants again so a test can call it without HTTP.

## 3. Where to look

```text
app/main.py                      process startup and route mounting
app/api/health.py                /health/live and /health/ready
app/api/deps.py                  one database transaction per request
app/api/errors.py                JSON error shape
app/core/config.py               settings
app/core/logging.py              what is allowed into a log line
app/core/exceptions.py           NotFoundError, ConflictError, DomainValidationError
app/db/session.py                engine and session factory
app/modules/users/router.py      HTTP
app/modules/users/schemas.py     request and response models
app/modules/users/service.py     rules
app/modules/users/repository.py  SQL
app/modules/users/models.py      table
migrations/versions/0001_create_users.py
tests/unit/                      no database
tests/integration/               PostgreSQL
```

`app/modules/appointments/README.md` is not an empty feature. It is a note that scheduling is stage 3 on the roadmap. The same is true for `documents`, `ai`, and `video`.

## 4. What Python is doing in these files

**Indentation is syntax.** A block ends when the indent ends. There are no braces around `create_user`.

**Imports are files, not a classpath.** `from app.modules.users.service import UserService` loads `app/modules/users/service.py`. The import graph is the dependency graph. Feature modules do not import each other. `app/db/session.py` does not import FastAPI. That split is what lets a future worker open a session without starting a web server.

**`__init__.py` makes a directory a package.** The users package docstring says the endpoints are not an account system. That string is documentation for importers, not a runtime check.

**Type hints are not enforced at runtime** except by tools that opt in. `mypy` reads `user_id: UUID`. Pydantic reads `UserCreate` and actually rejects a bad body. A hint on an internal function will not stop a bad call. That is why `normalize_display_name` raises `DomainValidationError` itself.

**`None` is one value.** `User | None` means the repository did not find a row. The service turns that into `NotFoundError`. It does not return a nullable entity to the router.

**Decorators wrap a function.** `@router.post("/users", ...)` registers `create_user` with FastAPI. `@lru_cache` on `get_settings` stores the first `Settings` object. `@pytest.mark.parametrize` runs one test function several times. The decorator replaces or registers the function it sits on. Read the decorator line, then the function.

**Context managers are `try`/`finally` with a protocol.** `async with session_factory() as session` opens a session and closes it on the way out, including when the block raises. `lifespan` uses `@asynccontextmanager` for the same reason around the engine: `dispose()` runs on shutdown.

**f-strings** show up in validation messages: `f"Limit must be between 1 and {MAX_PAGE_SIZE}."`. They are string interpolation.

**There is no `new` keyword.** `UserService(repository)` calls `__init__`.

**Mutable default arguments are a classic bug** (`def f(items: list = [])` shares one list). This code uses `= None` or immutable defaults instead. `Settings` defaults such as `api_prefix: str = "/api/v1"` are safe because strings are immutable.

## 5. Process startup

Open `app/main.py`.

`create_app` is the composition root, in the same role as a small `main` that wires a manual dependency graph:

1. Resolve `Settings`. Tests pass an object. Uvicorn uses `get_settings()`, which reads the environment and `.env`.
2. Configure JSON logging.
3. Build a `FastAPI` instance. `redirect_slashes=False` so `/api/v1/users/` is not silently rewritten.
4. Store settings on `application.state`.
5. Register exception handlers.
6. Add `AccessLogMiddleware`.
7. Mount `health_router` with no prefix and `api_router` at `/api/v1`.

The last line, `app = create_app()`, exists because the process supervisor imports `app.main:app`. That import reads settings immediately. It does not connect to Postgres. The engine is created later.

`lifespan` runs when the server starts, and its `finally` block runs when the server stops:

```python
engine = create_db_engine(settings)
app.state.engine = engine
app.state.session_factory = create_session_factory(engine)
try:
    yield
finally:
    await engine.dispose()
```

That is the whole connection lifecycle for the process. There is no global engine variable in `app/db/session.py`. A test that calls `create_app` gets its own app and, once its lifespan starts, its own engine.

Compare this with an Android `Application` class or a Flutter binding that starts in `main()`. The process has one app object. Request state is not stored on it, except the shared engine and the session factory.

## 6. Follow `POST /api/v1/users`

Use this body:

```json
{"display_name": "  Ada Lovelace  ", "email": "  Ada@Example.com "}
```

**Routing.** `app/api/router.py` includes the users router. The route function is `create_user` in `app/modules/users/router.py`. The path is `/users`. The prefix `/api/v1` was added in `create_app`. The function returns `UserRead` and the status is 201.

**Schema.** FastAPI builds a `UserCreate` before the function body runs. `extra="forbid"` rejects a `password` field. `str_strip_whitespace` turns the display name into `Ada Lovelace`. `EmailStr` checks the address and lowercases the domain, so the schema value is `Ada@example.com`. The service then lowercases the whole address to `ada@example.com` before it stores the row. A failure becomes `RequestValidationError`. `validation_exception_handler` in `app/api/errors.py` writes:

```json
{"error": {"code": "validation_error", "message": "Request validation failed.", "details": []}}
```

`details` contains location, message, and type. It does not copy the raw input back into a log. The HTTP response can still quote a value inside a Pydantic message because the client sent that value. The server log must not.

**Dependency.** `create_user` asks for `service: Annotated[UserService, Depends(get_user_service)]`. FastAPI calls `get_user_service`. That function asks for a session via `Depends(get_db_session)`. So the order is: open a session, build `UserRepository(session)`, build `UserService(repository)`, call the route.

This is dependency injection without a container. The graph is the parameter list. It is closer to passing dependencies into a constructor than to a global service locator. Hilt would generate a factory. Here the factory is `get_user_service`, and it is three lines because the graph is three lines.

**Service.** `create_user` on `UserService` does not trust the schema completely. It calls `normalize_display_name` and `normalize_email`. The email becomes `ada@example.com`. The service then asks the repository if that address exists. If it does, it raises `ConflictError` with code `duplicate_email`.

The service constructs a `User` with a UUID and timestamps. Those values are Python values, so a unit test can see them without a database round trip. The columns also have server defaults so a raw SQL insert still gets a timestamp.

**Repository.** `add` calls `session.add` and `await session.flush()`. Flush sends the `INSERT` and runs `uq_users_email` now, not at commit time. If two requests both pass the email lookup, one flush raises `IntegrityError`. The service catches that and raises the same `ConflictError`. The router never imports SQLAlchemy.

**Response.** `UserRead.model_validate(user)` copies attributes off the entity because `from_attributes=True`. The route's declared return type is `UserRead`. FastAPI serializes that model. The entity class is not the response class.

**Commit or roll back.** Look at `get_db_session`. After the route returns, cleanup runs `await session.commit()`. If the route raised, cleanup runs `rollback()` and re-raises. `app_error_handler` then turns `ConflictError` into HTTP 409. The handler does not contain the duplicate-email rule. It only reads `status_code`, `code`, and `message` from the exception.

**Access log.** `AccessLogMiddleware` writes `request completed` with `http_method`, `path`, `status_code`, and `duration_ms`. A duplicate-email request is a 409 in that line. The email address is not one of the fields `JsonFormatter` is allowed to emit.

A missing user follows the same pipe. `get_user` loads by primary key, raises `NotFoundError` when the result is `None`, and the handler returns 404 with code `user_not_found`.

## 7. Why this is async

Postgres is on the other side of a socket. While that socket waits, the CPU in this process is free. `async def` and `await` let one OS thread run another request during that wait. `asyncpg` is the driver that speaks Postgres in that style. SQLAlchemy's async session is a wrapper around it. That is why `DATABASE_URL` must start with `postgresql+asyncpg://` and why the tests refuse SQLite.

Async does not make CPU-bound work faster. It does not run your function on a thread pool. If you call a blocking library inside `create_user` — a sync database driver, `time.sleep`, a huge image encode — you stall every other request on this worker.

That is also why video processing and model calls are not hidden inside this process. Stage 6 and stage 9 on the roadmap exist so that heavy work gets a worker and its own session, instead of a blocking call in a route. The engine factory is already separate from FastAPI so that worker can use it.

You will see `await` on `flush`, `execute`, `commit`, `rollback`, `connect`, and `dispose`. You will not see `session.query(...)`. That older API is synchronous. If a tutorial shows it, it is the wrong API for this repository.

## 8. How FastAPI dependencies behave

`Depends` means "call this to get the argument". Dependencies can depend on other dependencies. `get_user_service` depends on `get_db_session`.

A dependency that `yield`s is a context manager. Code before `yield` is setup. The yielded value is injected. Code after `yield` is cleanup and runs after the path function returns, including when the path function raised. That is why commit and rollback sit after `yield` in `get_db_session`.

FastAPI builds this graph per request. A session is not reused across requests. The engine is.

Tests in this repository do not use `app.dependency_overrides`. Unit tests call `UserService` with an in-memory stand-in, so they never start a session. Integration tests start the real app against PostgreSQL, so the real dependency runs. An override would be useful if you needed to swap one dependency and still go through HTTP without a database. We did not do that, because the SQL needs a real Postgres to be a meaningful test.

If you add an override later, it looks like this and belongs in a test, not in `app/`:

```python
application.dependency_overrides[get_db_session] = some_fake_session
```

Clear the dict afterwards. Prefer the existing split: service tests for rules, Postgres tests for SQL.

## 9. Sessions, transactions, and migrations

One request, one session, one transaction. The repository is allowed to flush. The dependency is the only place that commits. Services do not call `commit`. If they did, a later step in the same request could not roll the earlier step back.

`expire_on_commit=False` in `create_session_factory` keeps attributes usable after commit. Do not add a lazy relationship and then touch it in the router after the session is done. Async SQLAlchemy will not query it for you.

Migrations are files under `migrations/versions/`. `0001_create_users.py` creates the table, the primary key `pk_users`, and the unique constraint `uq_users_email`. `tests/unit/test_metadata.py` asserts the model matches those names. Alembic's `env.py` loads `Settings` and imports `User` so autogenerate can see the table. Importing the model there is a side effect on purpose. `app/db` staying ignorant of features is also on purpose.

The application never calls Alembic. You run `uv run alembic upgrade head`. A container restart that migrates itself hides a failed migration inside the restart loop. The README command is the migration path.

`/health/ready` runs `SELECT 1`. After a fresh database, ready can succeed before you have migrated. The users routes then fail until `upgrade head`. That split is documented because it surprises people who expect ready to mean "schema is current".

## 10. Logging and secrets

Open `app/core/logging.py`. `JsonFormatter` copies the message and a whitelist of extra fields. It does not write `exc_info`. `tests/unit/test_logging.py` builds a record whose exception text contains a database URL and whose extra data contains an email, then asserts neither string appears in the JSON.

`database_is_ready` logs `database readiness check failed` and `error_type`. It does not log the exception. `tests/unit/test_health_and_wiring.py` points the engine at port 1, expects 503, and checks the log text for the URL.

When you add a log line, add a field to `_ALLOWED_EXTRA` only if that field cannot carry personal data. A path in this API is a route plus a UUID. Do not put the email in the path.

## 11. How the tests are organized

`tests/unit/` answers "does the rule hold?" without I/O.

`tests/unit/test_user_service.py` uses `InMemoryUserRepository`. It is not a subclass and it does not open a session. `service_for` passes it through `cast` so mypy accepts the stand-in. The cast is a test seam, not a production interface. We did not add a `Protocol` because there is one stand-in. The interesting cases are:

- normalization of name and email
- duplicate email, including case
- `IntegrityError` translated to `ConflictError`, which is the race the lookup cannot see
- missing user
- page size and offset checks

`tests/unit/test_user_schema.py` covers the HTTP contract: strip, length, email shape, and a forbidden `password` field.

`tests/integration/` answers "does the HTTP stack persist rows in Postgres?" `tests/integration/conftest.py` reads `TEST_DATABASE_URL`, runs Alembic in a subprocess, and opens the app with `ASGITransport`. HTTPX talks to the app in-process. There is no need for the uvicorn port. After each test the fixture truncates `users`.

The subprocess matters. Alembic's `env.py` calls `asyncio.run`. Pytest is already running a loop. A second `asyncio.run` inside that loop fails. A child process has its own loop.

Pytest fixtures are the setup method. `client` is an async fixture. The test asks for it by naming the argument `client`. That is the same idea as a JUnit parameter resolver, with less annotation.

`pytest.mark.parametrize` is a table test. You can read the invalid emails in `test_create_user_rejects_invalid_values` as data, not as copy-pasted functions.

Assertions are plain `assert`. A failure shows the values. There is no `assertEquals`.

Run one test:

```bash
uv run pytest tests/unit/test_user_service.py::test_create_user_rejects_duplicate_email -q
```

Run the database tests only after exporting the URL in the README:

```bash
uv run pytest tests/integration -q
```

## 12. Map a few Python errors to Kotlin

| Python | Closest thing you have seen |
| --- | --- |
| `ImportError` | A missing module on the classpath |
| `TypeError` at a call | A bad argument, often only at runtime |
| `pydantic.ValidationError` | A failed serializer or a Bean Validation error |
| `sqlalchemy.exc.IntegrityError` | A constraint violation from JDBC |
| `pytest.skip` | `@Disabled` with a reason |

An unhandled exception becomes HTTP 500 with code `internal_error`. The response does not include the traceback. The log includes file and line numbers via `stack_frames`, not the exception message.

## 13. First change to make yourself

Do this before you add a feature. The goal is to see a test fail for a reason you understand.

Require display names to be at least two characters after stripping.

1. Add a unit test in `tests/unit/test_user_service.py` that calls `create_user` with `display_name="A"` and expects `DomainValidationError`. Run it. It fails, because one character is legal today.
2. Change `normalize_display_name` in `app/modules/users/service.py`. Run the unit test again.
3. Change `UserCreate` in `app/modules/users/schemas.py` so `display_name` uses `Field(min_length=2, max_length=120)`. Add `"A"` to the invalid payloads in `tests/unit/test_user_schema.py` and, if Postgres is running, in `tests/integration/test_users_api.py`.
4. Hit the API, or read the integration assertion, and notice the code is `validation_error`. The service test still sees `domain_validation_error`. The schema runs first on the way in. The service rule still protects a caller that is not HTTP.

That is the whole layering of this codebase in one small diff. After it is green, revert it or keep it. Do not start appointments, auth, or Redis clients as the first edit.

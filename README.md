# Resume Builder — Backend (Phase 1)

FastAPI backend covering Phase 1.1–1.4: scaffold, models, auth (email/password + Google OAuth via JWT cookies), deploy skeleton.

## What's here

```
app/
  core/
    config.py     - env-driven settings (pydantic-settings)
    database.py   - async SQLAlchemy engine/session, Base
    security.py   - password hashing, JWT create/decode
    cookies.py    - set/clear httpOnly auth cookies
    deps.py       - get_current_user / get_current_admin (replaces Flask's g)
  models/         - User, Job, Submission, UserFile, PasswordReset, UserPreferences
  schemas/        - Pydantic request/response models
  routers/
    auth.py       - /api/signup, /api/login, /api/refresh, /me, /logout,
                    /login/google, /auth/google/callback
  main.py         - FastAPI app, CORS, session middleware, Cloudinary config
alembic/          - migrations (replaces your old init_db())
```

## 1. Local setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `DATABASE_URL` — take your Neon connection string and change the driver prefix
  from `postgres://` or `postgresql://` to **`postgresql+asyncpg://`**
- `JWT_SECRET` — any long random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — same values you already use in Flask
- `GOOGLE_REDIRECT_URI` — for local dev: `http://localhost:8000/auth/google/callback`.
  **You must add this exact URI to the Google Cloud Console → Credentials → Authorized redirect URIs**,
  alongside your existing Flask one (you can have both while you migrate).
- Cloudinary vars — same as your Flask `.env`

## 2. Run migrations

```bash
alembic revision --autogenerate -m "init schema"
alembic upgrade head
```

This creates all 6 tables in Neon. Check the generated migration file in `alembic/versions/`
before running `upgrade head` — autogenerate is good but not infallible (e.g. it won't
detect column type changes reliably).

## 3. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` → should return `{"status": "ok"}`.

## 4. Test the auth loop

```bash
# signup
curl -i -c cookies.txt -X POST http://localhost:8000/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"testpass123","username":"You"}'

# hit protected route using the cookie jar curl just saved
curl -i -b cookies.txt http://localhost:8000/me
```

For Google login, open `http://localhost:8000/login/google` in a browser (not curl —
it's a redirect flow).

## 5. Deploy to Render

1. Push this repo to GitHub.
2. New Web Service on Render → connect repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add all `.env` vars in Render's Environment settings — **set `COOKIE_SECURE=true`
   and `COOKIE_DOMAIN` appropriately once you know your Vercel domain**.
6. Add your Render URL's callback (`https://your-app.onrender.com/auth/google/callback`)
   to Google Console's authorized redirect URIs.
7. Hit `https://your-app.onrender.com/health` to confirm.

## Notes / decisions made for you

- **Why JWT-in-cookie instead of Flask sessions:** your frontend (Vercel) and backend
  (Render) are different origins. `SessionMiddleware`/server-side sessions get awkward
  cross-origin; short-lived JWT access token + longer refresh token, both httpOnly
  cookies with `SameSite=None; Secure` in prod, is the standard pattern for this split.
- **`is_admin`** is a new boolean column (your Flask code referenced `user["is_admin"]`
  but I don't see it created in `init_db()` — it's added here properly with a migration).
  You'll need to manually flip it to `true` for your own user row after first signup:
  ```sql
  UPDATE users SET is_admin = true WHERE email = 'you@example.com';
  ```
- **Submission model** already has `parent_submission_id` and `job_description` columns
  added for Phase 1B's `/resume/tailor` versioning — no migration needed later.
- **Job model** already has `source` and `dedup_hash` columns for Phase 2's scraper dedup —
  ditto.

## Next (Phase 1B)

Once `/me` and Google login work end-to-end against Render + Neon, move to the
canonical `ResumeData` schema and the Gemini service. Say the word and I'll scaffold that next.

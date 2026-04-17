from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from starlette.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import Base, engine
from models import Base
from routers import auth, admin, users, posts, chats, messages, reactions, uploads, ai
from routers.assignments import router as assignments_router
from routers.classes import router as classes_router, rating_router
from routers.rag import router as rag_router
from websocket import router as ws_router
from sqlalchemy import text
from services.deadline_checker import deadline_checker_loop

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

def _migrate():
    with engine.connect() as conn:
        migrations = [
            "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS class_id INTEGER NOT NULL DEFAULT 0",
            "CREATE INDEX IF NOT EXISTS ix_assignments_class_id ON assignments(class_id)",
            "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS reference_solution_url TEXT",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS file_urls TEXT",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_url TEXT",
            "ALTER TABLE posts ADD COLUMN IF NOT EXISTS created_at DATETIME",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS variant_number INTEGER",
            """CREATE TABLE IF NOT EXISTS ai_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                class_id INTEGER,
                endpoint VARCHAR(64) NOT NULL DEFAULT 'chat',
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_class_id ON ai_usage_logs(class_id)",
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_created_at ON ai_usage_logs(created_at)",
        ]
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                try:
                    plain = stmt.replace(" IF NOT EXISTS", "")
                    conn.execute(text(plain))
                    conn.commit()
                except Exception:
                    pass

_migrate()

_cors_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _cors_raw.split(",")] if _cors_raw != "*" else ["*"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(deadline_checker_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Chatra API", version="3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(ws_router)
app.include_router(reactions.router)
app.include_router(uploads.router)
app.include_router(ai.router)
app.include_router(assignments_router)
app.include_router(classes_router)
app.include_router(rating_router)
app.include_router(rag_router)

_upload_dir = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(_upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")

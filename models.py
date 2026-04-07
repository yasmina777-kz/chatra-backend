from sqlalchemy import (
    String, Integer, Boolean, ForeignKey, Column, Text, DateTime, Table
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from db import Base


class_members = Table(
    "class_members",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE")),
    Column("user_id",  Integer, ForeignKey("users.id",  ondelete="CASCADE")),
)

chat_members = Table(
    "chat_members",
    Base.metadata,
    Column("chat_id", Integer, ForeignKey("chats.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)


class Class(Base):
    """Учебный класс/группа. Создаётся учителем или администратором."""
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    creator: Mapped["User"] = relationship(back_populates="classes_created", foreign_keys=[created_by])
    members: Mapped[list["User"]] = relationship(
        "User",
        secondary=class_members,
        back_populates="classes",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="student", nullable=False)
    # Roles: admin | teacher | student
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    posts: Mapped[list["Posts"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    chats: Mapped[list["Chat"]] = relationship(
        "Chat",
        secondary=chat_members,
        back_populates="members",
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )
    assignments_created: Mapped[list["Assignment"]] = relationship(
        back_populates="creator",
        cascade="all, delete-orphan",
        foreign_keys="Assignment.created_by",
    )
    classes_created: Mapped[list["Class"]] = relationship(
        back_populates="creator",
        cascade="all, delete-orphan",
        foreign_keys="Class.created_by",
    )
    classes: Mapped[list["Class"]] = relationship(
        "Class",
        secondary=class_members,
        back_populates="members",
    )


class Posts(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    # Optional: track creation time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship(back_populates="posts")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    members: Mapped[list["User"]] = relationship(
        "User",
        secondary=chat_members,
        back_populates="chats",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    is_read = Column(Boolean, default=False)
    file_url = Column(String, nullable=True)


class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    emoji = Column(String)


class Assignment(Base):
    """
    Assignment created by teacher/admin.
    criteria — JSON string:
    [{"name": "Полнота", "weight": 40, "description": "..."}, ...]
    """
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, server_default="0")
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    criteria: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Одно эталонное решение (legacy, оставляем для совместимости)
    reference_solution_url: Mapped[str] = mapped_column(String, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    creator: Mapped["User"] = relationship(back_populates="assignments_created", foreign_keys=[created_by])

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
    )
    variants: Mapped[list["AssignmentVariant"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="AssignmentVariant.variant_number",
    )


class AssignmentVariant(Base):
    """
    Вариант задания с эталонным решением.
    Учитель загружает несколько вариантов (1, 2, 3...),
    каждый со своим эталонным файлом.
    ИИ-проверка: сравнивает работу студента с нужным вариантом.
    """
    __tablename__ = "assignment_variants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    title: Mapped[str] = mapped_column(String(256), nullable=True)        # "Вариант 1"
    reference_solution_url: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assignment: Mapped["Assignment"] = relationship(back_populates="variants")


class Submission(Base):
    """
    Student answer. status: submitted | grading | graded | late
    variant_number — студент указывает свой вариант при сдаче.
    """
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    file_url: Mapped[str] = mapped_column(String, nullable=True)
    file_urls: Mapped[str] = mapped_column(Text, nullable=True)    # JSON list of URLs
    text_content: Mapped[str] = mapped_column(Text, nullable=True)
    variant_number: Mapped[int] = mapped_column(Integer, nullable=True)  # номер варианта студента

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String, default="submitted")

    assignment: Mapped["Assignment"] = relationship(back_populates="submissions")
    student: Mapped["User"] = relationship(back_populates="submissions")
    grade: Mapped["Grade"] = relationship(
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Grade(Base):
    """
    AI or teacher grading result.
    criteria_scores — JSON:
    [{"name": "Полнота", "score": 35, "max": 40, "comment": "..."}]
    graded_by: "ai" | "teacher"
    """
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, unique=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    criteria_scores: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    graded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    graded_by: Mapped[str] = mapped_column(String, default="ai")

    submission: Mapped["Submission"] = relationship(back_populates="grade")


# ══════════════════════════════════════════════════════════════════════════════
#  RAG — Document chunks with pgvector embeddings
# ══════════════════════════════════════════════════════════════════════════════

EMBED_DIM = 1536  # text-embedding-3-small


class RagDocument(Base):
    """One uploaded lecture file indexed for RAG."""
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class RagChunk(Base):
    """
    One text chunk from a RagDocument.
    embedding stored as pgvector VECTOR(1536) — requires PostgreSQL + pgvector.
    For SQLite (dev) the column falls back to Text (stored as JSON string).
    """
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stored as TEXT on SQLite, VECTOR(1536) on PostgreSQL via migration
    embedding: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["RagDocument"] = relationship(back_populates="chunks")


class AiUsageLog(Base):
    """
    Logs every AI API call with token usage for admin analytics.
    class_id=NULL means it was a general AI chat (not class-specific).
    """
    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)  # "chat" | "ai-grade"
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessedDocument(Base):
    """
    Кэш: результат алгоритмического парсинга файла (без ИИ).
    Хранит структурированный JSON — параграфы, таблицы, OCR-текст с картинок.
    ИИ читает этот JSON вместо сырого файла → экономия ~70-90% токенов.
    """
    __tablename__ = "processed_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    rag_document_id: Mapped[int] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)   # docx|pdf|image|text
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

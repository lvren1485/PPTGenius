from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Text, UnicodeText, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(UnicodeText(64), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(UnicodeText(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(UnicodeText(32), nullable=False, default="active")
    current_phase: Mapped[str | None] = mapped_column(UnicodeText(32), default="chat")
    workspace_path: Mapped[str] = mapped_column(UnicodeText(512), nullable=False, default="")
    total_tokens: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")
    outlines: Mapped[list["Outline"]] = relationship(back_populates="conversation")
    presentations: Mapped[list["Presentation"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(UnicodeText(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(UnicodeText(32), default="text")
    token_count: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Outline(Base):
    __tablename__ = "outlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    title: Mapped[str] = mapped_column(UnicodeText(256), nullable=False)
    status: Mapped[str] = mapped_column(UnicodeText(32), nullable=False, default="draft")
    eval_score: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    slide_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="outlines")
    slides: Mapped[list["OutlineSlide"]] = relationship(back_populates="outline")


class OutlineSlide(Base):
    __tablename__ = "outline_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outline_id: Mapped[int] = mapped_column(ForeignKey("outlines.id"), nullable=False)
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(UnicodeText(256), nullable=False)
    content_json: Mapped[dict | None] = mapped_column(JSON)
    layout_type: Mapped[str | None] = mapped_column(UnicodeText(32), default="content")
    has_image: Mapped[bool | None] = mapped_column(Boolean, default=False)
    has_chart: Mapped[bool | None] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    outline: Mapped["Outline"] = relationship(back_populates="slides")


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    outline_id: Mapped[int | None] = mapped_column(ForeignKey("outlines.id"))
    file_path: Mapped[str] = mapped_column(UnicodeText(512), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    slide_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(UnicodeText(32), nullable=False, default="completed")
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="presentations")
    slides: Mapped[list["PresentationSlide"]] = relationship(back_populates="presentation")


class PresentationSlide(Base):
    __tablename__ = "presentation_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    presentation_id: Mapped[int] = mapped_column(
        ForeignKey("presentations.id"), nullable=False
    )
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    layout_type: Mapped[str] = mapped_column(UnicodeText(32), nullable=False)
    color_scheme: Mapped[dict | None] = mapped_column(JSON)
    text_content_json: Mapped[dict | None] = mapped_column(JSON)
    image_paths: Mapped[str | None] = mapped_column(Text)
    chart_paths: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    presentation: Mapped["Presentation"] = relationship(back_populates="slides")


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(UnicodeText(256), nullable=False)
    file_path: Mapped[str] = mapped_column(UnicodeText(512), nullable=False)
    file_type: Mapped[str] = mapped_column(UnicodeText(16), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer, default=0)
    source_type: Mapped[str | None] = mapped_column(UnicodeText(16), default="upload")
    status: Mapped[str | None] = mapped_column(UnicodeText(32), default="indexed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("knowledge_files.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    file: Mapped["KnowledgeFile"] = relationship(back_populates="chunks")


class WebResource(Base):
    __tablename__ = "web_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    url: Mapped[str] = mapped_column(UnicodeText(1024), nullable=False)
    title: Mapped[str | None] = mapped_column(UnicodeText(256))
    content_text: Mapped[str | None] = mapped_column(Text)
    source_domain: Mapped[str | None] = mapped_column(UnicodeText(256))
    stored_path: Mapped[str | None] = mapped_column(UnicodeText(512))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

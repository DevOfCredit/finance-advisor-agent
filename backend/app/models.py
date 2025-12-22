"""
Database models for the application.

Defines all SQLAlchemy models including User, Email, Contact, Task, etc.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base


class User(Base):
    """
    User model representing a financial advisor.
    Stores OAuth tokens and connection status.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Google OAuth tokens
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    google_email = Column(String, nullable=True)  # User's Gmail address
    
    # HubSpot OAuth tokens
    hubspot_access_token = Column(Text, nullable=True)
    hubspot_refresh_token = Column(Text, nullable=True)
    hubspot_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    hubspot_contact_id = Column(String, nullable=True)  # HubSpot contact ID
    hubspot_name = Column(String, nullable=True)  # HubSpot account name
    
    # Relationships
    emails = relationship("Email", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    ongoing_instructions = relationship("OngoingInstruction", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class Email(Base):
    """
    Email model storing imported Gmail messages.
    Includes vector embedding for RAG search.
    """
    __tablename__ = "emails"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    gmail_id = Column(String, unique=True, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    
    # Email content
    subject = Column(String, nullable=True)
    from_email = Column(String, index=True, nullable=True)
    to_emails = Column(JSON, nullable=True)  # List of recipient emails
    cc_emails = Column(JSON, nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    
    # Metadata
    received_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Vector embedding for semantic search (1536 dimensions for OpenAI embeddings)
    embedding = Column(Vector(1536), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="emails")


class Contact(Base):
    """
    HubSpot contact model.
    Stores contact information and notes with vector embeddings.
    """
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hubspot_id = Column(String, unique=True, index=True, nullable=False)
    
    # Contact information
    email = Column(String, index=True, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    company = Column(String, nullable=True)
    
    # Notes and additional data
    notes = Column(Text, nullable=True)  # Combined notes text
    raw_data = Column(JSON, nullable=True)  # Full HubSpot contact data
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Vector embedding for semantic search
    embedding = Column(Vector(1536), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="contacts")


class Task(Base):
    """
    Task model for storing AI agent tasks.
    Allows tasks to persist across requests and continue until completion.
    """
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Task information
    task_type = Column(String, nullable=False)  # e.g., "schedule_appointment", "create_contact"
    status = Column(String, default="pending")  # pending, in_progress, completed, failed
    description = Column(Text, nullable=True)
    
    # Task data and context
    input_data = Column(JSON, nullable=True)  # Original request data
    current_state = Column(JSON, nullable=True)  # Current state of the task
    result = Column(JSON, nullable=True)  # Final result
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="tasks")


class OngoingInstruction(Base):
    """
    Model for storing ongoing instructions from the user.
    These are remembered and applied proactively.
    """
    __tablename__ = "ongoing_instructions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Instruction details
    instruction = Column(Text, nullable=False)  # The instruction text
    trigger_type = Column(String, nullable=True)  # email, calendar, hubspot, all
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    user = relationship("User", back_populates="ongoing_instructions")


class ChatMessage(Base):
    """
    Model for storing chat messages between user and AI agent.
    Enables chat history and infinite scroll functionality.
    """
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Message content
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message text
    error = Column(Boolean, default=False)  # Whether this is an error message
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationship
    user = relationship("User", back_populates="chat_messages")


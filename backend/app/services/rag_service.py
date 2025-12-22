"""
RAG (Retrieval Augmented Generation) service.

Handles vector embeddings and semantic search over emails and contacts.
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_, text as sa_text
from app.models import Email, Contact
from openai import OpenAI
from app.config import settings
from typing import List, Dict, Optional
import numpy as np

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


def get_embedding(text: str) -> List[float]:
    """
    Get embedding vector for text using OpenAI.
    Truncates text if it exceeds the model's token limit.
    
    Args:
        text: Text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    # text-embedding-3-small has a max of 8192 tokens
    # Roughly 1 token = 4 characters for English text, so 8192 tokens ≈ 32,768 characters
    # To be safe, truncate to 20,000 characters (well under the limit)
    MAX_CHARS = 20000
    
    if len(text) > MAX_CHARS:
        # Truncate but keep the beginning (subject and first part of body are usually most important)
        text = text[:MAX_CHARS]
        print(f"Warning: Text truncated to {MAX_CHARS} characters for embedding")
    
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def search_emails(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 5
) -> List[Email]:
    """
    Search emails using exact sender matching and semantic similarity.
    
    First tries to find exact matches by sender email/name, then falls back
    to semantic similarity search if no exact matches are found.
    
    Args:
        db: Database session
        user_id: User ID to filter emails
        query: Search query text
        limit: Maximum number of results
        
    Returns:
        List of matching Email objects
    """
    # First, try exact match by sender email/name
    # Check if query looks like a name or email (simple heuristic)
    query_lower = query.lower().strip()
    
    # Try to find emails from sender matching the query
    # This handles queries like "emails from robert" or just "robert"
    exact_matches = db.query(Email).filter(
        Email.user_id == user_id,
        or_(
            Email.from_email.ilike(f"%{query_lower}%"),
            Email.from_email.ilike(f"%{query_lower.replace(' ', '')}%")
        )
    ).order_by(Email.received_at.desc()).limit(limit).all()
    
    if exact_matches:
        return exact_matches
    
    # Fall back to semantic search if no exact matches
    # Get query embedding
    query_embedding = get_embedding(query)
    
    # Search using pgvector (cosine similarity)
    # Format embedding as PostgreSQL array string
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    # Using raw SQL for pgvector similarity search
    # Use CAST() instead of ::vector to avoid parameter binding issues
    results = db.execute(
        sa_text("""
        SELECT id, gmail_id, subject, from_email, body_text, received_at,
               1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
        FROM emails
        WHERE user_id = :user_id AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
        """),
        {
            "user_id": user_id,
            "query_embedding": embedding_str,
            "limit": limit
        }
    ).fetchall()
    
    # Convert to Email objects
    email_ids = [r[0] for r in results]
    emails = db.query(Email).filter(Email.id.in_(email_ids)).all()
    
    # Sort by similarity (maintain order from query)
    email_dict = {e.id: e for e in emails}
    return [email_dict[eid] for eid in email_ids if eid in email_dict]


def search_contacts(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 5
) -> List[Contact]:
    """
    Search contacts using semantic similarity.
    
    Args:
        db: Database session
        user_id: User ID to filter contacts
        query: Search query text
        limit: Maximum number of results
        
    Returns:
        List of matching Contact objects
    """
    # Get query embedding
    query_embedding = get_embedding(query)
    
    # Format embedding as PostgreSQL array string
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    # Search using pgvector
    # Use CAST() instead of ::vector to avoid parameter binding issues
    results = db.execute(
        sa_text("""
        SELECT id, hubspot_id, email, first_name, last_name, notes,
               1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
        FROM contacts
        WHERE user_id = :user_id AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
        """),
        {
            "user_id": user_id,
            "query_embedding": embedding_str,
            "limit": limit
        }
    ).fetchall()
    
    # Convert to Contact objects
    contact_ids = [r[0] for r in results]
    contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
    
    # Sort by similarity
    contact_dict = {c.id: c for c in contacts}
    return [contact_dict[cid] for cid in contact_ids if cid in contact_dict]


def get_relevant_context(
    db: Session,
    user_id: int,
    query: str,
    email_limit: int = 5,
    contact_limit: int = 5
) -> str:
    """
    Get relevant context from emails and contacts for a query.
    
    Args:
        db: Database session
        user_id: User ID
        query: Search query
        email_limit: Maximum number of emails to include
        contact_limit: Maximum number of contacts to include
        
    Returns:
        Formatted context string for LLM
    """
    # Search emails and contacts
    emails = search_emails(db, user_id, query, email_limit)
    contacts = search_contacts(db, user_id, query, contact_limit)
    
    # Format context
    context_parts = []
    
    if emails:
        context_parts.append("## Relevant Emails:")
        for email in emails:
            context_parts.append(f"""
From: {email.from_email}
Subject: {email.subject}
Date: {email.received_at}
Body: {email.body_text[:500]}...
""")
    
    if contacts:
        context_parts.append("\n## Relevant Contacts:")
        for contact in contacts:
            name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Unknown"
            context_parts.append(f"""
Name: {name}
Email: {contact.email}
Company: {contact.company or 'N/A'}
Notes: {contact.notes[:300] if contact.notes else 'No notes'}...
""")
    
    return "\n".join(context_parts) if context_parts else "No relevant context found."


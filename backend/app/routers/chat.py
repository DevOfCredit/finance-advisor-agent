"""
Chat routes for AI agent conversations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models import User, ChatMessage as ChatMessageModel
from app.auth import verify_token
from app.services.ai_agent import AIAgent

router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    conversation_history: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: Optional[str] = None
    error: Optional[str] = None
    message_id: Optional[int] = None  # ID of saved assistant message


class ChatHistoryMessage(BaseModel):
    """Chat history message model for API responses."""
    id: int
    role: str
    content: str
    error: bool
    timestamp: str  # ISO format datetime


class ChatHistoryResponse(BaseModel):
    """Chat history response with pagination."""
    messages: List[ChatHistoryMessage]
    has_more: bool  # Whether there are more messages to load


def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from JWT token.
    
    Args:
        authorization: Authorization header with Bearer token
        db: Database session
        
    Returns:
        User object
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'"
        )
    
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Process a chat message and return AI response.
    Saves both user and assistant messages to the database.
    
    Args:
        request: Chat request with message and conversation history
        authorization: JWT token in Authorization header
        db: Database session
        
    Returns:
        Chat response with AI message or error
    """
    user = get_current_user(authorization, db)
    
    # Save user message to database
    user_message = ChatMessageModel(
        user_id=user.id,
        role="user",
        content=request.message,
        error=False
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    # Convert conversation history to dict format
    history = []
    if request.conversation_history:
        for msg in request.conversation_history:
            history.append({
                "role": msg.role,
                "content": msg.content
            })
    
    # Initialize AI agent
    agent = AIAgent(db, user)
    
    # Process message
    result = await agent.chat(request.message, history)
    
    # Save assistant message to database
    assistant_message = ChatMessageModel(
        user_id=user.id,
        role="assistant",
        content=result.get("response", "") or result.get("error", ""),
        error=bool(result.get("error"))
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    
    # Add message ID to response
    result["message_id"] = assistant_message.id
    
    return ChatResponse(**result)


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    limit: int = Query(20, ge=1, le=50, description="Number of messages to fetch"),
    before_id: Optional[int] = Query(None, description="Fetch messages before this ID (for pagination)"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get chat history with pagination.
    Returns messages in reverse chronological order (newest first).
    
    Args:
        limit: Number of messages to fetch (default 20, max 50)
        before_id: Fetch messages created before this message ID (for infinite scroll)
        authorization: JWT token
        db: Database session
        
    Returns:
        Chat history with messages and pagination info
    """
    user = get_current_user(authorization, db)
    
    # Build query
    query = db.query(ChatMessageModel).filter(
        ChatMessageModel.user_id == user.id
    )
    
    # If before_id is provided, fetch older messages
    # Get the message with before_id to use its timestamp for filtering
    if before_id:
        before_message = db.query(ChatMessageModel).filter(
            ChatMessageModel.id == before_id,
            ChatMessageModel.user_id == user.id
        ).first()
        if before_message and before_message.created_at:
            # Filter by created_at to ensure we get older messages
            query = query.filter(ChatMessageModel.created_at < before_message.created_at)
        else:
            # Fallback to ID filtering if timestamp not available
            query = query.filter(ChatMessageModel.id < before_id)
    
    # Order by created_at descending (newest first) and limit
    # We fetch limit+1 to check if there are more messages
    messages = query.order_by(desc(ChatMessageModel.created_at)).limit(limit + 1).all()
    
    # Check if there are more messages
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]  # Remove the extra message
    
    # Convert to response format
    history_messages = [
        ChatHistoryMessage(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            error=msg.error,
            timestamp=msg.created_at.isoformat() if msg.created_at else ""
        )
        for msg in messages
    ]
    
    return ChatHistoryResponse(
        messages=history_messages,
        has_more=has_more
    )


@router.post("/ongoing-instruction")
async def add_ongoing_instruction(
    instruction: str,
    trigger_type: Optional[str] = "all",
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Add an ongoing instruction for the AI agent.
    
    Args:
        instruction: Instruction text
        trigger_type: When to apply (email, calendar, hubspot, all)
        authorization: JWT token
        db: Database session
        
    Returns:
        Created instruction
    """
    user = get_current_user(authorization, db)
    
    from app.models import OngoingInstruction
    
    ongoing_instruction = OngoingInstruction(
        user_id=user.id,
        instruction=instruction,
        trigger_type=trigger_type,
        is_active=True
    )
    
    db.add(ongoing_instruction)
    db.commit()
    db.refresh(ongoing_instruction)
    
    return {
        "id": ongoing_instruction.id,
        "instruction": ongoing_instruction.instruction,
        "trigger_type": ongoing_instruction.trigger_type
    }


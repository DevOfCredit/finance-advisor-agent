"""
AI Agent service with tool calling capabilities.

Handles conversation with OpenAI, tool calling, and task management.
"""

from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Optional, Any
from app.config import settings
from app.models import User, Task, OngoingInstruction
from app.services.rag_service import get_relevant_context
from app.services.google_service import GoogleService
from app.services.hubspot_service import HubSpotService
from datetime import datetime, timedelta, timezone
import json

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


# Define available tools for the AI agent
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_emails_and_contacts",
            "description": "Search emails and contacts for information about clients. Use this to answer questions about clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to find relevant emails and contacts"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient. Use this to communicate with clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line"
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content"
                    },
                    "cc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional CC email addresses"
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create a calendar event/appointment. Use this to schedule meetings. IMPORTANT: Always include the attendee's email address in the 'attendees' array so they receive an invitation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title/summary"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in ISO 8601 format (e.g., 2025-05-15T14:00:00Z)"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in ISO 8601 format (e.g., 2025-05-15T15:00:00Z)"
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses. REQUIRED: Always include the email address of the person who requested the meeting so they receive an invitation. If the event is created from an email, use the sender's email address."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description"
                    }
                },
                "required": ["summary", "start_time", "end_time", "attendees"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hubspot_contact",
            "description": "Search for a contact in HubSpot by name or email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Contact name or email to search for"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_hubspot_contact",
            "description": "Create a new contact in HubSpot CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Contact email address (required)"
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Contact first name"
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Contact last name"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Contact phone number"
                    },
                    "company": {
                        "type": "string",
                        "description": "Company name"
                    }
                },
                "required": ["email"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_hubspot_note",
            "description": "Create a note for a HubSpot contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "string",
                        "description": "HubSpot contact ID"
                    },
                    "note": {
                        "type": "string",
                        "description": "Note content"
                    }
                },
                "required": ["contact_id", "note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get calendar events for a time period. Use this to check availability or find upcoming meetings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "Minimum time in ISO 8601 format (optional)"
                    },
                    "time_max": {
                        "type": "string",
                        "description": "Maximum time in ISO 8601 format (optional)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a task that needs to be completed over time (e.g., scheduling that requires waiting for email response).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "description": "Type of task (e.g., 'schedule_appointment', 'create_contact')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Task description"
                    },
                    "input_data": {
                        "type": "object",
                        "description": "Task input data and current state"
                    }
                },
                "required": ["task_type", "description", "input_data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_ongoing_instruction",
            "description": "Create an ongoing instruction that the AI will remember and apply automatically when specific events occur (e.g., emails, calendar events, HubSpot changes). Use this when the user asks you to remember something or set up an automation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "The instruction text describing what should happen (e.g., 'When someone emails me about booking a call, automatically create a calendar event')"
                    },
                    "trigger_type": {
                        "type": "string",
                        "description": "When to apply this instruction: 'email' (for email events), 'calendar' (for calendar events), 'hubspot' (for HubSpot events), or 'all' (for all events). If not specified, will be auto-detected from the instruction text.",
                        "enum": ["email", "calendar", "hubspot", "all"]
                    }
                },
                "required": ["instruction"]
            }
        }
    }
]


def detect_trigger_type(instruction: str) -> str:
    """
    Automatically detect the trigger type from instruction text using AI.
    
    Args:
        instruction: The instruction text
        
    Returns:
        Trigger type: "email", "calendar", "hubspot", or "all"
    """
    prompt = f"""Analyze this instruction and determine what type of event should trigger it:
"{instruction}"

The instruction should be triggered by:
- "email" if it mentions emails, messages, or receiving communications
- "calendar" if it mentions calendar events, meetings, appointments, or scheduling
- "hubspot" if it mentions HubSpot, contacts, CRM, or creating/updating contacts
- "all" if it applies to multiple types or is general

Respond with ONLY one word: email, calendar, hubspot, or all"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes instructions and determines trigger types. Respond with only one word."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=10
        )
        trigger_type = response.choices[0].message.content.strip().lower()
        
        # Validate response
        valid_types = ["email", "calendar", "hubspot", "all"]
        if trigger_type in valid_types:
            return trigger_type
        else:
            # Default to "all" if detection fails
            return "all"
    except Exception as e:
        print(f"Error detecting trigger type: {e}")
        return "all"


class AIAgent:
    """
    AI Agent that handles conversations, tool calling, and task management.
    """
    
    def __init__(self, db: Session, user: User):
        """
        Initialize AI Agent.
        
        Args:
            db: Database session
            user: User object with OAuth tokens
        """
        self.db = db
        self.user = user
        self.google_service = None
        self.hubspot_service = None
        
        # Initialize services if tokens available
        if user.google_access_token:
            self.google_service = GoogleService(user.google_access_token)
        if user.hubspot_access_token:
            self.hubspot_service = HubSpotService(user.hubspot_access_token)
    
    async def chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Process a chat message and return response.
        
        Args:
            message: User's message
            conversation_history: Previous conversation messages
            
        Returns:
            Dictionary with response text and any errors
        """
        if conversation_history is None:
            conversation_history = []
        
        # Get ongoing instructions
        ongoing_instructions = self.db.query(OngoingInstruction).filter(
            OngoingInstruction.user_id == self.user.id,
            OngoingInstruction.is_active == True
        ).all()
        
        # Build system prompt
        system_prompt = self._build_system_prompt(ongoing_instructions)
        
        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": message})
        
        try:
            # Call OpenAI with tool calling
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            # Handle response
            assistant_message = response.choices[0].message
            messages.append(assistant_message)
            
            # Execute tool calls if any
            tool_results = []
            if assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    result = await self._execute_tool(tool_call)
                    tool_results.append(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
                
                # Get final response after tool execution
                final_response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages
                )
                response_text = final_response.choices[0].message.content
            else:
                response_text = assistant_message.content
            
            return {
                "response": response_text,
                "error": None
            }
        
        except Exception as e:
            return {
                "response": None,
                "error": f"Error processing message: {str(e)}"
            }
    
    def _build_system_prompt(self, ongoing_instructions: List[OngoingInstruction]) -> str:
        """Build system prompt with ongoing instructions."""
        # Get current date and time
        current_datetime = datetime.now(timezone.utc)
        current_date_str = current_datetime.strftime("%Y-%m-%d")
        current_time_str = current_datetime.strftime("%H:%M:%S UTC")
        current_weekday = current_datetime.strftime("%A")
        
        prompt = f"""You are an AI assistant for a Financial Advisor. You help manage client relationships by:
- Answering questions about clients using information from emails and HubSpot CRM
- Performing actions like scheduling appointments, sending emails, creating contacts
- Remembering and following ongoing instructions

CRITICAL: Today is {current_date_str} ({current_weekday}) at {current_time_str}. 
When someone mentions relative dates like "next Tuesday", "tomorrow", "next week", you MUST calculate the actual date based on today's date ({current_date_str}).
Always use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ) for calendar event times.

Available integrations:
"""
        
        if self.google_service:
            prompt += "- Gmail: Read and send emails\n- Google Calendar: View and create events\n"
        if self.hubspot_service:
            prompt += "- HubSpot CRM: Search, create, and manage contacts and notes\n"
        
        if ongoing_instructions:
            prompt += "\n## Ongoing Instructions (always follow these):\n"
            for instruction in ongoing_instructions:
                prompt += f"- {instruction.instruction}\n"
        
        prompt += """
Be helpful, professional, and proactive. When scheduling appointments, handle the full flow including:
1. Finding the contact
2. Sending email with available times
3. Waiting for response
4. Creating calendar event when confirmed
5. Adding notes to HubSpot

Use tool calling to perform actions. Create tasks for multi-step processes that require waiting.

When creating calendar events:
- ALWAYS include the attendee's email address in the 'attendees' parameter so they receive an invitation
- If creating an event from an email, use the sender's email address as an attendee
- Calculate dates from relative terms (e.g., "next Tuesday", "tomorrow") based on TODAY's date
- Always use ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ (e.g., 2025-01-20T14:00:00Z)
- Ensure the date is in the future, not in the past
- Double-check your date calculations before creating events

If the user asks you to remember something or set up an automation (e.g., "when someone emails me...", "when I create a contact..."), use the create_ongoing_instruction tool to save it. The system will automatically detect the trigger type from the instruction text.
"""
        
        return prompt
    
    async def _execute_tool(self, tool_call) -> Dict:
        """
        Execute a tool call.
        
        Args:
            tool_call: Tool call object from OpenAI
            
        Returns:
            Tool execution result
        """
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        try:
            if function_name == "search_emails_and_contacts":
                context = get_relevant_context(
                    self.db,
                    self.user.id,
                    function_args["query"]
                )
                return {"success": True, "context": context}
            
            elif function_name == "send_email":
                if not self.google_service:
                    return {"success": False, "error": "Google not connected"}
                result = await self.google_service.send_email(
                    to=function_args["to"],
                    subject=function_args["subject"],
                    body=function_args["body"],
                    cc=function_args.get("cc")
                )
                return {"success": True, "message_id": result.get("id")}
            
            elif function_name == "create_calendar_event":
                if not self.google_service:
                    return {"success": False, "error": "Google not connected"}
                result = await self.google_service.create_calendar_event(
                    summary=function_args["summary"],
                    start_time=function_args["start_time"],
                    end_time=function_args["end_time"],
                    attendees=function_args.get("attendees"),
                    description=function_args.get("description")
                )
                return {"success": True, "event_id": result.get("id")}
            
            elif function_name == "search_hubspot_contact":
                if not self.hubspot_service:
                    return {"success": False, "error": "HubSpot not connected"}
                results = await self.hubspot_service.search_contacts(
                    query=function_args["query"]
                )
                return {"success": True, "contacts": results}
            
            elif function_name == "create_hubspot_contact":
                if not self.hubspot_service:
                    return {"success": False, "error": "HubSpot not connected"}
                result = await self.hubspot_service.create_contact(
                    email=function_args["email"],
                    first_name=function_args.get("first_name"),
                    last_name=function_args.get("last_name"),
                    phone=function_args.get("phone"),
                    company=function_args.get("company")
                )
                return {"success": True, "contact": result}
            
            elif function_name == "create_hubspot_note":
                if not self.hubspot_service:
                    return {"success": False, "error": "HubSpot not connected"}
                result = await self.hubspot_service.create_note(
                    contact_id=function_args["contact_id"],
                    note=function_args["note"]
                )
                return {"success": True, "note": result}
            
            elif function_name == "get_calendar_events":
                if not self.google_service:
                    return {"success": False, "error": "Google not connected"}
                results = await self.google_service.list_calendar_events(
                    time_min=function_args.get("time_min"),
                    time_max=function_args.get("time_max")
                )
                return {"success": True, "events": results}
            
            elif function_name == "create_task":
                # Create task in database
                task = Task(
                    user_id=self.user.id,
                    task_type=function_args["task_type"],
                    description=function_args["description"],
                    input_data=function_args["input_data"],
                    status="pending"
                )
                self.db.add(task)
                self.db.commit()
                return {"success": True, "task_id": task.id}
            
            elif function_name == "create_ongoing_instruction":
                # Create ongoing instruction
                instruction_text = function_args["instruction"]
                
                # Auto-detect trigger type if not provided
                trigger_type = function_args.get("trigger_type")
                if not trigger_type:
                    trigger_type = detect_trigger_type(instruction_text)
                
                # Create the instruction
                ongoing_instruction = OngoingInstruction(
                    user_id=self.user.id,
                    instruction=instruction_text,
                    trigger_type=trigger_type,
                    is_active=True
                )
                self.db.add(ongoing_instruction)
                self.db.commit()
                self.db.refresh(ongoing_instruction)
                
                return {
                    "success": True,
                    "instruction_id": ongoing_instruction.id,
                    "instruction": ongoing_instruction.instruction,
                    "trigger_type": ongoing_instruction.trigger_type
                }
            
            else:
                return {"success": False, "error": f"Unknown tool: {function_name}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def process_ongoing_instructions(
        self,
        trigger_type: str,
        trigger_data: Dict
    ) -> Optional[str]:
        """
        Process ongoing instructions when a trigger event occurs.
        
        Args:
            trigger_type: Type of trigger (email, calendar, hubspot)
            trigger_data: Data about the trigger event
            
        Returns:
            Optional response message if action was taken
        """
        # Get relevant ongoing instructions
        instructions = self.db.query(OngoingInstruction).filter(
            OngoingInstruction.user_id == self.user.id,
            OngoingInstruction.is_active == True,
            or_(
                OngoingInstruction.trigger_type == trigger_type,
                OngoingInstruction.trigger_type == "all"
            )
        ).all()
        
        if not instructions:
            return None
        
        # Get current date and time
        current_datetime = datetime.now(timezone.utc)
        current_date_str = current_datetime.strftime("%Y-%m-%d")
        current_time_str = current_datetime.strftime("%H:%M:%S UTC")
        current_weekday = current_datetime.strftime("%A")
        
        # Build prompt for AI to decide what to do
        prompt = f"""CRITICAL: Today is {current_date_str} ({current_weekday}) at {current_time_str}.

A {trigger_type} event occurred:
{json.dumps(trigger_data, indent=2)}

You have these ongoing instructions:
"""
        for instruction in instructions:
            prompt += f"- {instruction.instruction}\n"
        
        prompt += "\nShould you take any action? Use tools if needed."
        prompt += f"\n\nIMPORTANT: When calculating dates from relative terms (e.g., 'next Tuesday', 'tomorrow', 'next week'), use TODAY's date ({current_date_str}) to determine the actual future date. Always use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ) for calendar events. Ensure dates are in the future, not the past."
        prompt += "\n\nCRITICAL: When creating calendar events, ALWAYS include the attendee's email address in the 'attendees' parameter. If this event was triggered by an email, use the sender's email address (from the 'from' field in the event data above) as an attendee so they receive an invitation."
        
        result = await self.chat(prompt)
        return result.get("response")


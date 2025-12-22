# Financial Advisor AI Agent

A comprehensive AI agent for Financial Advisors that integrates with Gmail, Google Calendar, and HubSpot. The agent can answer questions about clients using RAG and perform actions through tool calling.

## Project Structure

```
Jump-agent/
├── backend/          # FastAPI backend
├── frontend/         # Next.js frontend
└── README.md         # This file
```

## Prerequisites

Before starting, ensure you have:
- Python 3.11+ installed
- Node.js 18+ and npm/yarn installed
- PostgreSQL 14+ installed and running
- Google Cloud Console account (for OAuth)
- HubSpot account (free tier works)

## Step-by-Step Setup

### 1. Database Setup

1. **Install PostgreSQL** (if not already installed):
   - Windows: Download from [postgresql.org](https://www.postgresql.org/download/windows/)
   - Mac: `brew install postgresql` or download from postgresql.org
   - Linux: `sudo apt-get install postgresql` (Ubuntu/Debian)

2. **Start PostgreSQL service**:
   - Windows: Services app → Start "postgresql-x64-XX" service
   - Mac/Linux: `sudo service postgresql start` or `brew services start postgresql`

3. **Create a new database**:
   ```bash
   # Connect to PostgreSQL
   psql -U postgres
   
   # Create database
   CREATE DATABASE financial_advisor_agent;
   
   # Connect to the new database
   \c financial_advisor_agent
   
   # Install pgvector extension
   CREATE EXTENSION vector;
   
   # Exit
   \q
   ```

   **Note**: You may need to install pgvector separately:
   - Mac: `brew install pgvector`
   - Linux: Follow instructions at [github.com/pgvector/pgvector](https://github.com/pgvector/pgvector)
   - Windows: Download from pgvector releases

### 2. Backend Setup

1. **Navigate to backend directory**:
   ```bash
   cd backend
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment**:
   - **Windows PowerShell**: `venv\Scripts\Activate.ps1`
   - **Windows CMD**: `venv\Scripts\activate.bat`
   - **Mac/Linux**: `source venv/bin/activate`

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**:
   - Copy `.env.example` to `.env`:
     ```bash
     # Windows
     copy .env.example .env
     
     # Mac/Linux
     cp .env.example .env
     ```
   - Open `.env` and fill in all required values (see Configuration section below)

6. **Run database migrations**:
   ```bash
   # Make sure you're in the backend directory with venv activated
   alembic upgrade head
   ```

7. **Start the backend server**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

   You should see output like:
   ```
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
   INFO:     Started reloader process
   INFO:     Started server process
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   ```

### 3. Frontend Setup

1. **Navigate to frontend directory** (in a new terminal):
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```
   
   This may take a few minutes. If you encounter errors, try:
   ```bash
   npm install --legacy-peer-deps
   ```

3. **Set up environment variables**:
   - Copy `.env.example` to `.env.local`:
     ```bash
     # Windows
     copy .env.example .env.local
     
     # Mac/Linux
     cp .env.example .env.local
     ```
   - Open `.env.local` and verify `NEXT_PUBLIC_API_URL=http://localhost:8000`

4. **Start the development server**:
   ```bash
   npm run dev
   ```

   You should see:
   ```
   ▲ Next.js 14.0.4
   - Local:        http://localhost:3000
   ```

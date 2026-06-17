# FormPilot AI

<div align="center">
  <h3>The Intelligent Form Automation Agent</h3>
  <p>An advanced, AI-powered system that securely parses resumes and intelligently automates form-filling across the web using human-like browser automation.</p>
</div>

---

## 🚀 Overview

FormPilot is a comprehensive full-stack MVP designed to automate complex, multi-page form submissions (like job applications). It leverages the **Gemini LLM API** along with sophisticated rule-based matching and Playwright browser automation to map user profile data accurately to dynamic web forms.

## ✨ Key Features & Techniques

- **Intelligent Profile Parsing**: Upload a resume (PDF). The backend extracts text using `pypdf` and uses the **Gemini API** to convert unstructured resume data into a heavily structured Pydantic schema (JSON).
- **Hybrid AI Field Mapping Engine**: Uses a two-pronged approach for assigning values to detected fields:
  - **Rule-Based Engine**: Uses text normalization, abbreviation expansion (e.g., matching "CS" to "Computer Science"), exact matches, and fuzzy scoring (`difflib.SequenceMatcher`).
  - **LLM Fallback**: If rules fail to find a high-confidence match, the engine delegates complex decisions to the Gemini LLM.
- **Smart Form Scanning**: Playwright traverses target DOM structures, identifying inputs, selects, multiselects, and textareas, grouping them into a logical field schema.
- **Live Collaborative Workspace**: A split-screen interface displaying real-time execution logs alongside an interactive AI chat. You can edit the mapping plan before execution.
- **Human-Like Browser Automation**: Playwright natively injects fields directly into the active page using synthetic `focus`, `type` (with random delays), and dispatching `input`/`change` events to ensure SPA frameworks (React/Vue) register the changes.
- **Real-Time Streaming**: Live execution screenshots and progress events are streamed from the Playwright runner directly to the frontend via native WebSockets.

## 🛠️ Technology Stack (Current Implementation)

### Frontend
- **Framework**: Next.js 15+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS & shadcn/ui inspired layouts
- **State Management**: Zustand
- **Forms & Validation**: React Hook Form + Zod
- **Animations & Icons**: Framer Motion & Lucide-React
- **Aesthetics**: Soft Lavender theme (`#F3F0FA`), white floating cards, and dynamic purple gradients.

### Backend
- **Framework**: FastAPI (Python)
- **Concurrency**: `asyncio` Event Loop
- **AI / LLM**: Google GenAI SDK (Gemini API)
- **Browser Automation**: Playwright (`async_playwright`)
- **Data Persistence (MVP)**: In-memory session state dictionaries (`active_profiles`, `active_runs`, etc.) backed by a local JSON disk cache (`profiles_cache.json`) for persistence across server restarts.
- **Real-Time Communication**: FastAPI native `WebSocket` (No Redis or Pub/Sub used in this MVP version).

## 📂 Project Structure

```text
/
├── frontend/           # Next.js Application
│   ├── src/app/        # App Router pages (auth, dashboard, live workspace)
│   ├── src/components/ # Reusable UI components
│   └── src/store/      # Zustand state stores
├── backend/            # FastAPI Application
│   ├── main.py         # REST Controllers, WebSockets, & Playwright Runner
│   ├── ai_service.py   # Resume parsing, fuzzy matching, and rule-based mapping engine
│   ├── browser_service.py # Playwright DOM form scanning
│   └── requirements.txt# Backend Python dependencies
└── PROJECT_RULES.md    # Target Architectural Guidelines
```

## 🚦 Getting Started (Local Development)

### Prerequisites
- Node.js (v20+)
- Python (3.10+)
- A Gemini API Key (`GEMINI_API_KEY`)

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Backend Setup
```bash
cd backend
python -m venv venv
# On Windows: venv\Scripts\activate
# On Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
playwright install chromium

# Create a .env file and add your GEMINI_API_KEY
echo "GEMINI_API_KEY=your_api_key_here" > .env

# Start FastAPI server
python -m uvicorn main:app --port 8000 --reload
```

## 📜 Development Notes

This project was developed as an MVP focused on solving the core problem effectively: extracting candidate information from resumes and automating web form completion with real-time visibility and user control.

The current implementation emphasizes simplicity, rapid execution, and maintainability while providing a foundation for future scalability and additional automation capabilities.


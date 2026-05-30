# Browser Use Web Demo

A web interface for [browser-use](https://github.com/browser-use/browser-use) AI browser automation.

## Quick Start

### Local Development

1. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Start the backend:
   ```bash
   cd backend
   python main.py
   ```

3. Start the frontend dev server (separate terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Open http://localhost:5173

### Docker

```bash
docker-compose up
```

Open http://localhost:8000

## Usage

1. Go to **Settings** and configure at least one LLM provider
2. Go to **Home**, type a task, select a model, and click Execute
3. Watch the AI browser automation run in real-time

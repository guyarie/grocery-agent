# Grocery Automation - Kroger MVP

A minimal viable product for grocery automation featuring LLM-powered receipt parsing and Kroger API integration.

## Features

- Upload Amazon Fresh receipts (PDF/image)
- Extract items using Google Gemini LLM
- Match products via Kroger Products API
- Add items to Kroger cart with one click
- Cart view to review, remove items, and check out
- Receipt history and reordering

## Prerequisites

1. **pyenv** - Python version management
2. **uv** - Fast Python package manager
3. **Node.js** - For React frontend

## Setup

### 1. Install Python 3.11.9

```bash
pyenv install 3.11.9
pyenv local 3.11.9
```

### 2. Create Virtual Environment and Install Dependencies

```bash
uv venv
uv pip install -e ".[dev]"
```

### 3. Activate Virtual Environment

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and add your API credentials
```

### 5. Run Backend

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

### 6. Run Frontend

```bash
cd frontend
npm install
npm start
```

## Project Structure

```
├── src/              # Backend source code
├── tests/            # Test suite
├── frontend/         # React frontend
├── config/           # Configuration files
├── data/             # Data storage (receipts, database)
├── docs/             # Documentation
├── pyproject.toml    # Python dependencies
├── .python-version   # Python version
└── .env              # Environment variables
```

## Development

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black src/ tests/
```

### Linting

```bash
ruff check src/ tests/
```

### Type Checking

```bash
mypy src/
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT

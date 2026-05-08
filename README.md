# ⚡ MultiThread File Processor — v4 (Patterns Edition)

Streamlit web app that processes CSV, TXT, and PDF files in parallel using `concurrent.futures.ThreadPoolExecutor`.

---

## 🏛 Architecture Pattern — Layered Architecture (3-Tier)

```
┌──────────────────────────────────────────────────────┐
│  Layer 3 — Presentation     app.py                   │
│             Streamlit UI — renders results, wires    │
│             observers, calls Factory                 │
│                       │                              │
│  Layer 2 — Business Logic   layers/business_layer.py │
│             Workers, parallel executor, JSON builder  │
│             Uses Strategy, Singleton, Observer        │
│                       │                              │
│  Layer 1 — Data Access      layers/data_layer.py     │
│             File I/O only — raw bytes                │
└──────────────────────────────────────────────────────┘
```

**Rule:** Each layer depends ONLY on the layer directly below it.

---

## ♟ Design Pattern 1 — Strategy Pattern

**File:** `patterns/strategy.py`

```
TextExtractionStrategy        ← Abstract Strategy
    ├── TxtExtractionStrategy ← Concrete Strategy A
    ├── CsvExtractionStrategy ← Concrete Strategy B
    └── PdfExtractionStrategy ← Concrete Strategy C

TextExtractor                 ← Context (used by business layer)
```

Adding DOCX support = one new class. Zero existing code changes.

---

## 👁 Design Pattern 2 — Observer Pattern

**File:** `patterns/observer.py`

```
Worker Thread → ProgressNotifier (Subject) → ProgressEvent
                     └─► StreamlitProgressObserver → st.progress()
                     └─► LogProgressObserver       → logger.info()
```

Workers never import Streamlit. UI is fully decoupled from business logic.

---

## 🔒 Design Pattern 3 — Singleton Pattern

**File:** `patterns/singleton.py`

```python
class ThreadPoolManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ...   # create once
        return cls._instance
```

All 4 tabs share **one** ThreadPoolExecutor — prevents thread explosion.

---

## 🏭 Design Pattern 4 — Factory Pattern

**File:** `patterns/factory.py`

```python
processor = FileProcessorFactory.create("search")
# Returns _worker_search — tab never imports it directly
```

Tabs are fully decoupled from worker function names.

---

## 📁 Project Structure

```
project/
├── app.py                    ← Layer 3: Presentation
├── requirements.txt
├── README.md
├── layers/
│   ├── data_layer.py         ← Layer 1: Data Access
│   └── business_layer.py    ← Layer 2: Business Logic
└── patterns/
    ├── strategy.py           ← Strategy Pattern
    ├── observer.py           ← Observer Pattern
    ├── singleton.py          ← Singleton Pattern
    └── factory.py            ← Factory Pattern
```

---

## 🚀 Quick Start

```bash
python -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows

pip install -r requirements.txt
streamlit run app.py
```

Opens at **http://localhost:8501**

---

## 🧩 Features

| Tab | Feature |
|---|---|
| 🔍 Text Search | Parallel keyword search — all file types |
| 📊 File Statistics | Word / line / char / paragraph counts + charts |
| 💬 Sentiment Analysis | VADER scoring + word frequency charts |
| 🗃️ Merge to JSON | All files → one unified JSON |
| 📐 Patterns Reference | Live code documentation of all patterns |

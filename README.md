# ⚡ MultiThread File Processor — v5

Streamlit app that processes CSV, TXT, PDF files in parallel with `ThreadPoolExecutor`.

## 🚀 Quick Start
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 🏛 Architecture — Layered (3-Tier)
| Layer | File | Responsibility |
|---|---|---|
| Presentation | `app.py` | Streamlit UI only |
| Business Logic | `layers/business_layer.py` | Workers, executor, JSON builder |
| Data Access | `layers/data_layer.py` | File I/O only |

## ♟ Design Patterns
| Pattern | File | Role |
|---|---|---|
| Strategy | `patterns/design_patterns.py` | Txt/Csv/Pdf extraction algorithms |
| Factory | `patterns/design_patterns.py` | `FileProcessorFactory.create(task)` |
| Observer | `patterns/design_patterns.py` | `ProgressNotifier` → UI observers |
| Singleton | `patterns/design_patterns.py` | One shared `ThreadPoolManager` |

## ⚡ Why MultiThread is Faster
Python's GIL is released during I/O (file reads, network, sleep).
`ThreadPoolExecutor` overlaps the waiting time across all workers simultaneously.
Sequential: waits add up. Parallel: all wait at the same time → total ≈ 1 file's wait.

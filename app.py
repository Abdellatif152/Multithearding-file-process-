"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MultiThread File Processor — v5 (Full Patterns Edition)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARCHITECTURE PATTERN — LAYERED ARCHITECTURE (3-Tier)
  Layer 3 ← THIS FILE  (Presentation — Streamlit UI only)
  Layer 2 ← layers/business_layer.py  (Business Logic)
  Layer 1 ← layers/data_layer.py      (Data Access — I/O only)

DESIGN PATTERNS
  Strategy  → TextExtractor + TxtStrategy / CsvStrategy / PdfStrategy
  Factory   → FileProcessorFactory.create(task) returns the right worker
  Observer  → ProgressNotifier → StreamlitProgressObserver + LogProgressObserver
  Singleton → ThreadPoolManager (one shared ThreadPoolExecutor for all tabs)
"""

import os
import sys
import time
import logging
import collections
from datetime import datetime

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

# ── Layer 2 ───────────────────────────────────────────────────────────────────
from layers.business_layer import (
    run_parallel, run_sequential, build_merged_json,
    worker_search_timed, worker_stats_timed,
    worker_sentiment_timed, worker_json_timed,
)
# ── Patterns ──────────────────────────────────────────────────────────────────
from patterns.design_patterns import (
    MAX_WORKERS, PDF_BACKEND,
    FileProcessorFactory,
    ProgressNotifier, StreamlitProgressObserver, LogProgressObserver,
    ThreadPoolManager,
)

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    import plotly.express as px
    PLOTLY = True
except ImportError:
    PLOTLY = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # noqa
    VADER = True
except ImportError:
    VADER = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MTFP.UI")

# Warm up Singleton at startup
ThreadPoolManager()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="MultiThread File Processor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');
:root{--bg:#0d0f14;--surface:#13161e;--card:#1a1e2a;--border:#252a38;
      --accent:#00e5ff;--purple:#7c3aed;--amber:#f59e0b;--text:#e2e8f0;
      --muted:#64748b;--red:#ef4444;--green:#22c55e;}
html,body,.stApp{background:var(--bg)!important;color:var(--text);font-family:'Syne',sans-serif;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border);}
[data-testid="stSidebar"] *{color:var(--text)!important;}

.app-header{text-align:center;padding:2rem 0 1rem;border-bottom:1px solid var(--border);margin-bottom:1.5rem;}
.app-header h1{font-family:'Syne',sans-serif;font-weight:800;font-size:2.5rem;margin:0;
  background:linear-gradient(90deg,var(--accent),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.app-header p{color:var(--muted);font-family:'JetBrains Mono',monospace;font-size:.76rem;margin-top:.4rem;}

.badge-row{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:center;margin:.5rem 0 1rem;}
.badge{font-family:'JetBrains Mono',monospace;font-size:.65rem;font-weight:700;
  padding:.25rem .7rem;border-radius:999px;border:1px solid;}
.badge-arch{color:var(--accent);border-color:var(--accent);background:rgba(0,229,255,.08);}
.badge-pat{color:var(--purple);border-color:var(--purple);background:rgba(124,58,237,.08);}

[data-testid="stTabs"] [role="tablist"]{gap:.4rem;background:var(--surface);
  padding:.4rem;border-radius:10px;border:1px solid var(--border);}
[data-testid="stTabs"] [role="tab"]{background:transparent!important;color:var(--muted)!important;
  border-radius:7px!important;font-family:'Syne',sans-serif!important;font-weight:700!important;}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{
  background:linear-gradient(135deg,var(--purple),var(--accent))!important;color:#fff!important;}

.m-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.8rem;margin:1rem 0;}
.m-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1rem;text-align:center;}
.m-card .v{font-size:1.5rem;font-weight:800;font-family:'JetBrains Mono',monospace;color:var(--accent);}
.m-card .l{font-size:.7rem;color:var(--muted);margin-top:.25rem;}

.box-info{background:rgba(0,229,255,.07);border-left:3px solid var(--accent);
  border-radius:0 8px 8px 0;padding:.7rem 1rem;margin:.7rem 0;font-size:.86rem;}
.box-warn{background:rgba(245,158,11,.07);border-left:3px solid var(--amber);
  border-radius:0 8px 8px 0;padding:.7rem 1rem;margin:.7rem 0;font-size:.86rem;color:var(--amber);}
.box-err{background:rgba(239,68,68,.07);border-left:3px solid var(--red);
  border-radius:0 8px 8px 0;padding:.7rem 1rem;margin:.7rem 0;font-size:.86rem;color:var(--red);}
.box-pat{background:rgba(124,58,237,.07);border-left:3px solid var(--purple);
  border-radius:0 8px 8px 0;padding:.7rem 1rem;margin:.7rem 0;
  font-size:.82rem;color:#c4b5fd;font-family:'JetBrains Mono',monospace;}

.tc-wrap{display:flex;gap:.8rem;margin:1rem 0;flex-wrap:wrap;}
.tc-card{flex:1;min-width:180px;background:var(--card);border:1px solid var(--border);
  border-radius:10px;padding:1.2rem;text-align:center;}
.tc-card.s{border-color:var(--amber);}.tc-card.m{border-color:var(--green);}
.tc-val{font-size:2rem;font-weight:800;font-family:'JetBrains Mono',monospace;}
.tc-card.s .tc-val{color:var(--amber);}.tc-card.m .tc-val{color:var(--green);}
.tc-lbl{font-size:.72rem;color:var(--muted);margin-top:.3rem;}

.sec{font-family:'Syne',sans-serif;font-weight:800;font-size:1rem;color:var(--accent);
  margin:1.2rem 0 .6rem;display:flex;align-items:center;gap:.5rem;}
.sec::after{content:'';flex:1;height:1px;background:var(--border);}

.stButton>button{background:linear-gradient(135deg,var(--purple),var(--accent))!important;
  color:#fff!important;border:none!important;border-radius:8px!important;
  font-family:'Syne',sans-serif!important;font-weight:700!important;padding:.5rem 1.5rem!important;}
.stDownloadButton>button{background:var(--card)!important;color:var(--accent)!important;
  border:1px solid var(--accent)!important;border-radius:8px!important;
  font-family:'Syne',sans-serif!important;font-weight:700!important;}
.stProgress>div>div{background:var(--accent)!important;}
.stTextInput input,.stSelectbox select,.stNumberInput input{
  background:var(--card)!important;border:1px solid var(--border)!important;
  color:var(--text)!important;border-radius:8px!important;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="app-header">
  <h1>⚡ MultiThread File Processor</h1>
  <p>ThreadPoolExecutor · {MAX_WORKERS} workers · CSV · TXT · PDF · v5</p>
</div>
<div class="badge-row">
  <span class="badge badge-arch">🏛 Layered Architecture</span>
  <span class="badge badge-pat">♟ Strategy Pattern</span>
  <span class="badge badge-pat">🏭 Factory Pattern</span>
  <span class="badge badge-pat">👁 Observer Pattern</span>
  <span class="badge badge-pat">🔒 Singleton Pattern</span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
if "file_store" not in st.session_state:
    st.session_state.file_store = {}

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.markdown("---")
    mode = st.radio("Input Mode", ["📁 Upload Files", "📂 Folder Path"], index=0)

    if mode == "📁 Upload Files":
        uploads = st.file_uploader(
            "Upload Files (CSV, TXT, PDF)",
            type=["csv", "txt", "pdf"],
            accept_multiple_files=True,
        )
        if uploads:
            store = {f.name: f.read() for f in uploads}
            st.session_state.file_store = store
            st.success(f"✅ {len(store)} file(s) ready")
            for name, raw in store.items():
                st.markdown(f"<small>• {name} ({len(raw)/1024:.1f} KB)</small>",
                            unsafe_allow_html=True)
    else:
        from layers.data_layer import FileRepository
        folder = st.text_input("Folder Path", placeholder="/path/to/folder")
        if folder:
            store = FileRepository.from_folder(folder)
            if store:
                st.session_state.file_store = store
                st.success(f"✅ {len(store)} file(s) found")
            else:
                st.error("❌ Folder not found or empty")

    st.markdown("---")
    n = len(st.session_state.file_store)
    st.markdown(f"""
    <div style='font-size:.74rem;color:#64748b;font-family:"JetBrains Mono",monospace;'>
    <b>Runtime Info</b><br>
    Files loaded  : <code>{n}</code><br>
    Workers       : <code>{MAX_WORKERS}</code><br>
    PDF backend   : <code>{PDF_BACKEND}</code><br>
    Plotly        : <code>{'✅' if PLOTLY else '❌'}</code><br>
    VADER         : <code>{'✅' if VADER else '❌'}</code>
    </div>
    <hr>
    <div style='font-size:.70rem;color:#64748b;font-family:"JetBrains Mono",monospace;'>
    <b>Patterns Active</b><br>
    🏛 Layered Architecture (3 layers)<br>
    ♟ Strategy → Txt / Csv / Pdf<br>
    🏭 Factory → FileProcessorFactory<br>
    👁 Observer → Notifier + StreamlitObs<br>
    🔒 Singleton → ThreadPoolManager
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _no_files():
    st.markdown('<div class="box-warn">⚠️ No files loaded — upload files or set a folder path in the sidebar.</div>',
                unsafe_allow_html=True)


def _render_timing(single_t: float, multi_t: float):
    speedup = single_t / multi_t if multi_t > 0 else 1.0
    saved   = max(0.0, single_t - multi_t)
    pct     = max(0.0, (1 - multi_t / single_t) * 100) if single_t > 0 else 0

    if speedup >= 2.5:
        grad, emoji = "linear-gradient(135deg,#7c3aed,#22c55e)", "🚀"
    elif speedup >= 1.5:
        grad, emoji = "linear-gradient(135deg,#7c3aed,#00e5ff)", "⚡"
    else:
        grad, emoji = "linear-gradient(135deg,#f59e0b,#ef4444)", "⚠️"

    st.markdown(f"""
    <div class="tc-wrap">
      <div class="tc-card s">
        <div class="tc-val">{single_t:.2f}s</div>
        <div class="tc-lbl">🐌 Single Thread<br>1 file at a time (sequential)</div>
      </div>
      <div class="tc-card m">
        <div class="tc-val">{multi_t:.2f}s</div>
        <div class="tc-lbl">⚡ MultiThread<br>{MAX_WORKERS} workers in parallel</div>
      </div>
    </div>
    <div style="{grad};border-radius:10px;padding:.7rem 1.2rem;
                font-weight:800;color:#fff;text-align:center;
                font-size:1.1rem;margin-top:.5rem;font-family:'Syne',sans-serif;">
      {emoji} Speedup <b>{speedup:.2f}×</b> &nbsp;|&nbsp;
      Saved <b>{saved:.2f}s</b> &nbsp;|&nbsp; <b>{pct:.0f}%</b> faster
    </div>
    <div style="font-size:.76rem;color:#64748b;font-family:'JetBrains Mono',monospace;
                margin-top:.6rem;padding:.5rem .8rem;background:#13161e;border-radius:8px;
                border-left:3px solid #252a38;">
      💡 <b>Why threads win:</b>
      Sequential → file1 wait… file2 wait… file3 wait… (waits add up)<br>
      Parallel &nbsp;→ file1 ┐<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;file2 ├── all waiting at the same time → total ≈ 1 file's wait<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;file3 ┘
      &nbsp; (GIL released during I/O — threads run freely)
    </div>
    """, unsafe_allow_html=True)


def _make_notifier(bar, label: str) -> ProgressNotifier:
    """
    Observer Pattern — wire a Streamlit widget to the business-layer notifier.
    Presentation layer creates observers; business layer never sees Streamlit.
    """
    n = ProgressNotifier()
    n.subscribe(StreamlitProgressObserver(bar))
    n.subscribe(LogProgressObserver())
    return n


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _dark(fig):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_family="Syne",
        font_color="#e2e8f0",
    )
    return fig


COLORS = ["#00e5ff", "#7c3aed", "#f59e0b", "#22c55e", "#ef4444"]


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🔍  Text Search",
    "📊  File Statistics",
    "💬  Sentiment Analysis",
    "🗃️  Merge to JSON",
])


# ╔══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TEXT SEARCH
# ╚══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="sec">🔍 Search Text Across Files</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-info">Searches all loaded files concurrently using ThreadPoolExecutor. Results include file name, line number, context, and occurrence count.</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-pat">♟ Strategy → TextExtractor picks TxtStrategy / CsvStrategy / PdfStrategy per file.<br>🏭 Factory → FileProcessorFactory.create("search") returns the worker.<br>👁 Observer → ProgressNotifier fires events; StreamlitProgressObserver updates the bar.<br>🔒 Singleton → all tabs share one ThreadPoolManager executor.</div>', unsafe_allow_html=True)

    col_q, col_cs = st.columns([4, 1])
    with col_q:
        query = st.text_input("Search Query", placeholder="Type a keyword or phrase…", key="t1_q")
    with col_cs:
        case_sen = st.checkbox("Case Sensitive", value=False, key="t1_cs")

    if st.button("⚡ Search All Files", key="t1_run"):
        store = st.session_state.file_store
        if not store:
            _no_files()
        elif not query.strip():
            st.warning("Please enter a search query.")
        else:
            # Factory Pattern: get the right worker
            worker = FileProcessorFactory.create("search")
            tasks  = [(name, raw, query, case_sen) for name, raw in store.items()]

            # ── Sequential baseline ──
            t0 = time.perf_counter()
            run_sequential(worker, tasks)
            single_t = time.perf_counter() - t0

            # ── Parallel run ──
            bar      = st.progress(0, text="Searching…")
            notifier = _make_notifier(bar, "Searched")        # Observer wired
            t0       = time.perf_counter()
            nested   = run_parallel(worker, tasks, "Searched", notifier)
            multi_t  = time.perf_counter() - t0
            bar.empty()

            all_rows = [row for batch in nested for row in batch]
            _render_timing(single_t, multi_t)
            st.markdown("---")

            if not all_rows:
                st.markdown(f'<div class="box-warn">No matches found for "<b>{query}</b>" in {len(tasks)} file(s).</div>',
                            unsafe_allow_html=True)
            else:
                df = pd.DataFrame(all_rows)
                total_hits = int(df["Occurrences"].sum())
                st.markdown(f"""
                <div class="m-row">
                  <div class="m-card"><div class="v">{total_hits:,}</div><div class="l">Total Hits</div></div>
                  <div class="m-card"><div class="v">{df['File'].nunique()}</div><div class="l">Files Matched</div></div>
                  <div class="m-card"><div class="v">{len(all_rows):,}</div><div class="l">Match Locations</div></div>
                  <div class="m-card"><div class="v">{len(tasks)}</div><div class="l">Files Searched</div></div>
                </div>""", unsafe_allow_html=True)

                st.markdown('<div class="sec">📋 Search Results</div>', unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True, height=420)

                if PLOTLY:
                    hits_by_file = df.groupby("File")["Occurrences"].sum().reset_index()
                    st.plotly_chart(_dark(px.bar(
                        hits_by_file, x="File", y="Occurrences",
                        title=f'Hits per File — query: "{query}"',
                        template="plotly_dark",
                        color_discrete_sequence=COLORS,
                    )), use_container_width=True)

                st.download_button("⬇️ Download Results CSV", _csv(df),
                                   f"search_{datetime.now():%Y%m%d_%H%M%S}.csv",
                                   "text/csv", key="t1_dl")


# ╔══════════════════════════════════════════════════════════════════════════════
# TAB 2 — FILE STATISTICS
# ╚══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="sec">📊 File Statistics Analyzer</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-info">Computes word count, character count, line count, paragraph count, top word, and MD5 checksum for every file — all in parallel.</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-pat">♟ Strategy → CsvExtractionStrategy / TxtExtractionStrategy / PdfExtractionStrategy.<br>🏭 Factory → FileProcessorFactory.create("stats") returns the worker.<br>👁 Observer → ProgressNotifier decouples worker progress from Streamlit.<br>🔒 Singleton → ThreadPoolManager reused — no new pool created per click.</div>', unsafe_allow_html=True)

    if st.button("⚡ Analyze All Files", key="t2_run"):
        store = st.session_state.file_store
        if not store:
            _no_files()
        else:
            worker = FileProcessorFactory.create("stats")
            tasks  = [(name, raw) for name, raw in store.items()]

            t0 = time.perf_counter()
            run_sequential(worker, tasks)
            single_t = time.perf_counter() - t0

            bar      = st.progress(0, text="Analyzing…")
            notifier = _make_notifier(bar, "Analyzed")
            t0       = time.perf_counter()
            results  = run_parallel(worker, tasks, "Analyzed", notifier)
            multi_t  = time.perf_counter() - t0
            bar.empty()

            _render_timing(single_t, multi_t)
            st.markdown("---")

            df = pd.DataFrame(results).sort_values("Words", ascending=False).reset_index(drop=True)

            st.markdown(f"""
            <div class="m-row">
              <div class="m-card"><div class="v">{len(df)}</div><div class="l">Files Analyzed</div></div>
              <div class="m-card"><div class="v">{df['Words'].sum():,}</div><div class="l">Total Words</div></div>
              <div class="m-card"><div class="v">{df['Lines'].sum():,}</div><div class="l">Total Lines</div></div>
              <div class="m-card"><div class="v">{df['Characters'].sum():,}</div><div class="l">Total Characters</div></div>
              <div class="m-card"><div class="v">{df['Size (KB)'].sum():.1f} KB</div><div class="l">Total Size</div></div>
            </div>""", unsafe_allow_html=True)

            st.markdown('<div class="sec">📋 Statistics Table</div>', unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)

            if PLOTLY and len(df) > 0:
                c1, c2 = st.columns(2)
                with c1:
                    st.plotly_chart(_dark(px.bar(df, x="File", y="Words", color="Type",
                        title="Word Count per File", template="plotly_dark",
                        color_discrete_sequence=COLORS)), use_container_width=True)
                with c2:
                    st.plotly_chart(_dark(px.bar(df, x="File", y="Lines", color="Type",
                        title="Line Count per File", template="plotly_dark",
                        color_discrete_sequence=COLORS)), use_container_width=True)
                c3, c4 = st.columns(2)
                with c3:
                    st.plotly_chart(_dark(px.pie(df, values="Words", names="File",
                        title="Word Distribution", template="plotly_dark",
                        color_discrete_sequence=COLORS)), use_container_width=True)
                with c4:
                    st.plotly_chart(_dark(px.scatter(df, x="Characters", y="Lines",
                        size="Size (KB)", color="Type", hover_data=["File"],
                        title="Characters vs Lines", template="plotly_dark",
                        color_discrete_sequence=COLORS)), use_container_width=True)
            else:
                st.bar_chart(df.set_index("File")[["Words", "Lines"]])

            st.download_button("⬇️ Download Statistics CSV", _csv(df),
                               f"stats_{datetime.now():%Y%m%d_%H%M%S}.csv",
                               "text/csv", key="t2_dl")


# ╔══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SENTIMENT ANALYSIS
# ╚══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="sec">💬 Sentiment Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-info">VADER sentiment scoring — compound, positive, neutral, negative scores for every file. Optional keyword filter to analyse only relevant lines.</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-pat">♟ Strategy → PdfExtractionStrategy used inside worker for PDF files.<br>🏭 Factory → FileProcessorFactory.create("sentiment") returns the worker.<br>👁 Observer → each completed future fires notifier.notify() → StreamlitProgressObserver.<br>🔒 Singleton → same ThreadPoolManager pool shared across all tabs.</div>', unsafe_allow_html=True)

    if not VADER:
        st.markdown('<div class="box-err">❌ vaderSentiment not installed — run: <code>pip install vaderSentiment</code></div>',
                    unsafe_allow_html=True)
    else:
        kw = st.text_input(
            "Optional keyword filter (analyse only lines containing this word)",
            placeholder="e.g. product / price / quality",
            key="t3_kw",
        )

        if st.button("⚡ Analyse Sentiment", key="t3_run"):
            store = st.session_state.file_store
            if not store:
                _no_files()
            else:
                worker = FileProcessorFactory.create("sentiment")
                tasks  = [(name, raw, kw) for name, raw in store.items()]

                t0 = time.perf_counter()
                run_sequential(worker, tasks)
                single_t = time.perf_counter() - t0

                bar      = st.progress(0, text="Analysing sentiment…")
                notifier = _make_notifier(bar, "Analysed")
                t0       = time.perf_counter()
                results  = run_parallel(worker, tasks, "Analysed", notifier)
                multi_t  = time.perf_counter() - t0
                bar.empty()

                _render_timing(single_t, multi_t)
                st.markdown("---")

                valid  = [r for r in results if r.get("Compound") is not None]
                errors = [r for r in results if r.get("Compound") is None]

                for e in errors:
                    st.markdown(f'<div class="box-err">⚠️ {e["File"]}: {e.get("error")}</div>',
                                unsafe_allow_html=True)

                if valid:
                    df = pd.DataFrame([{k: v for k, v in r.items() if k != "Word_Freq"}
                                       for r in valid])
                    avg_c = df["Compound"].mean()
                    pos_c = (df["Label"] == "positive").sum()
                    neg_c = (df["Label"] == "negative").sum()
                    neu_c = (df["Label"] == "neutral").sum()

                    st.markdown(f"""
                    <div class="m-row">
                      <div class="m-card"><div class="v">{avg_c:+.3f}</div><div class="l">Avg Compound Score</div></div>
                      <div class="m-card"><div class="v" style="color:var(--green)">{pos_c}</div><div class="l">Positive Files</div></div>
                      <div class="m-card"><div class="v" style="color:var(--amber)">{neu_c}</div><div class="l">Neutral Files</div></div>
                      <div class="m-card"><div class="v" style="color:var(--red)">{neg_c}</div><div class="l">Negative Files</div></div>
                      <div class="m-card"><div class="v">{len(valid)}</div><div class="l">Files Scored</div></div>
                    </div>""", unsafe_allow_html=True)

                    st.markdown('<div class="sec">📋 Sentiment Scores Table</div>', unsafe_allow_html=True)
                    st.dataframe(df, use_container_width=True)

                    if PLOTLY:
                        cmap = {"positive": "#22c55e", "neutral": "#f59e0b", "negative": "#ef4444"}

                        c1, c2 = st.columns(2)
                        with c1:
                            lc = df["Label"].value_counts().reset_index()
                            lc.columns = ["Label", "Count"]
                            st.plotly_chart(_dark(px.pie(
                                lc, values="Count", names="Label",
                                title="Sentiment Distribution",
                                template="plotly_dark",
                                color="Label", color_discrete_map=cmap,
                            )), use_container_width=True)
                        with c2:
                            st.plotly_chart(_dark(px.bar(
                                df, x="File", y="Compound",
                                color="Label",
                                title="Compound Score per File",
                                template="plotly_dark",
                                color_discrete_map=cmap,
                            )), use_container_width=True)

                        # Stacked positive / neutral / negative bars
                        st.markdown('<div class="sec">📊 Score Breakdown per File</div>', unsafe_allow_html=True)
                        df_melt = df[["File", "Positive", "Neutral", "Negative"]].melt(
                            id_vars="File", var_name="Sentiment", value_name="Score"
                        )
                        st.plotly_chart(_dark(px.bar(
                            df_melt, x="File", y="Score", color="Sentiment",
                            barmode="group",
                            title="Positive / Neutral / Negative per File",
                            template="plotly_dark",
                            color_discrete_map={
                                "Positive": "#22c55e",
                                "Neutral":  "#f59e0b",
                                "Negative": "#ef4444",
                            },
                        )), use_container_width=True)

                        # Word frequency
                        all_freq: dict = {}
                        for r in valid:
                            for w, c in r.get("Word_Freq", {}).items():
                                all_freq[w] = all_freq.get(w, 0) + c
                        if all_freq:
                            top20 = sorted(all_freq.items(), key=lambda x: x[1], reverse=True)[:20]
                            wdf   = pd.DataFrame(top20, columns=["Word", "Count"])
                            st.markdown('<div class="sec">🔤 Top 20 Most Frequent Words</div>', unsafe_allow_html=True)
                            st.plotly_chart(_dark(px.bar(
                                wdf, x="Count", y="Word", orientation="h",
                                title="Top 20 Words (across all files)",
                                template="plotly_dark",
                                color_discrete_sequence=["#7c3aed"],
                            )), use_container_width=True)

                    st.download_button("⬇️ Download Sentiment CSV", _csv(df),
                                       f"sentiment_{datetime.now():%Y%m%d_%H%M%S}.csv",
                                       "text/csv", key="t3_dl")


# ╔══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MERGE TO JSON
# ╚══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="sec">🗃️ Merge All Files → Single JSON</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-info">Converts every CSV, TXT, and PDF into one unified JSON document. Includes optional file metadata (size, MD5, timestamp).</div>', unsafe_allow_html=True)
    st.markdown('<div class="box-pat">♟ Strategy → TxtStrategy / CsvStrategy / PdfStrategy each handle their format.<br>🏭 Factory → FileProcessorFactory.create("json") returns the worker.<br>👁 Observer → notifier.notify() after every completed future.<br>🔒 Singleton → same executor pool reused — no resource waste.</div>', unsafe_allow_html=True)

    c_ind, c_meta = st.columns(2)
    with c_ind:
        indent   = st.selectbox("JSON Indentation (spaces)", [2, 4, 0], index=0, key="t4_indent")
    with c_meta:
        inc_meta = st.checkbox("Include file metadata (size, MD5, timestamp)", value=True, key="t4_meta")

    if st.button("⚡ Merge to JSON", key="t4_run"):
        store = st.session_state.file_store
        if not store:
            _no_files()
        else:
            worker = FileProcessorFactory.create("json")
            tasks  = [(name, raw, inc_meta) for name, raw in store.items()]

            t0 = time.perf_counter()
            run_sequential(worker, tasks)
            single_t = time.perf_counter() - t0

            bar      = st.progress(0, text="Converting…")
            notifier = _make_notifier(bar, "Converted")
            t0       = time.perf_counter()
            entries  = run_parallel(worker, tasks, "Converted", notifier)
            multi_t  = time.perf_counter() - t0
            bar.empty()

            _render_timing(single_t, multi_t)
            st.markdown("---")

            json_str, json_bytes, total_items, size_kb = build_merged_json(entries, indent)

            st.markdown(f"""
            <div class="m-row">
              <div class="m-card"><div class="v">{len(entries)}</div><div class="l">Files Merged</div></div>
              <div class="m-card"><div class="v">{total_items:,}</div><div class="l">Total Data Items</div></div>
              <div class="m-card"><div class="v">{size_kb:.1f} KB</div><div class="l">Output Size</div></div>
            </div>""", unsafe_allow_html=True)

            if PLOTLY:
                tc = collections.Counter(e["type"] for e in entries)
                col_c, _ = st.columns([1, 2])
                with col_c:
                    st.plotly_chart(_dark(px.pie(
                        values=list(tc.values()),
                        names=list(tc.keys()),
                        title="Files by Type",
                        template="plotly_dark",
                        color_discrete_sequence=COLORS,
                    )), use_container_width=True)

            st.markdown('<div class="sec">👁️ JSON Preview (first 5000 chars)</div>', unsafe_allow_html=True)
            preview = json_str[:5000] + ("\n\n… [truncated]" if len(json_str) > 5000 else "")
            st.code(preview, language="json")

            st.download_button(
                "⬇️ Download Merged JSON",
                data=json_bytes,
                file_name=f"merged_{datetime.now():%Y%m%d_%H%M%S}.json",
                mime="application/json",
                key="t4_dl",
            )


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(f"""
<div style='text-align:center;color:#64748b;font-size:.73rem;
    font-family:"JetBrains Mono",monospace;padding:.8rem;'>
⚡ MultiThread File Processor v5 &nbsp;·&nbsp;
Layered Architecture &nbsp;·&nbsp;
Strategy + Factory + Observer + Singleton Patterns &nbsp;·&nbsp;
{MAX_WORKERS} workers
</div>
""", unsafe_allow_html=True)

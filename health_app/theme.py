"""Health 창 색·글꼴. 그래프 색은 검증된 dark 팔레트(#3987e5·#d95926, 배경 #1a1a19) — 글자는 데이터 색을 쓰지 않는다."""

SURFACE = "#1a1a19"        # 그래프 바탕
WINDOW = "#242423"         # 창 바탕
PANEL = "#2b2b29"          # 표·글 상자 바탕
INK_PRIMARY, INK_SECONDARY, INK_MUTED = "#ffffff", "#c3c2b7", "#898781"
GRID, BASELINE = "#2c2c2a", "#383835"
TOOLTIP_BG = "#262624"
ACCENT = "#1f6aa5"         # 버튼(기존 slurm_ui 파랑)
DANGER = "#7a3b3b"
GPU_COLORS = ("#3987e5", "#d95926")   # 범주 1·2번 — GPU 번호마다 고정(정렬이 바뀌어도 색은 따라가지 않는다)
SINGLE_COLOR = GPU_COLORS[0]
WARNING = "#fab219"                    # 상태색(경고) — 기준선에만
CORE_RAMP = ("#22324a", "#3987e5", "#d2e5fc")   # 코어 사용률 0→50→100%: 한 색(파랑) 진하기, 어두운 바탕이라 밝을수록 바쁨
STATUS_COLORS = {"ok": "#00e060", "warn": "#ffcc00", "fail": "#ff5555", None: "#999999"}
DETAIL_COLORS = {**{key: value for key, value in STATUS_COLORS.items() if key}, "title": "#66aaff", "default": "#cccccc"}

UI_FONT = "Malgun Gothic"
MONO_FONT = "Consolas"

STYLE_SHEET = f"""
QWidget {{ background: {WINDOW}; color: {INK_SECONDARY}; font-family: "{UI_FONT}"; font-size: 10pt; }}
QTableWidget, QPlainTextEdit {{ background: {PANEL}; border: none; selection-background-color: #3a3a38;
                               selection-color: {INK_PRIMARY}; gridline-color: {GRID}; }}
QHeaderView::section {{ background: {WINDOW}; color: #66aaff; border: none; border-bottom: 1px solid {BASELINE};
                        padding: 4px 6px; font-weight: bold; }}
QPushButton {{ background: {ACCENT}; color: {INK_PRIMARY}; border: none; border-radius: 5px; padding: 6px 14px; }}
QPushButton:hover {{ background: #2a7cbd; }}
QPushButton:disabled {{ background: #3a3a38; color: {INK_MUTED}; }}
QPushButton#danger {{ background: {DANGER}; }}
QPushButton#quiet {{ background: #3a3a38; }}
QPushButton#range {{ background: #3a3a38; border-radius: 0; padding: 4px 12px; }}
QPushButton#range:checked {{ background: {ACCENT}; }}
QDockWidget {{ color: {INK_SECONDARY}; font-weight: bold; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 8px; }}
QTabBar::tab {{ background: {PANEL}; color: {INK_MUTED}; padding: 6px 14px; border: none; }}
QTabBar::tab:selected {{ background: {ACCENT}; color: {INK_PRIMARY}; }}
QSplitter::handle {{ background: {WINDOW}; }}
QToolTip {{ background: {TOOLTIP_BG}; color: {INK_PRIMARY}; border: 1px solid {BASELINE}; }}
"""

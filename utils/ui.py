"""앱 전체 공통 스타일(폰트·표 가독성)과 공용 UI 조각(로고 헤더, CSV 다운로드)."""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

# Pretendard / Noto Sans KR 우선, 사내망에서 CDN이 막히면 시스템 폰트로 자연스럽게 대체됩니다.
# ※ 아이콘(Material Symbols)까지 덮어쓰면 사이드바 메뉴가 깨지므로 아이콘 폰트는 아래에서 되돌립니다.
_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css');
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

:root {
  --app-font: "Pretendard Variable", Pretendard, "Noto Sans KR", "Malgun Gothic",
              -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
}
html, body, .stApp { font-family: var(--app-font); -webkit-font-smoothing: antialiased; }
.stApp p, .stApp label, .stApp li, .stApp td, .stApp th,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp button, .stApp input, .stApp textarea, .stApp select,
.stMarkdown, [data-testid="stWidgetLabel"], [data-testid="stMetricValue"],
[data-testid="stMetricLabel"] { font-family: var(--app-font); }

/* 아이콘 폰트는 반드시 원래대로 (사이드바 메뉴 아이콘 깨짐 방지) */
[data-testid="stIconMaterial"], .material-icons, .material-icons-outlined,
.material-symbols-rounded, .material-symbols-outlined,
span[translate="no"] {
  font-family: "Material Symbols Rounded", "Material Icons" !important;
  font-feature-settings: "liga" !important;
}

/* 숫자 입력칸의 +/- 버튼 숨김 (직접 타이핑만) */
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"],
[data-testid="stNumberInputStepper"] { display: none !important; }
[data-testid="stNumberInputContainer"] input { border-radius: 8px; }

/* 표 머리글: 은은한 배경 + 진한 글씨로 컬럼이 바로 보이게 */
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataEditor"] [role="columnheader"] {
  font-weight: 700 !important;
  color: #1B3A5C !important;
  background-color: #D7E6F5 !important;
}

/* 로고 + 제목 한 줄 헤더 — 화면 폭에 따라 글자 크기가 줄어들어 줄바꿈되지 않음 */
.apphead { display: flex; align-items: center; gap: .55em; min-width: 0; margin: .2rem 0 .9rem; }
.apphead img { height: clamp(26px, 4.2vw, 46px); width: auto; flex: 0 0 auto; }
.apphead .t {
  font-size: clamp(1.05rem, 3.1vw, 2.1rem);
  font-weight: 800; letter-spacing: -.02em; line-height: 1.15;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 상세 화면의 항목 라벨 (순번/입력날짜/담당부서 …) */
.fieldlabel { font-size: .78rem; font-weight: 700; color: #4A6480;
              letter-spacing: .02em; margin-bottom: 6px; }
.fieldvalue { font-size: .95rem; line-height: 1.5; margin-bottom: 24px; }
</style>
"""


def inject():
    st.markdown(_CSS, unsafe_allow_html=True)


@lru_cache(maxsize=1)
def _logo_b64() -> str:
    """로고를 HTML 안에 직접 넣기 위해 base64로 (파일이 없으면 빈 문자열)."""
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode()
    except Exception:          # noqa: BLE001  로고 파일이 없어도 앱은 동작해야 함
        return ""


def page_header(title: str):
    """로고 + 제목을 한 줄로. 창이 좁아지면 글자가 작아질 뿐 줄바꿈되지 않습니다."""
    b64 = _logo_b64()
    img = f"<img src='data:image/png;base64,{b64}' alt=''>" if b64 else ""
    st.markdown(f"<div class='apphead'>{img}<div class='t'>{title}</div></div>",
                unsafe_allow_html=True)


def sidebar_logo():
    """사이드바 상단에 로고 표시 (st.logo 를 지원하는 버전에서만)."""
    if LOGO_PATH.exists():
        try:
            st.logo(str(LOGO_PATH), size="large")
        except Exception:      # noqa: BLE001  구버전 호환
            pass


def download_csv(df, filename: str, label: str = "⬇️ CSV 다운로드", key=None,
                 help: str = "", width: str = "content"):
    """현재 보고 있는 데이터를 CSV로 내려받기.
    엑셀에서 한글이 깨지지 않도록 UTF-8 BOM(utf-8-sig)으로 저장합니다."""
    import pandas as pd  # noqa: PLC0415  (ui 모듈 임포트 비용을 줄이려고 지역 임포트)

    if df is None or len(df) == 0:
        st.caption("내려받을 데이터가 없습니다.")
        return
    out = df.copy()
    if isinstance(out, pd.Series):
        out = out.to_frame()
    data = out.to_csv(index=False).encode("utf-8-sig")
    st.download_button(f"{label} ({len(out):,}건)", data=data, file_name=filename,
                       mime="text/csv", key=key, help=help or "엑셀에서 바로 열 수 있습니다.",
                       width=width)

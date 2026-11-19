"""엑셀·CSV 파일로 받은 DB를 앱 형식으로 정리합니다. (스트림릿 의존 없음 → 테스트 가능)

쓰는 곳: DB입력 → 'DB 일괄 등록' → '파일로 등록' 탭
순번은 여기서 매기지 않습니다. 파일에 적힌 순서대로 data.bulk_add_db 가 이어서 부여합니다.
"""
import io
import re
from datetime import date, datetime

import pandas as pd

from utils import config as C
from utils.clean import (REASON_KEYWORDS, channel_of, normalize_addr,
                         normalize_phone, phone_digits, region_of)

# 파일에서 읽어오는 항목. 순번·등록경로·원본ID·유입경로_기타는 앱이 알아서 채웁니다.
IMPORT_COLS = ["입력날짜", "병원명", "병원소재지", "분과", "연락처", "담당자",
               "상담가능날짜", "문의이유", "세부문의사항", "유입경로",
               "담당부서", "진행상황", "비고"]
REQUIRED = ["병원명"]          # 이것만 비면 그 줄은 건너뜁니다

# 파일 열 이름 → 앱 항목. 공백·밑줄·대소문자는 무시하고 비교합니다.
HEADER_ALIAS = {
    "입력날짜": "입력날짜", "등록일": "입력날짜", "등록날짜": "입력날짜", "접수일": "입력날짜",
    "접수일자": "입력날짜", "접수일시": "입력날짜", "신청일": "입력날짜", "날짜": "입력날짜",
    "유입일": "입력날짜", "db유입일": "입력날짜", "문의일": "입력날짜", "문의날짜": "입력날짜",

    "병원명": "병원명", "병원": "병원명", "업체명": "병원명", "상호": "병원명", "상호명": "병원명",
    "기관명": "병원명", "고객명": "병원명", "거래처": "병원명",

    "병원소재지": "병원소재지", "소재지": "병원소재지", "지역": "병원소재지", "주소": "병원소재지",
    "병원주소": "병원소재지", "위치": "병원소재지",

    "분과": "분과", "진료과": "분과", "진료과목": "분과", "과목": "분과", "진료분야": "분과",

    "연락처": "연락처", "전화번호": "연락처", "전화": "연락처", "휴대폰": "연락처",
    "휴대폰번호": "연락처", "핸드폰": "연락처", "핸드폰번호": "연락처", "번호": "연락처", "tel": "연락처",

    "담당자": "담당자", "병원담당자": "담당자", "담당자명": "담당자", "성명": "담당자",
    "이름": "담당자", "원장": "담당자", "원장님": "담당자",

    "상담가능날짜": "상담가능날짜", "상담가능일": "상담가능날짜", "상담가능시간": "상담가능날짜",
    "상담희망일": "상담가능날짜", "상담희망날짜": "상담가능날짜", "통화가능시간": "상담가능날짜",

    "문의이유": "문의이유", "문의사유": "문의이유", "문의유형": "문의이유", "문의구분": "문의이유",

    "세부문의사항": "세부문의사항", "세부문의": "세부문의사항", "문의내용": "세부문의사항",
    "상담내용": "세부문의사항", "내용": "세부문의사항", "요청사항": "세부문의사항", "상세내용": "세부문의사항",

    "유입경로": "유입경로", "경로": "유입경로", "매체": "유입경로", "유입": "유입경로",
    "유입매체": "유입경로", "광고매체": "유입경로", "채널": "유입경로", "인지경로": "유입경로",

    "담당부서": "담당부서", "애드리절트담당부서": "담당부서", "부서": "담당부서",
    "배정팀": "담당부서", "담당팀": "담당부서", "팀": "담당부서",

    "진행상황": "진행상황", "상태": "진행상황", "진행상태": "진행상황", "진행": "진행상황",

    "비고": "비고", "기타": "비고", "메모": "비고", "캠페인": "비고", "특이사항": "비고",
}

BLANKS = {"", "-", "nan", "none", "nat", "null", "#n/a", "n/a"}


# ── 값 다듬기 ───────────────────────────────────────────────────
def txt(v) -> str:
    """셀 값 → 문자열. 엑셀의 빈칸·'-'·NaN 은 모두 빈 문자열로."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in BLANKS else s


def to_date(v) -> str:
    """날짜 칸 → 'YYYY-MM-DD'. 날짜값·엑셀 일련번호·'2026.11.3'·'11/3' 모두 받습니다."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return f"{v:%Y-%m-%d}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = float(v)
        if 20000 <= n <= 80000:                       # 엑셀 일련번호 (1954년 ~ 2119년)
            return f"{pd.Timestamp('1899-12-30') + pd.Timedelta(days=int(n)):%Y-%m-%d}"
        return ""
    s = txt(v)
    if not s:
        return ""
    if m := re.search(r"(\d{4})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", s):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    if m := re.fullmatch(r"\s*(\d{1,2})[-./](\d{1,2})\s*", s):  # 연도 없이 '11/3' → 올해
        mo, d = int(m[1]), int(m[2])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{date.today().year:04d}-{mo:02d}-{d:02d}"
    try:
        return f"{pd.to_datetime(s, errors='raise'):%Y-%m-%d}"
    except Exception:
        return ""


def dept_of(text: str):
    """분과 → (값, 경고). 목록에 없으면 원문을 그대로 두고 경고만 남깁니다."""
    t = txt(text)
    if not t:
        return "", ""
    flat = t.replace(" ", "")
    for d in C.DEPARTMENTS:
        if d.replace(" ", "") == flat:
            return d, ""
    for d in C.DEPARTMENTS:                           # '재활의학과' → '정형외과/신경외과/재활/통증'
        if d == C.DEPT_ETC:
            continue
        if any(len(p) >= 2 and p in flat for p in d.replace("/", " ").split()):
            return d, ""
    return t, f"분과 '{t}' — 목록에 없어 적힌 대로 저장합니다"


def team_of(text: str):
    """담당부서 → (값, 경고). 팀 목록에 없으면 미할당으로 둡니다."""
    t = txt(text)
    if not t or t == C.UNASSIGNED:
        return "", ""
    flat = t.replace(" ", "")
    for team in C.TEAMS:
        if team.replace(" ", "") == flat:
            return team, ""
    return "", f"담당부서 '{t}' — 팀 목록에 없어 미할당으로 둡니다"


def status_of(text: str):
    """진행상황 → (값, 경고). 목록에 없으면 '접촉 전'."""
    t = txt(text)
    if not t:
        return C.PRE_CONTACT, ""
    flat = t.replace(" ", "")
    for s in C.STATUSES:
        if s.replace(" ", "") == flat:
            return s, ""
    return C.PRE_CONTACT, f"진행상황 '{t}' — 목록에 없어 '{C.PRE_CONTACT}'으로 둡니다"


def reasons_of(text: str) -> str:
    """문의이유 → 앱의 짧은 라벨. 긴 문장 안에 쉼표가 있어 통째로 훑어 찾습니다."""
    t = txt(text)
    if not t:
        return ""
    out = [lab for kw, lab in REASON_KEYWORDS if kw in t]
    out += [r for r in C.INQUIRY_REASONS if r != "기타" and r in t]
    if not out:
        return t[:60] if len(t) > 2 else "기타"       # 알 수 없으면 원문 보존
    if "기타" in t:
        out.append("기타")
    return ", ".join(dict.fromkeys(out))


# ── 파일 읽기 ───────────────────────────────────────────────────
def sheet_names(data: bytes, filename: str):
    """엑셀이면 시트 이름 목록, CSV 면 None."""
    if filename.lower().endswith((".csv", ".txt", ".tsv")):
        return None
    return pd.ExcelFile(io.BytesIO(data)).sheet_names


def read_table(data: bytes, filename: str, sheet=None, header_row: int = 1) -> pd.DataFrame:
    """파일 → 표. header_row 는 '헤더가 몇 번째 줄인지'(1부터)."""
    skip = max(int(header_row), 1) - 1
    if filename.lower().endswith((".csv", ".txt", ".tsv")):
        sep = "\t" if filename.lower().endswith(".tsv") else None
        last = None
        for enc in ("utf-8-sig", "cp949", "utf-8"):
            try:
                return pd.read_csv(io.BytesIO(data), header=skip, dtype=object,
                                   sep=sep, engine="python", encoding=enc)
            except Exception as e:      # noqa: PERF203  — 인코딩을 차례로 시도
                last = e
        raise RuntimeError(f"CSV 를 읽지 못했습니다: {last}")
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0,
                         header=skip, dtype=object)


def norm_header(s) -> str:
    return re.sub(r"[\s_()\[\]*]+", "", str(s)).lower()


def guess_mapping(file_cols) -> dict:
    """파일 열 이름 → 앱 항목 자동 연결. {앱 항목: 파일 열 이름}"""
    out = {}
    for col in file_cols:
        key = norm_header(col)
        if not key or key.startswith("unnamed:"):
            continue
        app = HEADER_ALIAS.get(key)
        if app is None:                              # '병원 연락처' 처럼 말이 붙은 경우
            app = next((v for k, v in HEADER_ALIAS.items() if len(k) >= 3 and k in key), None)
        if app and app not in out:
            out[app] = col
    return out


# ── 본 작업 ─────────────────────────────────────────────────────
def clean_rows(df: pd.DataFrame, mapping: dict):
    """파일 표 + 열 연결 → (등록할 행 목록, 확인표).

    등록할 행에는 순번을 넣지 않습니다. 파일 순서대로 앱이 번호를 매깁니다.
    확인표(issues)는 '몇 번째 줄의 무엇이 어떻게 바뀌었는지' 보여주기 위한 것입니다.
    """
    rows, issues, today = [], [], str(date.today())

    def note(line, hospital, msg):
        issues.append({"줄": line, "병원명": hospital, "확인할 내용": msg})

    for i, r in enumerate(df.to_dict("records")):
        line = i + 1
        get = lambda app: r.get(mapping[app]) if mapping.get(app) in r else None  # noqa: E731

        hospital = txt(get("병원명"))
        if not hospital:
            if any(txt(v) for v in r.values()):      # 완전히 빈 줄은 조용히 넘김
                note(line, "", "병원명이 비어 있어 건너뜁니다")
            continue

        in_date = to_date(get("입력날짜"))
        if not in_date:                              # 비거나 못 읽은 날짜는 오늘로 (통계에서 빠지지 않게)
            raw_date = txt(get("입력날짜"))
            note(line, hospital,
                 (f"입력날짜 '{raw_date}' — 날짜로 읽지 못해 오늘({today})로 넣습니다" if raw_date
                  else f"입력날짜가 비어 있어 오늘({today})로 넣습니다"))
            in_date = today

        raw_addr = txt(get("병원소재지"))
        addr = normalize_addr(raw_addr)
        if raw_addr and region_of(addr) not in C.REGION_FULL:
            note(line, hospital, f"소재지 '{raw_addr}' — 시·도를 알 수 없어 적힌 대로 저장합니다")
        elif raw_addr and addr != raw_addr:
            note(line, hospital, f"소재지 '{raw_addr}' → '{addr}'")

        raw_phone = txt(get("연락처"))
        phone = normalize_phone(raw_phone)
        digits = phone_digits(raw_phone)
        if raw_phone and not (9 <= len(digits) <= 11):
            note(line, hospital, f"연락처 '{raw_phone}' — 전화번호 형식이 아닙니다")

        dept, w = dept_of(get("분과"))
        if w:
            note(line, hospital, w)
        team, w = team_of(get("담당부서"))
        if w:
            note(line, hospital, w)
        status, w = status_of(get("진행상황"))
        if w:
            note(line, hospital, w)

        channel, channel_etc = channel_of(txt(get("유입경로")), "")
        if channel == C.CHANNEL_ETC and channel_etc:
            note(line, hospital, f"유입경로 '{channel_etc}' — 목록에 없어 '기타'로 두고 원문을 남겼습니다")

        rows.append({
            "입력날짜": in_date, "담당부서": team, "진행상황": status,
            "병원명": hospital, "병원소재지": addr, "분과": dept,
            "연락처": phone, "담당자": txt(get("담당자")),
            "상담가능날짜": to_date(get("상담가능날짜")),
            "문의이유": reasons_of(get("문의이유")),
            "세부문의사항": txt(get("세부문의사항")),
            "유입경로": channel, "유입경로_기타": channel_etc,
            "비고": txt(get("비고")),
        })

    cols = ["줄", "병원명", "확인할 내용"]
    return rows, pd.DataFrame(issues, columns=cols)


def template() -> pd.DataFrame:
    """'양식 받기'로 내려주는 빈 표 — 열 이름과 예시 한 줄."""
    sample = {
        "입력날짜": "2026-11-19", "병원명": "예시정형외과", "병원소재지": "서울시 강남구",
        "분과": C.DEPARTMENTS[1], "연락처": "010-1234-5678", "담당자": "홍길동 원장",
        "상담가능날짜": "2026-11-20", "문의이유": C.INQUIRY_REASONS[2],
        "세부문의사항": "신환이 줄어 온라인 마케팅을 알아보고 있습니다.",
        "유입경로": C.CHANNELS[0], "담당부서": "", "진행상황": "",
        "비고": "11월 전시회",
    }
    return pd.DataFrame([sample], columns=IMPORT_COLS)

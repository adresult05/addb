"""구글시트 연결 점검 스크립트 (읽기 전용 — 시트에 아무것도 쓰지 않습니다).

사용법:
    python check_connection.py

앱을 켜기 전에 이걸 먼저 돌려서 설정이 맞는지 확인하세요.
어디가 잘못됐는지와 고치는 방법을 한글로 알려줍니다.
"""
import re
import sys
from pathlib import Path

OK, WARN, FAIL = "✅", "⚠️ ", "❌"
problems = []


def say(mark, msg, hint=""):
    print(f"{mark} {msg}")
    if hint:
        for line in hint.strip().split("\n"):
            print(f"      {line}")
    if mark == FAIL:
        problems.append(msg)


def die():
    print("\n" + "─" * 58)
    print(f"{FAIL} 점검 중단: 위 문제를 먼저 해결해주세요.")
    sys.exit(1)


print("=" * 58)
print(" 애드리절트 DB 대시보드 — 구글시트 연결 점검")
print("=" * 58)

# ── 1. secrets.toml ───────────────────────────────────────────
print("\n[1/7] secrets.toml 확인")
sec_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
if not sec_path.exists():
    say(FAIL, "'.streamlit/secrets.toml' 파일이 없습니다.",
        "'.streamlit/secrets.toml.example' 을 복사해서 'secrets.toml' 로 이름을 바꾸고\n"
        "내용을 채워주세요.")
    die()

try:
    import tomllib
    with open(sec_path, "rb") as f:
        sec = tomllib.load(f)
except Exception as e:
    say(FAIL, f"secrets.toml 을 읽지 못했습니다: {e}",
        "따옴표나 줄바꿈이 깨졌을 수 있습니다. 특히 private_key 는 한 줄로,\n"
        '줄바꿈은 \\n 으로 들어가야 합니다.')
    die()
say(OK, "secrets.toml 읽기 성공")

gs, sa = sec.get("gsheets"), sec.get("gcp_service_account")
if not gs:
    say(FAIL, "[gsheets] 블록이 없습니다.", "secrets.toml.example 을 참고해 추가해주세요.")
if not sa:
    say(FAIL, "[gcp_service_account] 블록이 없습니다.", "서비스 계정 JSON 키 내용을 넣어주세요.")
if problems:
    die()

missing = [k for k in ("spreadsheet_id",) if not gs.get(k)]
if missing:
    say(FAIL, f"[gsheets] 에 {', '.join(missing)} 가 비어 있습니다.")
    die()

email = sa.get("client_email", "")
say(OK, f"서비스 계정: {email}")

if not gs.get("import_from"):
    say(FAIL, "[gsheets] 에 import_from 이 없습니다.",
        'import_from = "2026-10-12" 처럼 넣어주세요.\n'
        "이 날짜 이후 접수된 raw 응답만 가져옵니다. (과거 전체가 쏟아지는 걸 막는 안전장치)")
    die()
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(gs["import_from"])):
    say(FAIL, f"import_from 형식이 잘못됐습니다: {gs['import_from']}", '"YYYY-MM-DD" 형식이어야 합니다.')
    die()
say(OK, f"import_from = {gs['import_from']} (이 날짜 이후 응답만 가져옵니다)")

last_no = str(gs.get("last_no", "") or "")
if last_no:
    if not re.fullmatch(r"\d{2}-\d{3}", last_no):
        say(FAIL, f"last_no 형식이 잘못됐습니다: {last_no}", '"26-187" 처럼 두자리-세자리 여야 합니다.')
        die()
    say(OK, f"last_no = {last_no} (다음 번호부터 이어서 부여)")
else:
    say(WARN, "last_no 가 없습니다 — 순번이 26-001 부터 시작합니다.",
        "기존 시트에 이미 26-xxx 순번을 쓰고 있다면 번호가 겹칩니다.\n"
        '마지막 순번을 last_no = "26-187" 처럼 넣어주세요.')

# ── 2. 라이브러리 ─────────────────────────────────────────────
print("\n[2/7] 필요한 라이브러리 확인")
try:
    import gspread  # noqa: F401
    say(OK, "gspread 설치됨")
except ImportError:
    say(FAIL, "gspread 가 설치되지 않았습니다.", "python -m pip install -r requirements.txt")
    die()

# ── 3. 인증 ───────────────────────────────────────────────────
print("\n[3/7] 구글 인증")
try:
    gc = gspread.service_account_from_dict(dict(sa))
    say(OK, "서비스 계정 인증 성공")
except Exception as e:
    say(FAIL, f"인증 실패: {type(e).__name__}: {e}",
        "private_key 가 깨졌을 가능성이 큽니다. JSON 키의 private_key 값을\n"
        "따옴표 안에 그대로(줄바꿈은 \\n 으로) 넣었는지 확인해주세요.")
    die()


def open_sheet(sid, what):
    try:
        ss = gc.open_by_key(sid)
        say(OK, f"{what} 열기 성공: '{ss.title}'")
        return ss
    except Exception as e:
        name = type(e).__name__
        if "SpreadsheetNotFound" in name or "404" in str(e):
            say(FAIL, f"{what} 를 찾을 수 없습니다 (ID: {sid[:20]}...)",
                f"· 시트 ID가 맞는지 확인하세요 (주소의 /d/ 와 /edit 사이)\n"
                f"· 시트를 {email} 에 공유했는지 확인하세요")
        elif "403" in str(e) or "PermissionError" in name:
            say(FAIL, f"{what} 접근 권한이 없습니다.",
                f"시트를 {email} 에 공유해주세요.\n"
                f"(앱 데이터 시트는 '편집자', raw 시트는 '뷰어' 이상)")
        elif "API has not been used" in str(e) or "disabled" in str(e):
            say(FAIL, f"{what}: 구글 API가 꺼져 있습니다.",
                "Google Cloud 콘솔에서 'Google Sheets API' 와 'Google Drive API' 를 켜주세요.")
        else:
            say(FAIL, f"{what} 열기 실패: {name}: {e}")
        return None


# ── 4. 앱 데이터 시트 ─────────────────────────────────────────
print("\n[4/7] 앱 데이터 스프레드시트 (DB마스터·진행로그가 저장될 곳)")
app_ss = open_sheet(gs["spreadsheet_id"], "앱 데이터 시트")
if app_ss is None:
    die()

tabs = [ws.title for ws in app_ss.worksheets()]
print(f"      현재 탭: {', '.join(tabs)}")

master_name = gs.get("master_worksheet", "DB마스터")
log_name = gs.get("log_worksheet", "진행로그")
sys.path.insert(0, str(Path(__file__).parent))
from utils import config as C  # noqa: E402

for name, cols in ((master_name, C.DB_COLUMNS), (log_name, C.LOG_COLUMNS)):
    if name not in tabs:
        say(OK, f"'{name}' 탭 없음 — 앱이 처음 실행될 때 자동으로 만듭니다.")
        continue
    head = app_ss.worksheet(name).row_values(1)
    if not head:
        say(OK, f"'{name}' 탭이 비어 있음 — 앱이 헤더를 넣습니다.")
    elif head[:len(cols)] == cols:
        n = len(app_ss.worksheet(name).get_all_values()) - 1
        say(OK, f"'{name}' 탭 사용 가능 (기존 {n}행)")
    else:
        say(FAIL, f"'{name}' 탭의 헤더가 앱 형식과 다릅니다.",
            f"현재: {', '.join(head[:6])} ...\n"
            f"필요: {', '.join(cols[:6])} ...\n"
            f"→ 다른 용도로 쓰는 탭 같습니다. secrets 의 "
            f"{'master_worksheet' if name == master_name else 'log_worksheet'} 에\n"
            f"  다른 이름을 지정하거나, 이 탭 이름을 바꿔주세요.")

# 쓰기(편집자) 권한 확인 — 임시 탭을 만들었다가 바로 지웁니다.
TMP = "_연결테스트_임시"
tmp_ws = None
try:
    if TMP in tabs:                       # 이전 점검이 중간에 끊겼던 경우
        app_ss.del_worksheet(app_ss.worksheet(TMP))
    tmp_ws = app_ss.add_worksheet(title=TMP, rows=1, cols=1)
    say(OK, "쓰기 권한 있음 (편집자)")
except Exception as e:
    if "403" in str(e) or "permission" in str(e).lower():
        say(FAIL, "쓰기 권한이 없습니다 — 읽기 전용으로 공유돼 있습니다.",
            f"이 시트를 {email} 에 '편집자' 로 다시 공유해주세요.")
    else:
        say(FAIL, f"쓰기 권한 확인 실패: {type(e).__name__}: {e}")
finally:
    if tmp_ws is not None:
        try:
            app_ss.del_worksheet(tmp_ws)
        except Exception:
            say(WARN, f"임시 탭 '{TMP}' 을(를) 지우지 못했습니다. 시트에서 직접 삭제해주세요.")
if problems:
    die()

# ── 5. raw 시트 ───────────────────────────────────────────────
print("\n[5/7] Tally raw 스프레드시트")
raw_id = gs.get("raw_spreadsheet_id") or gs["spreadsheet_id"]
raw_ss = app_ss if raw_id == gs["spreadsheet_id"] else open_sheet(raw_id, "raw 시트")
if raw_ss is None:
    die()
if raw_ss is app_ss:
    say(OK, "raw 가 앱 데이터 시트와 같은 파일에 있습니다.")

raw_name = gs.get("raw_worksheet", "raw")
raw_tabs = [ws.title for ws in raw_ss.worksheets()]
if raw_name not in raw_tabs:
    say(FAIL, f"'{raw_name}' 탭이 없습니다.",
        f"그 파일의 탭 목록: {', '.join(raw_tabs)}\n"
        f"→ secrets 의 raw_worksheet 를 실제 탭 이름으로 고쳐주세요.")
    die()
raw_ws = raw_ss.worksheet(raw_name)
raw_vals = raw_ws.get_all_values()
say(OK, f"'{raw_name}' 탭 읽기 성공 (헤더 포함 {len(raw_vals)}행)")
if len(raw_vals) < 2:
    say(WARN, "raw 에 응답이 아직 없습니다.")

# ── 6. raw 헤더 해석 ──────────────────────────────────────────
print("\n[6/7] raw 헤더 해석 (Tally 질문 → 앱 컬럼 매칭)")
from utils.clean import clean_raw_row, parse_headers  # noqa: E402

try:
    cols_map = parse_headers(raw_vals[0])
    say(OK, "필수 헤더(병원명·연락처) 찾음")
except Exception as e:
    say(FAIL, f"헤더 해석 실패: {e}",
        f"raw 1행: {', '.join(raw_vals[0][:8])} ...\n"
        "→ Tally 질문 문구가 바뀌었을 수 있습니다. 헤더를 알려주시면 맞춰드릴게요.")
    die()

labels = {"date": "입력날짜", "hospital": "병원명", "person": "성함", "phone": "연락처",
          "dept_sel": "분과 선택", "dept_txt": "분과 직접입력", "addr": "병원 소재지",
          "avail": "상담 가능 날짜", "detail": "문의 내용", "channel": "알게 된 경로",
          "channel_txt": "경로 직접입력"}
for k, label in labels.items():
    mark = OK if cols_map.get(k) is not None else WARN
    pos = f"{cols_map[k] + 1}번째 열" if cols_map.get(k) is not None else "못 찾음 (빈 값으로 저장)"
    print(f"      {mark} {label}: {pos}")
print(f"      {OK} 문의이유 체크박스: {len(cols_map['reasons'])}개")

# ── 7. 가져올 건수 미리보기 ───────────────────────────────────
print("\n[7/7] 지금 앱을 켜면 가져올 DB 미리보기")
imp_from = str(gs["import_from"])
rows, skipped_old, skipped_bad = [], 0, 0
for r in raw_vals[1:]:
    rec = clean_raw_row(cols_map, r)
    if not rec or not rec["입력날짜"]:
        skipped_bad += 1
        continue
    if rec["입력날짜"] < imp_from:
        skipped_old += 1
        continue
    rows.append(rec)

print(f"      raw 전체 응답: {len(raw_vals) - 1}건")
print(f"      · {imp_from} 이전이라 제외: {skipped_old}건")
print(f"      · 병원명·연락처·날짜가 비어 제외: {skipped_bad}건")
say(OK if rows else WARN, f"가져올 DB: {len(rows)}건")

if rows:
    print("\n      ── 변환 결과 샘플 (첫 건) ─────────────────")
    for k in ("입력날짜", "병원명", "병원소재지", "분과", "연락처", "담당자",
              "상담가능날짜", "문의이유", "유입경로", "유입경로_기타"):
        v = str(rows[0].get(k, ""))
        print(f"      {k:9}: {v[:50]}{'…' if len(v) > 50 else ''}")
    detail = str(rows[0].get("세부문의사항", "")).replace("\n", " ")
    print(f"      {'세부문의사항':9}: {detail[:50]}{'…' if len(detail) > 50 else ''}")
    print("      ─────────────────────────────────────────")
    print("      ↑ 값이 엉뚱한 칸에 들어갔다면 알려주세요. 매칭을 고쳐드립니다.")

    yy = rows[0]["입력날짜"][2:4]
    start = int(last_no.split("-")[1]) + 1 if last_no and last_no[:2] == yy else 1
    print(f"\n      순번은 {yy}-{start:03d} 부터 부여됩니다.")

# ── 마무리 ────────────────────────────────────────────────────
print("\n" + "=" * 58)
if problems:
    print(f"{FAIL} 문제 {len(problems)}건 — 위 내용을 확인해주세요.")
    sys.exit(1)
print(f"{OK} 점검 통과! 이제 앱을 켜도 됩니다.")
print("     python -m streamlit run app.py")
print("\n     순서: admin 로그인 → 메인에서 '새 DB 불러오기' →")
print("           시트에 DB마스터/진행로그 탭이 생겼는지 확인")
print("=" * 58)

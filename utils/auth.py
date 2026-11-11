import hashlib
import hmac
import time
from datetime import datetime, timedelta

import streamlit as st

from utils import config as C
from utils import ui as UI

# ── 로그인 유지 ────────────────────────────────────────────────
# 로그인하면 브라우저에 쿠키를 남겨, 새로고침·새 탭·앱 재시작 뒤에도 그대로 들어갑니다.
# 며칠 뒤에 다시 묻게 할지 (0 으로 두면 이 기능이 꺼지고 매번 로그인합니다)
REMEMBER_DAYS = 14
COOKIE_NAME = "addb_login"


# 팀 계정도 admin 과 똑같이 전체 DB 조회 + 팀 배정 + Tally 불러오기를 할 수 있게 합니다.
# 팀별로 자기 DB만 보게 되돌리려면 이 값을 False 로 바꾸세요
# (그러면 secrets 의 role = "team" / team = "..." 설정이 그대로 적용됩니다).
EVERYONE_IS_ADMIN = True


def _users() -> dict:
    try:
        u = st.secrets.get("users")
        if u:
            return {k: dict(v) for k, v in u.items()}
    except Exception:
        pass
    return {"admin": {"password": "admin1234", "role": "admin"}}  # 데모 계정


def _pw_ok(expected: str, given: str) -> bool:
    """비밀번호 비교 (타이밍 공격 방지용 고정시간 비교).
    한/영 상태를 안 바꾸고 한글로 입력하면 compare_digest 가 TypeError 를 내므로
    바이트로 바꿔서 비교합니다 (앱이 죽지 않고 '틀렸습니다'로 안내되게)."""
    return hmac.compare_digest(str(expected).encode("utf-8"), str(given).encode("utf-8"))


def _secret_key() -> bytes:
    """쿠키 서명용 키. secrets 에 auth_secret 이 있으면 그걸 쓰고,
    없으면 계정 정보에서 만들어 냅니다 (비밀번호를 바꾸면 기존 쿠키는 무효가 됩니다)."""
    try:
        k = st.secrets.get("auth_secret")
    except Exception:
        k = None
    if not k:
        k = repr(sorted((u, d.get("password", "")) for u, d in _users().items()))
    return hashlib.sha256(str(k).encode("utf-8")).digest()


def _sign(uid: str, exp: int) -> str:
    msg = f"{uid}|{exp}".encode("utf-8")
    return hmac.new(_secret_key(), msg, hashlib.sha256).hexdigest()[:32]


def _make_token(uid: str) -> str:
    exp = int(time.time()) + REMEMBER_DAYS * 86400
    return f"{uid}|{exp}|{_sign(uid, exp)}"


def _read_token(token: str) -> str:
    """토큰이 유효하면 아이디를, 아니면 빈 문자열을 돌려줍니다."""
    try:
        uid, exp_s, sig = str(token).split("|")
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return ""
    if exp < time.time():
        return ""
    if not hmac.compare_digest(sig, _sign(uid, exp)):
        return ""
    return uid if uid in _users() else ""


def _cookies():
    """쿠키 읽기/쓰기 도구. 세션마다 새로 만들어야 값이 제대로 옵니다
    (캐시해서 여러 세션이 나눠 쓰면 다른 사람 쿠키를 읽는 사고가 납니다)."""
    import extra_streamlit_components as stx
    return stx.CookieManager(key="addb_cookies")


def _set_session(uid: str, info: dict):
    st.session_state["user"] = {
        "id": uid,
        "name": str(info.get("name", "") or uid),
        "role": "admin" if EVERYONE_IS_ADMIN else info.get("role", "team"),
        "team": info.get("team", ""),
    }


def _flush_cookie():
    """로그인 직후 한 번, 쿠키를 실제로 기록합니다.
    쿠키 쓰기도 화면이 한 번 그려져야 반영되므로 rerun 직전이 아니라 여기서 합니다."""
    tok = st.session_state.pop("_ck_pending", None)
    if not tok:
        return
    try:
        _cookies().set(COOKIE_NAME, tok, key="addb_write",
                       expires_at=datetime.now() + timedelta(days=REMEMBER_DAYS))
    except Exception:
        pass          # 쿠키가 막혀 있어도 이번 로그인 자체는 유지


def is_logged_in() -> bool:
    if "user" in st.session_state:
        _flush_cookie()
        return True
    if REMEMBER_DAYS <= 0 or st.session_state.get("_ck_done"):
        return False

    try:
        jar = _cookies().get_all(key="addb_read") or {}
    except Exception:
        st.session_state["_ck_done"] = True
        return False

    # 쿠키는 화면이 두세 번 그려진 뒤에야 도착합니다. 올 때까지 잠깐 기다렸다 판단
    if COOKIE_NAME not in jar and st.session_state.get("_ck_try", 0) < 3:
        st.session_state["_ck_try"] = st.session_state.get("_ck_try", 0) + 1
        time.sleep(0.35)        # 쿠키가 도착할 틈을 주고 다시 확인 (최대 3번, 약 1초)
        st.rerun()

    st.session_state["_ck_done"] = True
    uid = _read_token(jar.get(COOKIE_NAME, ""))
    if uid:
        _set_session(uid, _users()[uid])
        return True
    return False


def current_user() -> dict:
    return st.session_state["user"]


def display_name(u: dict = None) -> str:
    """화면에 보여줄 이름. secrets에 name 을 적어두면 그 이름, 없으면 아이디."""
    u = u or current_user()
    return str(u.get("name") or u.get("id", ""))


def visible_teams() -> list:
    u = current_user()
    return C.TEAMS if u["role"] == "admin" else [u["team"]]


def scope(df):
    """로그인 사용자가 볼 수 있는 DB만 남김 (admin=전체, team=본인 팀)."""
    u = current_user()
    if u["role"] == "admin":
        return df
    return df[df["담당부서"] == u["team"]]


_LOGIN_CSS = """
<style>
/* 로그인 화면 전용 — 로고와 제목을 가운데로 */
.loginhead { text-align: center; margin: 5vh 0 1.1rem; }
.loginhead img { height: 76px; width: auto; margin-bottom: 14px; }
.loginhead .lt { font-size: clamp(1.15rem, 2.6vw, 1.6rem); font-weight: 800;
                 letter-spacing: -.02em; line-height: 1.2; }
.loginhead .ls { font-size: .86rem; color: #6B7C93; margin-top: 7px; }
.loginfoot { text-align: center; font-size: .8rem; color: #8A97A8; margin-top: .9rem; }
/* 입력칸을 조금 크게 (오타 줄이기) */
[data-testid="stForm"] input { height: 2.6rem; font-size: .98rem; }
[data-testid="stForm"] [data-testid="stWidgetLabel"] p { font-weight: 600; font-size: .85rem; }
/* 로그인 화면에서는 사이드바 자리를 비움 */
[data-testid="stSidebar"] { display: none; }
</style>
"""


def login_view():
    if st.session_state.pop("_ck_del", False):
        try:                       # 저장해둔 로그인 표시 지우기
            _cookies().delete(COOKIE_NAME, key="addb_del")
        except Exception:
            pass
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        b64 = UI._logo_b64()   # noqa: SLF001  (같은 프로젝트 내부 모듈)
        img = f"<img src='data:image/png;base64,{b64}' alt=''>" if b64 else ""
        st.markdown(f"<div class='loginhead'>{img}"
                    f"<div class='lt'>{C.APP_TITLE}</div>"
                    f"<div class='ls'>아래에서 로그인해주세요.</div></div>",
                    unsafe_allow_html=True)

        with st.container(border=True):
            with st.form("login"):
                uid = st.text_input("아이디", placeholder="아이디 입력",
                                    autocomplete="username")
                pw = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력",
                                   autocomplete="current-password")
                keep = st.checkbox("로그인 상태 유지", value=True, key="keep_login",
                                   disabled=REMEMBER_DAYS <= 0)
                submitted = st.form_submit_button("로그인", type="primary", width="stretch")

            if submitted:
                info = _users().get(uid.strip())
                if info and _pw_ok(info.get("password", ""), pw):
                    _set_session(uid.strip(), info)
                    if REMEMBER_DAYS > 0 and keep:
                        st.session_state["_ck_pending"] = _make_token(uid.strip())
                    st.session_state["_ck_done"] = True
                    st.rerun()
                elif not uid.strip() or not pw:
                    st.warning("아이디와 비밀번호를 모두 입력해주세요.")
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다. "
                             "대소문자와 한/영 상태를 확인해주세요.")

        st.markdown("<div class='loginfoot' style='text-align:center'>"
                    "계정이 필요하거나 비밀번호를 잊으셨으면 관리자에게 문의해주세요.</div>",
                    unsafe_allow_html=True)


def sidebar_user():
    u = current_user()
    name = display_name(u)
    with st.sidebar:
        st.markdown(f"**👤 {name}**")
        # 이름이 팀 이름 그대로면 "(본사1팀)" 을 또 붙이지 않음
        team = u.get("team", "")
        team = "" if team == name else team
        st.caption(f"환영합니다, {name}님" + (f" ({team})" if team else ""))
        if st.button("로그아웃", icon=":material/logout:", width="stretch"):
            st.session_state.clear()
            st.session_state["_ck_done"] = True   # 지우자마자 다시 복구되지 않게
            st.session_state["_ck_del"] = True    # 쿠키 삭제는 다음 화면에서 (쓰기도 렌더가 필요)
            st.rerun()

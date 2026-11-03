import hmac
import streamlit as st
from utils import config as C
from utils import ui as UI


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


def is_logged_in() -> bool:
    return "user" in st.session_state


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
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        b64 = UI._logo_b64()   # noqa: SLF001  (같은 프로젝트 내부 모듈)
        img = f"<img src='data:image/png;base64,{b64}' alt=''>" if b64 else ""
        st.markdown(f"<div class='loginhead'>{img}"
                    f"<div class='lt'>{C.APP_TITLE}</div>"
                    f"<div class='ls'>애드리절트 내부용입니다. 받으신 계정으로 로그인해주세요.</div></div>",
                    unsafe_allow_html=True)

        with st.container(border=True):
            with st.form("login"):
                uid = st.text_input("아이디", placeholder="예: mapo",
                                    autocomplete="username")
                pw = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력",
                                   autocomplete="current-password")
                submitted = st.form_submit_button("로그인", type="primary", width="stretch")

            if submitted:
                info = _users().get(uid.strip())
                if info and _pw_ok(info.get("password", ""), pw):
                    st.session_state["user"] = {
                        "id": uid.strip(),
                        "name": str(info.get("name", "") or uid.strip()),  # 없으면 아이디를 그대로
                        "role": info.get("role", "team"),
                        "team": info.get("team", ""),
                    }
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
        team = "" if (u["role"] == "admin" or u.get("team", "") == name) else u.get("team", "")
        st.caption(f"환영합니다, {name}님" + (f" ({team})" if team else ""))
        if st.button("로그아웃", icon=":material/logout:", width="stretch"):
            st.session_state.clear()
            st.rerun()

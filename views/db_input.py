import zlib
from datetime import date

import pandas as pd
import streamlit as st

from utils import auth as A
from utils import config as C
from utils import data as D
from utils import importer as IM
from utils import ui as UI
from utils.clean import normalize_addr


def render():
    st.title("DB 입력")
    tab_one, tab_bulk = st.tabs(["신규 등록", "DB 일괄 등록"])
    with tab_one:
        _single_form()
    with tab_bulk:
        _bulk_import()


# ══ 신규 등록 (한 줄에 항목 하나씩) ═════════════════════════════
def _single_form():
    st.caption("직접 받은 DB를 1건씩 등록합니다. 담당부서는 지정하지 않으며, 등록된 DB는 '미할당'으로 통합 DB에 들어가 "
               "메인 페이지에서 배정합니다.")

    if msg := st.session_state.pop("input_flash", None):
        st.success(msg)

    user = A.current_user()
    ver = st.session_state.setdefault("input_ver", 0)   # 등록 성공 시 올려서 입력칸 초기화
    k = lambda name: f"in_{name}_{ver}"                 # noqa: E731
    form, _ = st.columns([2, 1])                        # 입력칸이 화면 전체로 늘어나지 않도록

    with form:
        in_date = st.date_input("입력날짜", value=date.today(), key=k("date"))
        hospital = st.text_input("병원명 *", key=k("hospital"))

        dept_sel = st.selectbox("분과", C.DEPARTMENTS, index=None, placeholder="선택", key=k("dept"))
        dept_etc = st.text_input("분과 직접입력 *", key=k("dept_etc")) if dept_sel == C.DEPT_ETC else ""

        person = st.text_input("담당자", key=k("person"))
        phone = st.text_input("연락처 *", placeholder="010-0000-0000", key=k("phone"))

        c1, c2 = st.columns([1, 2])
        region = c1.selectbox("병원소재지 (시·도)", C.REGIONS, index=None, placeholder="선택", key=k("region"))
        metro = region in C.METRO_REGIONS               # 광역시는 시·군·구 없이 이름만 저장
        sigungu = c2.text_input("구 (서울) / 시·군 (그 외)", key=k("sigungu"), disabled=metro,
                                help="서울은 구까지, 경기·강원 등 도 지역은 시·군까지, 광역시는 입력하지 않아도 됩니다.")

        channel = st.selectbox("유입경로", C.CHANNELS, key=k("channel"))
        channel_etc = st.text_input("유입경로 직접입력 *", key=k("channel_etc")) \
            if channel == C.CHANNEL_ETC else ""

        notes = D.existing_notes()
        note_pick = st.selectbox("비고 (캠페인·특이사항)", ["(없음)"] + notes + ["+ 새로 입력"],
                                 key=k("note_pick"),
                                 help="예: 브마팀 메타_AI마케팅 — 어떤 광고·캠페인으로 들어왔는지 기록합니다.")
        note = "" if note_pick == "(없음)" else note_pick
        if note_pick == "+ 새로 입력":
            note = st.text_input("비고 직접입력", key=k("note_new"))

        reason = st.multiselect("문의이유 (복수 선택 가능)", C.INQUIRY_REASONS, key=k("reason"))
        detail = st.text_area("세부문의사항", height=140, key=k("detail"))
        avail = st.date_input("상담 가능 날짜", value=None, key=k("avail"))

        st.markdown("")
        allow_dup = st.checkbox("중복이어도 등록", key=k("dup"),
                                help="연락처 또는 병원명이 같은 DB가 이미 있어도 새로 등록합니다.")
        submitted = st.button("등록", type="primary", width="stretch")

    if not submitted:
        return
    if not hospital.strip() or not phone.strip():
        st.warning("병원명과 연락처는 필수입니다.")
        return
    if channel == C.CHANNEL_ETC and not channel_etc.strip():
        st.warning("유입경로 '기타'는 직접 입력해주세요.")
        return
    if dept_sel == C.DEPT_ETC and not dept_etc.strip():
        st.warning("분과 '기타'는 직접 입력해주세요.")
        return
    dup = D.find_similar(phone, hospital)
    if not dup.empty and not allow_dup:
        st.warning(f"⚠️ 연락처 또는 병원명이 같은 DB가 이미 {len(dup)}건 있습니다. "
                   "그래도 등록하려면 '중복이어도 등록'을 체크하세요.")
        st.dataframe(dup[["순번", "입력날짜", "담당부서", "진행상황", "병원명", "연락처"]],
                     hide_index=True, width="stretch")
        return

    no = D.add_db({
        "입력날짜": str(in_date), "담당부서": "", "병원명": hospital.strip(),
        "병원소재지": normalize_addr(f"{region or ''} {sigungu.strip()}"),
        "분과": (dept_etc.strip() if dept_sel == C.DEPT_ETC else (dept_sel or "")),
        "연락처": phone, "담당자": person.strip(), "문의이유": ", ".join(reason),
        "상담가능날짜": str(avail) if avail else "",
        "세부문의사항": detail.strip(), "유입경로": channel, "유입경로_기타": channel_etc.strip(),
        "비고": note.strip(), "등록경로": "수동입력",
    }, author=user["id"])
    st.session_state["input_flash"] = (f"✅ {no} · {hospital.strip()} 등록이 완료되었습니다. "
                                       "메인 페이지에서 담당 팀을 배정해주세요.")
    st.session_state["input_ver"] = ver + 1
    st.rerun()


# ══ DB 일괄 등록 ════════════════════════════════════════════════
def _bulk_import():
    if msg := st.session_state.pop("bulk_flash", None):
        st.success(msg)
    t_paste, t_file = st.tabs(["📋 복사해서 붙여넣기", "📁 파일로 등록 (엑셀·CSV)"])
    with t_paste:
        _paste_import()
    with t_file:
        _file_import()


def _paste_import():
    st.caption("엑셀에서 복사한 표를 그대로 붙여넣어 여러 건을 한 번에 등록합니다. "
               "과거 DB, 외부 플랫폼에서 받은 DB 모두 사용할 수 있어요. "
               "순번을 비우면 입력날짜 연도에 맞춰 자동으로 부여됩니다.")
    cols = C.BULK_INPUT_COLS
    ver = st.session_state.setdefault("db_bulk_ver", 0)
    col_config = {
        "담당부서": st.column_config.SelectboxColumn(options=[""] + C.TEAMS),
        "진행상황": st.column_config.SelectboxColumn(options=[""] + C.STATUSES),
        "유입경로": st.column_config.SelectboxColumn(options=[""] + C.CHANNELS),
        "분과": st.column_config.SelectboxColumn(options=[""] + C.DEPARTMENTS),
        "기타": st.column_config.TextColumn(help="캠페인·특이사항 — 비고로 저장됩니다"),
        "순번": st.column_config.TextColumn(help="비워두면 자동 부여 (예: 26-045 처럼 직접 지정도 가능)"),
    }

    st.caption("엑셀에서 여러 행을 복사한 뒤, 표의 첫 칸을 클릭하고 Ctrl+V 하세요. 표가 모자라면 자동으로 늘어납니다.")
    blank = pd.DataFrame([{c: "" for c in cols} for _ in range(10)])
    edited = st.data_editor(blank, hide_index=True, num_rows="dynamic", width="stretch",
                            key=f"db_bulk_editor_{ver}", column_config=col_config)

    c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
    source = c1.text_input("등록경로 표시", value="일괄등록", key=f"db_bulk_src_{ver}",
                           help="외부 플랫폼에서 받은 DB라면 플랫폼 이름을 적어두면 나중에 구분하기 좋아요.")
    if c2.button("붙여넣은 내용 일괄 등록", type="primary", key=f"db_bulk_submit_{ver}"):
        rows = []
        for r in edited.to_dict("records"):
            row = {C.BULK_ALIAS.get(k, k): v for k, v in r.items()}
            row["등록경로"] = source.strip() or "일괄등록"
            rows.append(row)
        nos = D.bulk_add_db(rows, A.current_user()["id"])
        if nos:
            st.session_state["db_bulk_ver"] = ver + 1
            st.session_state["bulk_flash"] = _done_message(nos)
            st.rerun()
        else:
            st.warning("등록할 내용이 없습니다. (병원명이 비어있으면 건너뜁니다)")


def _done_message(nos: list) -> str:
    span = f"{nos[0]} ~ {nos[-1]}" if len(nos) > 1 else nos[0]
    return (f"✅ {len(nos)}건이 등록되었습니다. (순번 {span}) "
            "담당부서를 비워둔 DB는 메인 페이지에서 배정해주세요.")


# ══ 파일로 등록 (엑셀·CSV) ══════════════════════════════════════
def _file_import():
    st.caption("엑셀(.xlsx)이나 CSV 파일을 그대로 올려서 등록합니다. "
               "**순번은 적지 않아도 됩니다** — 파일에 적힌 순서대로 앱이 번호를 이어서 매깁니다. "
               "파일에 순번 열이 있어도 무시합니다.")
    ver = st.session_state.setdefault("db_file_ver", 0)
    k = lambda name: f"db_file_{name}_{ver}"            # noqa: E731

    up = st.file_uploader("DB 파일 올리기", type=["xlsx", "xlsm", "csv", "tsv"], key=k("up"))
    if up is None:
        _template_box()
        return

    data = up.getvalue()
    try:
        sheets = IM.sheet_names(data, up.name)
    except Exception as e:
        st.error(f"파일을 열지 못했습니다. 엑셀(.xlsx)이나 CSV 파일인지 확인해주세요.\n\n`{e}`")
        return

    c1, c2, _ = st.columns([1.6, 1, 1.4])
    sheet = c1.selectbox("시트", sheets, key=k("sheet")) if sheets else None
    header_row = c2.number_input("열 이름이 있는 줄", 1, 20, 1, key=k("hdr"),
                                 help="열 이름(병원명·연락처 …)이 적힌 줄이 몇 번째인지. 보통 1입니다.")
    try:
        raw = IM.read_table(data, up.name, sheet, int(header_row)).dropna(how="all")
    except Exception as e:
        st.error(f"표를 읽지 못했습니다. 시트와 '열 이름이 있는 줄'을 확인해주세요.\n\n`{e}`")
        return
    if raw.empty:
        st.warning("읽을 내용이 없습니다. 시트나 '열 이름이 있는 줄'을 확인해주세요.")
        return

    st.caption(f"**{len(raw):,}줄** 을 읽었습니다. 열 이름: {', '.join(str(c) for c in raw.columns[:12])}"
               + (" …" if len(raw.columns) > 12 else ""))
    with st.expander("파일 원본 먼저 보기 (처음 20줄)"):
        st.dataframe(raw.head(20), width="stretch")

    mapping = _mapping_editor(raw, k)
    if not mapping.get("병원명"):
        st.warning("**병원명** 열을 연결해주세요. 병원명 없이는 등록할 수 없습니다.")
        return

    rows, issues = IM.clean_rows(raw, mapping)
    if not rows:
        st.warning("등록할 줄이 없습니다. (병원명이 빈 줄은 건너뜁니다)")
        return

    dups = D.preview_duplicates(rows)
    n_dup = sum(1 for d in dups if d)

    st.divider()
    st.markdown(f"**등록 미리보기 · {len(rows):,}건**")
    prev = pd.DataFrame(rows)
    prev.insert(0, "중복", ["⚠️ " + d if d else "" for d in dups])
    st.dataframe(prev, hide_index=True, width="stretch", height=320,
                 column_config={"중복": st.column_config.TextColumn(width="medium"),
                                "세부문의사항": st.column_config.TextColumn(width="medium")})

    if not issues.empty:
        with st.expander(f"⚠️ 확인할 내용 {len(issues)}건 — 등록은 됩니다", expanded=n_dup == 0):
            st.caption("앱 형식에 맞춰 바꾼 값과, 읽지 못한 값입니다. 고쳐야 하면 파일을 수정해서 다시 올리세요.")
            st.dataframe(issues, hide_index=True, width="stretch")

    skip_dup = False
    if n_dup:
        st.warning(f"⚠️ 이미 있는 DB와 겹치거나 파일 안에서 중복되는 줄이 **{n_dup}건** 있습니다.")
        skip_dup = st.checkbox(f"중복 {n_dup}건은 빼고 등록", value=True, key=k("skipdup"))

    final = [r for r, d in zip(rows, dups) if not (skip_dup and d)]
    c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
    source = c1.text_input("등록경로 표시", value=f"파일등록({up.name[:20]})", key=k("src"),
                           help="나중에 어디서 받은 DB인지 구분할 수 있게 적어둡니다.")
    if c2.button(f"{len(final):,}건 등록하기", type="primary", key=k("go"),
                 disabled=not final, width="stretch"):
        for r in final:
            r["등록경로"] = source.strip() or "파일등록"
        nos = D.bulk_add_db(final, A.current_user()["id"], note=f"파일 일괄 등록 ({up.name})")
        if nos:
            st.session_state["db_file_ver"] = ver + 1
            st.session_state["bulk_flash"] = _done_message(nos)
            st.rerun()
        else:
            st.warning("등록할 내용이 없습니다.")


def _mapping_editor(raw, k) -> dict:
    """파일 열 ↔ 앱 항목 연결. 자동으로 맞춰 보여주고, 틀리면 직접 고칠 수 있게 합니다."""
    cols = [str(c) for c in raw.columns]
    auto = IM.guess_mapping(raw.columns)
    NONE = "(연결 안 함)"
    # 시트·헤더 줄을 바꾸면 열 목록이 통째로 달라집니다. 그때 예전 선택이 남아 있으면
    # 자동 연결이 무시되므로, 열 목록을 위젯 key 에 섞어 새로 잡게 합니다.
    sig = zlib.crc32("\u0000".join(cols).encode())
    summary = st.empty()                       # 연결 결과를 '확정된 값'으로 위에 보여주려고 자리만 잡아둡니다

    with st.expander("🔧 열 연결 고치기", expanded=not auto.get("병원명")):
        st.caption("왼쪽이 앱 항목, 오른쪽이 파일의 열입니다. 자동 연결이 틀렸으면 바꿔주세요.")
        picked, grid, opts = {}, st.columns(2), [NONE] + cols
        for i, app in enumerate(IM.IMPORT_COLS):
            cur = auto.get(app)
            sel = grid[i % 2].selectbox(
                app + (" *" if app in IM.REQUIRED else ""), opts,
                index=opts.index(cur) if cur in opts else 0, key=k(f"map_{app}_{sig}"))
            if sel != NONE:
                picked[app] = sel

    found = [f"**{app}** ← {picked[app]}" for app in IM.IMPORT_COLS if app in picked]
    missing = [app for app in IM.IMPORT_COLS if app not in picked]
    with summary.container():
        if found:
            st.success("열 연결 · " + "  /  ".join(found))
        else:
            st.warning("열 이름을 알아보지 못했습니다. 아래 '열 연결 고치기'에서 직접 연결해주세요.")
        if missing:
            st.caption("연결되지 않은 항목(비워둬도 됩니다): " + ", ".join(missing))
    return picked


def _template_box():
    """파일이 아직 없을 때: 어떤 형식이어야 하는지 + 빈 양식 내려받기."""
    st.info("올릴 파일이 아직 없습니다. 아래 양식을 받아서 채워 올리시면 가장 확실합니다.")
    t = IM.template()
    st.dataframe(t, hide_index=True, width="stretch")
    UI.download_csv(t.iloc[0:0], "DB_업로드_양식.csv", "⬇️ 빈 양식 받기 (CSV)", key="db_file_tpl")
    st.caption("열 이름이 양식과 달라도 됩니다 — '전화번호', '병원 담당자', '애드리절트 담당부서'처럼 "
               "흔히 쓰는 이름은 앱이 알아서 찾아 연결하고, 못 찾으면 직접 연결할 수 있습니다. "
               f"**병원명만 필수**이고 나머지는 비어도 됩니다. 담당부서를 비우면 {C.UNASSIGNED}로 들어갑니다.")

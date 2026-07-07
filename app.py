"""
agent.py에 있는 기능들을 그대로 가져다 쓰는 웹 화면(Streamlit)입니다.
터미널에 글자를 치지 않고, 웹 화면에서 날짜 선택/검색어 입력/버튼 클릭만으로 사용할 수 있어요.

결과 아래에는 파일로 내려받는 버튼도 있어요.
- 목록형 결과(회의록 할 일, 검색 결과) → CSV
- 줄글형 결과(일정, 요약, 보고서 답변) → PDF (한글 폰트 fonts/malgun.ttf 적용)

사용법:
    1) pip install anthropic streamlit reportlab
    2) 이 폴더의 .env 파일에 ANTHROPIC_API_KEY=실제_키 형식으로 키를 넣기
    3) streamlit run app.py
"""

import contextlib
import csv
import datetime
import io
import os
import re

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import agent

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "malgun.ttf")
FONT_NAME = "Malgun"
if os.path.isfile(FONT_PATH):
    pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
else:
    # 한글 폰트 파일이 없으면 PDF에서 한글이 깨질 수 있어요.
    FONT_NAME = "Helvetica"


def run_and_capture(func, *args, **kwargs) -> str:
    """agent.py의 print() 기반 함수를 그대로 호출하고, 출력 내용을 문자열로 캡처해서 돌려줍니다."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        func(*args, **kwargs)
    return buffer.getvalue().strip()


def wrap_line(c: canvas.Canvas, text: str, font_name: str, font_size: int, max_width: float):
    """한 줄 텍스트를 PDF 페이지 너비에 맞게 글자 단위로 줄바꿈합니다."""
    if text == "":
        return [""]
    lines = []
    current = ""
    for ch in text:
        candidate = current + ch
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def build_pdf_bytes(text: str, title: str) -> bytes:
    """줄글 텍스트를 한글 폰트가 적용된 PDF 파일(바이트)로 만듭니다."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x_margin = 20 * mm
    max_width = width - 2 * x_margin
    y = height - 20 * mm

    c.setFont(FONT_NAME, 16)
    for line in wrap_line(c, title, FONT_NAME, 16, max_width):
        c.drawString(x_margin, y, line)
        y -= 9 * mm
    y -= 4 * mm

    c.setFont(FONT_NAME, 11)
    for paragraph in text.split("\n"):
        for line in wrap_line(c, paragraph, FONT_NAME, 11, max_width):
            if y < 20 * mm:
                c.showPage()
                c.setFont(FONT_NAME, 11)
                y = height - 20 * mm
            c.drawString(x_margin, y, line)
            y -= 6 * mm

    c.save()
    return buffer.getvalue()


def build_csv_bytes(header, rows) -> bytes:
    """표 형태 데이터를 엑셀에서 한글이 안 깨지는 CSV 파일(바이트)로 만듭니다."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def parse_search_results(raw_text: str):
    """search_work_files()의 출력 텍스트를 표 형태(분류/파일/줄번호/내용)로 변환합니다."""
    header_re = re.compile(r"^\[(.+?)\]\s+(.+)$")
    line_re = re.compile(r"^(\d+)줄:\s*(.*)$")
    rows = []
    current_label, current_file = None, None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header_match = header_re.match(line)
        if header_match:
            current_label, current_file = header_match.group(1), header_match.group(2)
            continue
        line_match = line_re.match(line)
        if line_match and current_file:
            rows.append([current_label, current_file, line_match.group(1), line_match.group(2)])
    return ["분류", "파일", "줄번호", "내용"], rows


def parse_markdown_table(raw_text: str):
    """마크다운 표(| ... | ... |) 줄만 뽑아서 행 목록으로 변환합니다."""
    rows = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{1,}:?", c) for c in cells if c != ""):
            continue  # |---|---| 같은 구분선 줄은 건너뜁니다.
        rows.append(cells)
    return rows


def parse_action_items_for_csv(raw_text: str):
    """extract_meeting_action_items()의 결과(마크다운 표 또는 자유 형식)를 표 형태로 변환합니다."""
    table_rows = parse_markdown_table(raw_text)
    if table_rows:
        return table_rows[0], table_rows[1:]

    dash_rows = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip().lstrip("-• ").strip()
        if not line or " - " not in line:
            continue
        parts = [p.strip() for p in line.split(" - ")]
        if len(parts) >= 2:
            dash_rows.append(parts)
    if dash_rows:
        base_header = ["담당자", "할 일", "기한"]
        max_len = max(len(r) for r in dash_rows)
        header = base_header[:max_len] if max_len <= len(base_header) else base_header + [
            f"항목{i + 1}" for i in range(len(base_header), max_len)
        ]
        return header, dash_rows

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return ["내용"], [[line] for line in lines]


def get_api_key():
    """Streamlit Cloud의 Secrets(st.secrets)를 먼저 보고, 없으면 로컬 .env/환경변수를 씁니다."""
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except FileNotFoundError:
        pass  # 로컬처럼 secrets.toml 자체가 없는 경우
    return os.environ.get("ANTHROPIC_API_KEY")


@st.cache_resource
def get_client():
    agent.load_env_file(agent.ENV_FILE)
    return agent.anthropic.Anthropic(api_key=get_api_key())


st.set_page_config(page_title="총무팀 업무 도우미", page_icon="🗂️")
st.title("🗂️ 총무팀 업무 도우미")

try:
    client = get_client()
except Exception as e:
    client = None
    st.error(f"Anthropic 클라이언트를 초기화하지 못했어요: {e}")
    st.info(".env 파일에 ANTHROPIC_API_KEY가 올바르게 들어있는지 확인해 주세요.")

st.header("📅 날짜별 일정 / 🔎 문서 검색")

col1, col2 = st.columns(2)

with col1:
    selected_date = st.date_input("날짜를 골라주세요", value=datetime.date.today())
    if st.button("그 날짜 일정 보기"):
        date_str = selected_date.strftime("%Y-%m-%d")
        st.session_state["date_schedule_result"] = run_and_capture(
            agent.show_schedule_for_date, date_str
        )
        st.session_state["date_schedule_date"] = date_str

    if "date_schedule_result" in st.session_state:
        st.text(st.session_state["date_schedule_result"])
        date_str = st.session_state["date_schedule_date"]
        pdf_bytes = build_pdf_bytes(st.session_state["date_schedule_result"], f"{date_str} 일정")
        st.download_button(
            "📄 PDF로 내려받기",
            data=pdf_bytes,
            file_name=f"{date_str}_일정.pdf",
            mime="application/pdf",
            key="dl_date_schedule",
        )

with col2:
    keyword = st.text_input("업무 파일에서 찾을 단어를 입력하세요")
    if st.button("검색하기"):
        if keyword.strip():
            st.session_state["search_result"] = run_and_capture(agent.search_work_files, keyword)
            st.session_state["search_keyword"] = keyword
        else:
            st.warning("검색할 단어를 입력해 주세요.")

    if "search_result" in st.session_state:
        st.text(st.session_state["search_result"])
        header, rows = parse_search_results(st.session_state["search_result"])
        if rows:
            csv_bytes = build_csv_bytes(header, rows)
            st.download_button(
                "📊 CSV로 내려받기",
                data=csv_bytes,
                file_name=f"검색결과_{st.session_state['search_keyword']}.csv",
                mime="text/csv",
                key="dl_search",
            )

st.divider()
st.header("✅ 오늘 할 일 / 회의록 정리 / 보고서 질문")

if st.button("오늘 할 일 정리"):
    if client is None:
        st.error("Anthropic 클라이언트가 준비되지 않아서 실행할 수 없어요.")
    else:
        with st.spinner("오늘 일정을 정리하고 있어요..."):
            st.session_state["today_summary_result"] = run_and_capture(
                agent.summarize_today_schedule, client
            )

if "today_summary_result" in st.session_state:
    st.text(st.session_state["today_summary_result"])
    pdf_bytes = build_pdf_bytes(
        st.session_state["today_summary_result"], f"오늘({datetime.date.today()}) 할 일 정리"
    )
    st.download_button(
        "📄 PDF로 내려받기",
        data=pdf_bytes,
        file_name=f"오늘할일정리_{datetime.date.today()}.pdf",
        mime="application/pdf",
        key="dl_today_summary",
    )

if st.button("회의록 할 일 뽑기"):
    if client is None:
        st.error("Anthropic 클라이언트가 준비되지 않아서 실행할 수 없어요.")
    else:
        with st.spinner("회의록에서 할 일을 뽑고 있어요..."):
            st.session_state["meeting_items_result"] = run_and_capture(
                agent.extract_meeting_action_items, client
            )

if "meeting_items_result" in st.session_state:
    st.text(st.session_state["meeting_items_result"])
    header, rows = parse_action_items_for_csv(st.session_state["meeting_items_result"])
    if rows:
        csv_bytes = build_csv_bytes(header, rows)
        st.download_button(
            "📊 CSV로 내려받기",
            data=csv_bytes,
            file_name="회의록_할일목록.csv",
            mime="text/csv",
            key="dl_meeting_items",
        )

if st.button("이번 주 회의록 정리"):
    if client is None:
        st.error("Anthropic 클라이언트가 준비되지 않아서 실행할 수 없어요.")
    else:
        with st.spinner("이번 주 회의록을 정리하고 있어요..."):
            st.session_state["weekly_meeting_result"] = run_and_capture(
                agent.summarize_this_week_meetings, client
            )

if "weekly_meeting_result" in st.session_state:
    st.text(st.session_state["weekly_meeting_result"])
    pdf_bytes = build_pdf_bytes(st.session_state["weekly_meeting_result"], "이번 주 회의록 정리")
    st.download_button(
        "📄 PDF로 내려받기",
        data=pdf_bytes,
        file_name=f"이번주회의록정리_{datetime.date.today()}.pdf",
        mime="application/pdf",
        key="dl_weekly_meeting",
    )

report_question = st.text_input("보고서에 대해 궁금한 점을 입력하세요")
if st.button("보고서에 질문하기"):
    if client is None:
        st.error("Anthropic 클라이언트가 준비되지 않아서 실행할 수 없어요.")
    elif not report_question.strip():
        st.warning("질문을 입력해 주세요.")
    else:
        with st.spinner("보고서를 확인하고 있어요..."):
            st.session_state["report_answer_result"] = run_and_capture(
                agent.answer_from_reports, client, report_question
            )
            st.session_state["report_answer_question"] = report_question

if "report_answer_result" in st.session_state:
    st.text(st.session_state["report_answer_result"])
    pdf_bytes = build_pdf_bytes(
        st.session_state["report_answer_result"],
        f"보고서 질문: {st.session_state.get('report_answer_question', '')}",
    )
    st.download_button(
        "📄 PDF로 내려받기",
        data=pdf_bytes,
        file_name="보고서_답변.pdf",
        mime="application/pdf",
        key="dl_report_answer",
    )

if st.button("🌅 오늘 아침 브리핑"):
    if client is None:
        st.error("Anthropic 클라이언트가 준비되지 않아서 실행할 수 없어요.")
    else:
        with st.spinner("오늘 아침 브리핑을 만들고 있어요..."):
            st.session_state["morning_briefing_result"] = run_and_capture(
                agent.morning_briefing, client
            )

if "morning_briefing_result" in st.session_state:
    st.text(st.session_state["morning_briefing_result"])
    pdf_bytes = build_pdf_bytes(
        st.session_state["morning_briefing_result"], f"오늘({datetime.date.today()}) 아침 브리핑"
    )
    st.download_button(
        "📄 PDF로 내려받기",
        data=pdf_bytes,
        file_name=f"오늘아침브리핑_{datetime.date.today()}.pdf",
        mime="application/pdf",
        key="dl_morning_briefing",
    )

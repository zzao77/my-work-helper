"""
work-files(schedule/meetings/reports) 안의 내용을 읽어서,
터미널에서 묻는 질문에 그 내용만 근거로 답해주는 간단한 업무 도우미입니다.

사용법:
    1) pip install anthropic
    2) 이 폴더의 .env 파일에 ANTHROPIC_API_KEY=실제_키 형식으로 키를 넣기
    3) python agent.py
"""

import datetime
import os
import re
import sys

import anthropic

MODEL = "claude-sonnet-4-6"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_FILES_DIR = os.path.join(BASE_DIR, "work-files")
ENV_FILE = os.path.join(BASE_DIR, ".env")

TARGET_FOLDERS = {
    "schedule": "일정",
    "meetings": "회의록",
    "reports": "보고서",
}


def load_env_file(path: str) -> None:
    """.env 파일의 KEY=VALUE 줄을 읽어서 환경변수로 등록합니다 (이미 설정된 값은 덮어쓰지 않음)."""
    if not os.path.isfile(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_work_files() -> str:
    """schedule / meetings / reports 폴더의 파일들을 읽어서 하나의 문자열로 합칩니다."""
    sections = []
    for folder_name, label in TARGET_FOLDERS.items():
        folder_path = os.path.join(WORK_FILES_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        file_names = sorted(os.listdir(folder_path))
        for file_name in file_names:
            file_path = os.path.join(folder_path, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # 텍스트로 읽을 수 없는 파일(예: 엑셀, 파워포인트 등)은 건너뜁니다.
                continue

            sections.append(
                f"### [{label}] {folder_name}/{file_name}\n{content.strip()}\n"
            )

    return "\n".join(sections)


def show_today_schedule() -> None:
    """오늘 날짜와 이름이 같은 일정 파일(schedule/연-월-일.txt)을 찾아서 출력합니다."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    schedule_path = os.path.join(WORK_FILES_DIR, "schedule", f"{today_str}.txt")

    if not os.path.isfile(schedule_path):
        print("오늘 날짜의 일정 파일이 없습니다.")
        return

    with open(schedule_path, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"\n오늘({today_str}) 일정 - schedule/{today_str}.txt")
    print(content.strip())


def summarize_today_schedule(client: anthropic.Anthropic) -> None:
    """오늘 일정 파일을 찾아서(위 show_today_schedule과 동일한 방식) Claude에게 3줄 요약을 요청해 출력합니다."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    schedule_path = os.path.join(WORK_FILES_DIR, "schedule", f"{today_str}.txt")

    if not os.path.isfile(schedule_path):
        print("오늘 날짜의 일정 파일이 없습니다.")
        return

    with open(schedule_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=(
                "아래 오늘 일정 내용을 딱 3줄로 간단히 요약해 주세요. "
                "내용에 없는 것은 절대 지어내지 마세요. "
                "항상 한국어로, 공손하고 친절한 '해요체' 말투로 답하세요 (딱딱한 보고서체 금지)."
            ),
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        print(f"요약 중 문제가 생겼어요: {e}")
        return

    summary = next(
        (block.text for block in response.content if block.type == "text"),
        "(요약을 받지 못했어요)",
    )
    print(f"\n오늘({today_str}) 일정 3줄 요약")
    print(summary.strip())


def morning_briefing(client: anthropic.Anthropic) -> None:
    """오늘 일정 파일을 찾아서(위 show_today_schedule과 동일한 방식), 오늘 일정 요약과 오늘 챙길 일을 한 번에 정리해 출력합니다."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    schedule_path = os.path.join(WORK_FILES_DIR, "schedule", f"{today_str}.txt")

    if not os.path.isfile(schedule_path):
        print("오늘 날짜의 일정 파일이 없습니다.")
        return

    with open(schedule_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=(
                "아래는 오늘 일정 내용입니다. 이 내용만 근거로 '오늘 아침 브리핑'을 만들어 주세요. "
                "브리핑은 두 부분으로 구성하세요: "
                "1) 오늘 일정 요약 (간단히 2~3줄), "
                "2) 오늘 꼭 챙겨야 할 일 (급한 일·잊지 말아야 할 것 위주로 목록). "
                "내용에 없는 것은 절대 지어내지 마세요. "
                "항상 한국어로, 공손하고 친절한 '해요체' 말투로 답하세요 (딱딱한 보고서체 금지)."
            ),
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        print(f"브리핑을 만드는 중 문제가 생겼어요: {e}")
        return

    briefing = next(
        (block.text for block in response.content if block.type == "text"),
        "(브리핑을 받지 못했어요)",
    )
    print(f"\n오늘({today_str}) 아침 브리핑")
    print(briefing.strip())


def extract_meeting_action_items(client: anthropic.Anthropic) -> None:
    """meetings 폴더의 회의록들에서 담당자·할 일·기한이 있는 항목만 뽑아서 목록으로 보여줍니다."""
    meetings_dir = os.path.join(WORK_FILES_DIR, "meetings")
    if not os.path.isdir(meetings_dir):
        print("meetings 폴더를 찾을 수 없어요.")
        return

    sections = []
    for file_name in sorted(os.listdir(meetings_dir)):
        file_path = os.path.join(meetings_dir, file_name)
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            continue
        sections.append(f"### meetings/{file_name}\n{content.strip()}")

    if not sections:
        print("meetings 폴더에서 읽을 수 있는 회의록 파일을 찾지 못했어요.")
        return

    meetings_text = "\n\n".join(sections)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "아래는 회의록들입니다. 이 안에서 '누가 무엇을 언제까지 하기로 했는지' "
                "할 일(액션 아이템)만 뽑아서 목록으로 정리해 주세요. "
                "각 항목은 '담당자 - 할 일 - 기한' 형식으로 한 줄씩 적어 주세요. "
                "기한이 명확히 안 적혀 있으면 '기한 미정'이라고 표시하고, "
                "회의록에 실제로 없는 내용은 절대 만들어내지 마세요."
            ),
            messages=[{"role": "user", "content": meetings_text}],
        )
    except anthropic.APIError as e:
        print(f"할 일 추출 중 문제가 생겼어요: {e}")
        return

    result = next(
        (block.text for block in response.content if block.type == "text"),
        "(결과를 받지 못했어요)",
    )
    print("\n회의록에서 뽑은 할 일 목록")
    print(result.strip())


def summarize_this_week_meetings(client: anthropic.Anthropic) -> None:
    """이번 주(월~일)에 해당하는 회의록 파일들만 모아서 한 문단으로 요약합니다."""
    meetings_dir = os.path.join(WORK_FILES_DIR, "meetings")
    if not os.path.isdir(meetings_dir):
        print("meetings 폴더를 찾을 수 없어요.")
        return

    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)

    sections = []
    for file_name in sorted(os.listdir(meetings_dir)):
        file_path = os.path.join(meetings_dir, file_name)
        if not os.path.isfile(file_path):
            continue

        date_match = DATE_PATTERN.match(file_name)
        if not date_match:
            continue
        try:
            file_date = datetime.date.fromisoformat(date_match.group())
        except ValueError:
            continue
        if not (start_of_week <= file_date <= end_of_week):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            continue
        sections.append(f"### meetings/{file_name}\n{content.strip()}")

    if not sections:
        print(f"\n이번 주({start_of_week}~{end_of_week})에 해당하는 회의록이 없습니다.")
        return

    meetings_text = "\n\n".join(sections)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=(
                "아래는 이번 주 회의록입니다. 이 내용만 근거로 한 문단(3~5줄 정도)으로 간단히 요약해 주세요. "
                "여러 문단으로 나누지 말고 하나의 문단으로만 작성하세요. "
                "회의록에 실제로 없는 내용은 절대 지어내지 마세요. "
                "항상 한국어로, 공손하고 친절한 '해요체' 말투로 답하세요 (딱딱한 보고서체 금지)."
            ),
            messages=[{"role": "user", "content": meetings_text}],
        )
    except anthropic.APIError as e:
        print(f"요약 중 문제가 생겼어요: {e}")
        return

    summary = next(
        (block.text for block in response.content if block.type == "text"),
        "(요약을 받지 못했어요)",
    )
    # 응답에 줄바꿈이 섞여 있어도 터미널에는 항상 한 문단(한 줄)으로 보이게 합니다.
    summary_one_paragraph = " ".join(summary.split())
    print(f"\n이번 주({start_of_week}~{end_of_week}) 회의록 요약")
    print(summary_one_paragraph)


def answer_from_reports(client: anthropic.Anthropic, question: str) -> None:
    """reports 폴더의 문서만 읽어서, 그 내용만 근거로 질문에 답합니다. 없는 내용은 모른다고 답해요."""
    reports_dir = os.path.join(WORK_FILES_DIR, "reports")
    if not os.path.isdir(reports_dir):
        print("reports 폴더를 찾을 수 없어요.")
        return

    sections = []
    for file_name in sorted(os.listdir(reports_dir)):
        file_path = os.path.join(reports_dir, file_name)
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # 엑셀/파워포인트처럼 텍스트로 읽을 수 없는 파일은 건너뜁니다.
            continue
        sections.append(f"### reports/{file_name}\n{content.strip()}")

    if not sections:
        print("reports 폴더에서 읽을 수 있는 문서를 찾지 못했어요.")
        return

    reports_text = "\n\n".join(sections)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "아래 <보고서> 안에는 reports 폴더의 문서 내용이 들어 있습니다. "
                "반드시 이 내용만 근거로 질문에 답하세요. "
                "<보고서>에 없는 내용은 절대 추측하거나 지어내지 말고, "
                "\"보고서에서 확인이 안 돼요\"라고 솔직하게 답하세요. "
                "항상 한국어로 공손하고 친절하게 답하세요.\n\n"
                f"<보고서>\n{reports_text}\n</보고서>"
            ),
            messages=[{"role": "user", "content": question}],
        )
    except anthropic.APIError as e:
        print(f"답변 중 문제가 생겼어요: {e}")
        return

    answer = next(
        (block.text for block in response.content if block.type == "text"),
        "(답변을 받지 못했어요)",
    )
    print(f"\n답변> {answer.strip()}")


def show_schedule_for_date(date_str: str) -> None:
    """지정한 날짜(연-월-일)와 이름이 같은 일정 파일을 찾아서 출력합니다."""
    schedule_path = os.path.join(WORK_FILES_DIR, "schedule", f"{date_str}.txt")

    if not os.path.isfile(schedule_path):
        print("그 날짜의 일정 파일이 없습니다.")
        return

    with open(schedule_path, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"\n{date_str} 일정 - schedule/{date_str}.txt")
    print(content.strip())


def show_schedule_range(start_str: str, end_str: str) -> None:
    """시작 날짜부터 끝 날짜까지(양쪽 포함) 일정 파일들을 날짜순으로 모아서 출력합니다."""
    try:
        start_date = datetime.date.fromisoformat(start_str)
        end_date = datetime.date.fromisoformat(end_str)
    except ValueError:
        print("날짜 형식을 이해하지 못했어요. 연-월-일 형식으로 다시 말씀해 주세요.")
        return

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    print(f"\n{start_date}~{end_date} 일정 모음")

    found_any = False
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        schedule_path = os.path.join(WORK_FILES_DIR, "schedule", f"{date_str}.txt")

        if os.path.isfile(schedule_path):
            with open(schedule_path, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"\n[{date_str}] schedule/{date_str}.txt")
            print(content.strip())
            found_any = True
        else:
            print(f"\n[{date_str}] 그 날짜의 일정 파일이 없습니다.")

        current += datetime.timedelta(days=1)

    if not found_any:
        print("\n해당 기간에는 일정 파일이 하나도 없습니다.")


def search_work_files(keyword: str) -> None:
    """work-files 전체(schedule/meetings/reports)에서 키워드가 들어간 파일과 해당 부분(줄)을 찾아 보여줍니다."""
    if not keyword.strip():
        print("검색할 키워드를 입력해 주세요.")
        return

    found_any = False
    for folder_name, label in TARGET_FOLDERS.items():
        folder_path = os.path.join(WORK_FILES_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        for file_name in sorted(os.listdir(folder_path)):
            file_path = os.path.join(folder_path, file_name)
            if not os.path.isfile(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                # 텍스트로 읽을 수 없는 파일(예: 엑셀, 파워포인트 등)은 건너뜁니다.
                continue

            matched_lines = [
                (line_no, line.strip())
                for line_no, line in enumerate(lines, start=1)
                if keyword in line
            ]
            if not matched_lines:
                continue

            found_any = True
            print(f"\n[{label}] {folder_name}/{file_name}")
            for line_no, line_text in matched_lines:
                print(f"  {line_no}줄: {line_text}")

    if not found_any:
        print(f"\n'{keyword}'가 들어간 파일을 찾지 못했어요.")


def build_system_prompt(work_files_content: str) -> str:
    return f"""당신은 총무팀 사무 담당자를 돕는 업무 도우미입니다.
아래 <업무자료> 안에는 일정(schedule), 회의록(meetings), 보고서(reports) 폴더의 내용이 들어 있습니다.

답변 규칙:
- 반드시 <업무자료>에 실제로 적힌 내용만 근거로 답하세요.
- <업무자료>에 없는 내용은 절대 추측하거나 지어내지 말고, "자료에서 확인이 안 돼요"라고 솔직하게 답하세요.
- 항상 한국어로, 공손하고 친절한 업무 도우미 말투로 답하세요.
- 답변은 간결하게, 필요하면 관련 파일명(예: schedule/2026-07-07.txt)도 함께 알려주세요.

<업무자료>
{work_files_content}
</업무자료>
"""


def main() -> None:
    # 일부 한글 Windows 콘솔(cp949)은 '—' 같은 특수문자를 출력하지 못해 에러가 나므로,
    # 표준출력을 UTF-8로 맞춰서 파일 내용을 그대로 출력해도 깨지지 않게 합니다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_env_file(ENV_FILE)

    work_files_content = load_work_files()
    if not work_files_content.strip():
        print("work-files 폴더에서 읽을 수 있는 파일을 찾지 못했어요. 폴더 구성을 확인해 주세요.")
        return

    system_prompt = build_system_prompt(work_files_content)

    try:
        client = anthropic.Anthropic()
    except Exception as e:
        print(f"Anthropic 클라이언트를 초기화하지 못했어요: {e}")
        return

    print("업무 도우미를 시작할게요! (종료하려면 'exit' 또는 '종료' 입력)")
    print("문서 검색은 '검색 <키워드>' 형식으로 입력해 주세요. (예: 검색 예산)")
    print("이번 주 회의록 요약은 '이번 주 회의록 요약해줘'처럼 물어보세요.")
    messages = []

    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료할게요. 수고하셨어요!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "종료"):
            print("종료할게요. 수고하셨어요!")
            break

        if question.startswith("검색"):
            keyword = question[len("검색"):].strip(" :")
            search_work_files(keyword)
            continue

        if "회의" in question and "요약" in question:
            summarize_this_week_meetings(client)
            continue

        date_matches = DATE_PATTERN.findall(question)
        if len(date_matches) >= 2:
            show_schedule_range(date_matches[0], date_matches[1])
            continue
        if len(date_matches) == 1:
            show_schedule_for_date(date_matches[0])
            continue
        if "오늘" in question and "일정" in question:
            show_today_schedule()
            continue

        messages.append({"role": "user", "content": question})

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            print("API 키 인증에 실패했어요. ANTHROPIC_API_KEY 환경변수를 확인해 주세요.")
            messages.pop()
            continue
        except anthropic.APIError as e:
            print(f"API 호출 중 문제가 생겼어요: {e}")
            messages.pop()
            continue

        answer = next(
            (block.text for block in response.content if block.type == "text"),
            "(답변을 받지 못했어요)",
        )
        print(f"\n답변> {answer}")

        messages.append({"role": "assistant", "content": response.content})


if __name__ == "__main__":
    sys.exit(main() or 0)

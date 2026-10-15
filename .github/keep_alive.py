"""Streamlit Community Cloud 앱이 잠들지 않도록 실제로 페이지를 방문합니다."""
import sys
import time

from playwright.sync_api import sync_playwright

WAKE_WORDS = ["get this app back up", "Yes, get this app back up!", "app back up",
              "다시 켜기", "앱 깨우기"]
ALIVE_HINTS = ["애드리절트", "아이디", "비밀번호", "로그인", "stApp"]


def main(url: str) -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(60_000)

        print(f"접속 시도: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(8)

        for word in WAKE_WORDS:
            try:
                btn = page.get_by_text(word, exact=False)
                if btn.count() and btn.first.is_visible():
                    print(f"잠든 상태 감지 → '{word}' 클릭")
                    btn.first.click()
                    time.sleep(45)
                    break
            except Exception:
                pass

        time.sleep(10)
        html = page.content()
        title = page.title()
        ok = any(h in html for h in ALIVE_HINTS)

        page.screenshot(path="keepalive.png", full_page=False)
        browser.close()

        print(f"제목: {title}")
        print(f"HTML 길이: {len(html):,}")
        if ok:
            print("✅ 앱이 정상 동작 중입니다.")
            return 0
        print("⚠️ 페이지는 열렸지만 앱 화면을 확인하지 못했습니다.")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].startswith("http"):
        print("사용법: python keep_alive.py https://your-app.streamlit.app")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))

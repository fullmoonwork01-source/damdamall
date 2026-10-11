"""
초기 더미 데이터 시딩.
- 유저 30명(관리자 1명 포함), 상품 30개, 상품별 리뷰 0~5개, 과거 주문 몇 건,
  쿠폰 몇 개, Q&A 몇 건을 만들어 넣는다.
- DB 파일이 이미 있으면 아무 것도 하지 않는다 (매 재시작마다 새로 만들고
  싶으면 damdamall.db 파일을 지우고 다시 실행하면 된다).
"""
import hashlib
import random

from faker import Faker

from db import get_db

fake = Faker("ko_KR")

CATEGORIES = ["뷰티", "식품", "생활용품", "패션", "전자기기", "홈리빙"]

PRODUCT_NAME_TEMPLATES = {
    "뷰티": ["수분 진정 크림", "저자극 선크림 SPF50", "비타민C 세럼", "촉촉 립밤",
             "모공 타이트닝 토너", "클렌징 오일", "쿠션 파운데이션", "헤어 에센스"],
    "식품": ["유기농 그래놀라", "저당 프로틴바", "콜드브루 원액", "수제 곤약젤리",
             "제주 감귤청", "무첨가 견과 믹스", "동결건조 딸기칩", "귀리 우유"],
    "생활용품": ["초극세사 걸레", "무형광 세탁세제", "탈취 섬유향수", "다회용 지퍼백",
               "실리콘 밀폐용기 세트", "먼지없는 극세사 밀대", "친환경 주방세제"],
    "패션": ["오버핏 맨투맨", "와이드 슬랙스", "니트 가디건", "레더 크로스백",
            "베이직 반팔 티셔츠", "울 블렌드 코트", "스트랩 샌들"],
    "전자기기": ["무선 이어버드", "보조배터리 20000mAh", "블루투스 스피커",
              "휴대용 가습기", "미니 공기청정기", "저소음 무선 마우스", "USB-C 허브"],
    "홈리빙": ["패브릭 러그", "LED 무드등", "디퓨저 세트", "폴딩 수납박스",
             "메모리폼 베개", "미니 화분 세트", "암막 커튼"],
}

REVIEW_GOOD = [
    "생각보다 훨씬 좋아요! 재구매 의사 100%입니다.",
    "가격 대비 품질 최고예요. 주변에도 추천했어요.",
    "배송도 빠르고 포장도 꼼꼼해서 만족스러웠습니다.",
    "설명이랑 실물이 똑같아서 믿고 살 수 있었어요.",
    "선물용으로 샀는데 반응이 너무 좋았어요.",
]
REVIEW_BAD = [
    "생각보다 별로였어요. 사진이랑 살짝 다른 느낌.",
    "배송이 너무 오래 걸려서 아쉬웠습니다.",
    "가격 대비 그냥 그래요, 재구매는 고민중이에요.",
    "포장이 살짝 찌그러진 채로 왔어요. 교환 문의 남겨요.",
]


def _hash_pw(pw: str) -> str:
    return hashlib.md5(pw.encode()).hexdigest()


def seed(force=False):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] > 0 and not force:
        conn.close()
        print("[seed] 이미 데이터가 있어 시딩을 건너뜁니다.")
        return

    print("[seed] 더미 데이터 생성 중...")

    # --- 카테고리 ---
    for c in CATEGORIES:
        cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (c,))

    # --- 유저 (관리자 1 + 일반 29) ---
    user_ids = []
    cur.execute(
        "INSERT INTO users (username, email, password_hash, nickname, bio, address, is_admin, points) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
        ("admin", "admin@ooshop.example", _hash_pw("admin1234"), "관리자",
         "담다몰 운영팀입니다.", "서울시 강남구 테헤란로 1 담다몰 본사"),
    )
    admin_id = cur.lastrowid
    user_ids.append(admin_id)

    for _ in range(29):
        username = fake.user_name()
        email = fake.email()
        pw = _hash_pw(random.choice(["password123", "qwer1234", "abcd1234", "letmein1", "iloveyou1"]))
        nickname = fake.name() + random.choice(["", "님", "_" + str(random.randint(1, 999))])
        bio = random.choice([
            "안녕하세요, 잘 부탁드립니다!", "쇼핑 좋아하는 사람입니다.",
            "가성비 좋은 제품 찾는 중이에요.", "", "리뷰 이벤트 참여 중!",
        ])
        address = fake.address()
        points = random.choice([0, 1000, 3000, 5000, 12000])
        try:
            cur.execute(
                "INSERT INTO users (username, email, password_hash, nickname, bio, address, is_admin, points) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (username, email, pw, nickname, bio, address, points),
            )
            user_ids.append(cur.lastrowid)
        except Exception:
            continue

    # --- 배송지 ---
    for uid in user_ids:
        for i in range(random.randint(1, 2)):
            cur.execute(
                "INSERT INTO addresses (user_id, recipient, phone, address, is_default) VALUES (?, ?, ?, ?, ?)",
                (uid, fake.name(), fake.phone_number(), fake.address(), 1 if i == 0 else 0),
            )

    # --- 상품 ---
    product_ids = []
    colors = ["#5b7fff", "#ff8a5b", "#3ec28f", "#ff5b8c", "#8a5bff", "#ffb84d"]
    for cat, names in PRODUCT_NAME_TEMPLATES.items():
        for name in names:
            price = random.choice([5900, 8900, 12900, 15900, 19900, 25900, 32900, 45900, 59000, 89000])
            stock = random.choice([0, 1, 2, 5, 10, 20, 50, 100])
            desc = (
                f"{fake.catch_phrase()}. {name}은(는) 매일 사용하기 좋은 {cat} 아이템입니다. "
                f"{fake.bs()}."
            )
            cur.execute(
                "INSERT INTO products (name, description, price, category, stock, color) VALUES (?, ?, ?, ?, ?, ?)",
                (name, desc, price, cat, stock, random.choice(colors)),
            )
            product_ids.append(cur.lastrowid)

    # --- 리뷰 ---
    for pid in product_ids:
        for _ in range(random.randint(0, 5)):
            uid = random.choice(user_ids)
            good = random.random() < 0.75
            content = random.choice(REVIEW_GOOD if good else REVIEW_BAD)
            rating = random.randint(4, 5) if good else random.randint(1, 3)
            cur.execute(
                "INSERT INTO reviews (product_id, user_id, rating, content) VALUES (?, ?, ?, ?)",
                (pid, uid, rating, content),
            )

    # --- Q&A 게시판(상품과 무관한 일반 고객센터 문의) ---
    board_categories = ["배송문의", "상품문의", "환불/교환", "회원/주문", "기타"]
    board_titles = [
        "배송이 너무 늦어요", "주문 취소하고 싶어요", "포인트가 안 들어왔어요",
        "교환 신청은 어떻게 하나요", "회원 탈퇴 문의드립니다", "쿠폰이 적용이 안 돼요",
        "결제 오류가 발생했어요", "재입고 알림은 어디서 신청하나요", "영수증 발급 문의",
        "비회원 주문 조회는 어떻게 하나요", "배송지 변경이 가능할까요", "환불 처리 기간이 궁금해요",
    ]
    board_bodies = [
        "주문한 지 벌써 5일이 지났는데 아직 발송 전이라고 나와요. 확인 부탁드립니다.",
        "실수로 다른 상품을 주문했어요. 아직 배송 전인데 취소 가능할까요?",
        "리뷰 작성하면 적립되는 포인트가 이번엔 안 들어온 것 같아요.",
        "사이즈가 안 맞아서 교환하고 싶은데 절차가 궁금합니다.",
        "더 이상 서비스를 이용하지 않을 것 같아 탈퇴를 원합니다. 절차 안내 부탁드려요.",
        "쿠폰 코드를 입력했는데 할인이 적용되지 않고 그대로 나와요.",
        "결제 진행 중에 오류 화면이 떠서 결제가 완료됐는지 모르겠어요.",
        "품절 상품 재입고 알림 신청은 어디서 하나요?",
        "회사 지출 처리를 위해 영수증이 필요합니다. 발급 방법 알려주세요.",
        "회원가입 없이 주문했는데 주문 조회는 어떻게 하면 되나요?",
        "주문 후에 배송지를 다른 곳으로 바꾸고 싶습니다.",
        "환불 신청했는데 보통 며칠 정도 걸리나요?",
    ]
    for i in range(14):
        uid = random.choice(user_ids)
        title = random.choice(board_titles)
        body = random.choice(board_bodies)
        category = random.choice(board_categories)
        secret = 1 if random.random() < 0.35 else 0
        answered = random.random() < 0.4
        answer = "안녕하세요 고객님, 문의 주셔서 감사합니다. 순차적으로 확인 후 답변드리겠습니다." if answered else ""
        cur.execute(
            "INSERT INTO board_qna (user_id, category, title, content, is_secret, answer, answered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, category, title, body, secret, answer, "answered" if answered else ""),
        )
        board_post_id = cur.lastrowid

        # 비밀글이 아니면 다른 회원들의 댓글도 몇 개 채워둔다.
        if not secret:
            comment_pool = [
                "저도 똑같은 문제 겪었어요!", "혹시 해결되셨나요?", "저는 답변 빨리 받았어요.",
                "동일한 문의 남깁니다, 답변 기다려요.", "고객센터 전화도 해보세요.",
            ]
            for _ in range(random.randint(0, 3)):
                cur.execute(
                    "INSERT INTO board_qna_comments (post_id, user_id, content) VALUES (?, ?, ?)",
                    (board_post_id, random.choice(user_ids), random.choice(comment_pool)),
                )

    # --- 쿠폰 ---
    coupons = [
        ("WELCOME10", 10, "신규 회원 10% 할인"),
        ("SUMMER20", 20, "여름 시즌 20% 할인"),
        ("VIP30", 30, "VIP 회원 전용 30% 할인"),
    ]
    for code, pct, desc in coupons:
        cur.execute(
            "INSERT OR IGNORE INTO coupons (code, discount_percent, description) VALUES (?, ?, ?)",
            (code, pct, desc),
        )

    # --- 과거 주문 몇 건 ---
    for _ in range(20):
        uid = random.choice(user_ids)
        items = random.sample(product_ids, k=random.randint(1, 3))
        total = 0
        order_items = []
        for pid in items:
            cur.execute("SELECT name, price FROM products WHERE id = ?", (pid,))
            row = cur.fetchone()
            qty = random.randint(1, 2)
            total += row["price"] * qty
            order_items.append((pid, row["name"], row["price"], qty))
        cur.execute(
            "INSERT INTO orders (user_id, total_price, discount, status, address) VALUES (?, ?, 0, ?, ?)",
            (uid, total, random.choice(["결제완료", "배송중", "배송완료"]), fake.address()),
        )
        order_id = cur.lastrowid
        for pid, name, price, qty in order_items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, price, quantity) "
                "VALUES (?, ?, ?, ?, ?)",
                (order_id, pid, name, price, qty),
            )

    notice_data = [
        ("신규 회원 웰컴 쿠폰 안내", "신규 가입하신 모든 회원님께 10% 할인 쿠폰을 드립니다. 마이페이지에서 확인하세요."),
        ("설 연휴 배송 일정 안내", "설 연휴 기간 배송이 지연될 수 있습니다. 자세한 일정은 첨부파일을 참고해주세요."),
        ("개인정보 처리방침 개정 안내", "개인정보 처리방침이 일부 개정되었습니다. 첨부된 문서를 확인해주시기 바랍니다."),
        ("시스템 정기 점검 안내", "매월 첫째 주 일요일 새벽 2시~4시 시스템 점검이 진행됩니다."),
    ]
    for title, content in notice_data:
        cur.execute(
            "INSERT INTO notices (user_id, title, content, attachment) VALUES (?, ?, ?, '')",
            (admin_id, title, content),
        )

    conn.commit()
    conn.close()
    print(f"[seed] 완료: 유저 {len(user_ids)}명, 상품 {len(product_ids)}개 (admin 계정: admin / admin1234)")


if __name__ == "__main__":
    seed()

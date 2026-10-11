-- ============================================================================
--  담다몰 (damdamall) 데이터베이스 스키마  [SQLite]
-- ----------------------------------------------------------------------------
--  ※ 참고: 이 애플리케이션은 최초 실행(python app.py) 시 db.py 가 아래 테이블을
--     자동으로 생성하고, seed.py 가 더미 데이터를 채워줍니다.
--     따라서 이 파일을 수동으로 실행하지 않아도 동작합니다.
--
--  이 schema.sql 은 "DB에 어떤 테이블과 컬럼이 있는지" 한눈에 파악하거나,
--  수동으로 DB를 만들어보고 싶을 때 참고용으로 제공됩니다.
--
--  수동 생성 예시:
--     sqlite3 damdamall.db < schema.sql
-- ============================================================================

-- ─── 회원 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,              -- 로그인 아이디
    email         TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,                     -- 비밀번호 해시
    nickname      TEXT    NOT NULL,                     -- 표시 이름
    bio           TEXT    DEFAULT '',                   -- 자기소개
    address       TEXT    DEFAULT '',                   -- 기본 주소
    avatar_path   TEXT    DEFAULT '',                   -- 프로필 사진 경로
    points        INTEGER DEFAULT 0,                    -- 보유 포인트
    is_admin      INTEGER DEFAULT 0,                    -- 관리자 여부(0/1)
    created_at    TEXT    DEFAULT (datetime('now'))
);

-- ─── 세션 (로그인 유지) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    sid        TEXT    PRIMARY KEY,                     -- 세션 ID (쿠키 값)
    user_id    INTEGER,                                 -- 로그인한 회원
    created_at TEXT    DEFAULT (datetime('now'))
);

-- ─── 비밀번호 재설정 토큰 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    created_at TEXT    DEFAULT (datetime('now')),
    used       INTEGER DEFAULT 0                        -- 사용 여부(0/1)
);

-- ─── 상품 카테고리 ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    UNIQUE NOT NULL
);

-- ─── 상품 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL,
    price       INTEGER NOT NULL,                       -- 가격(원)
    category    TEXT    NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0,             -- 재고 수량
    color       TEXT    DEFAULT '#5b7fff',              -- 썸네일 색상
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ─── 배송지 ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS addresses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    recipient  TEXT    NOT NULL,                        -- 받는 사람
    phone      TEXT    NOT NULL,
    address    TEXT    NOT NULL,
    is_default INTEGER DEFAULT 0                        -- 기본 배송지 여부(0/1)
);

-- ─── 상품 리뷰 ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    rating     INTEGER NOT NULL,                        -- 별점
    content    TEXT    NOT NULL,
    reported   INTEGER DEFAULT 0,                       -- 신고 여부(0/1)
    created_at TEXT    DEFAULT (datetime('now'))
);

-- ─── 공지사항 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,                        -- 작성자(관리자)
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    attachment TEXT    DEFAULT '',                      -- 첨부파일명
    created_at TEXT    DEFAULT (datetime('now'))
);

-- ─── Q&A 게시판 ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS board_qna (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    category    TEXT    DEFAULT '기타',
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    is_secret   INTEGER DEFAULT 0,                      -- 비밀글 여부(0/1)
    reported    INTEGER DEFAULT 0,
    answer      TEXT    DEFAULT '',                     -- 관리자 답변
    answered_at TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ─── Q&A 댓글 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS board_qna_comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,                        -- 원글 ID
    user_id    INTEGER NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now'))
);

-- ─── 쿠폰 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coupons (
    code             TEXT    PRIMARY KEY,               -- 쿠폰 코드
    discount_percent INTEGER NOT NULL,                  -- 할인율(%)
    description      TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS coupon_usage (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code    TEXT    NOT NULL,
    used_at TEXT    DEFAULT (datetime('now'))
);

-- ─── 주문 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    total_price    INTEGER NOT NULL,                    -- 최종 결제 금액
    discount       INTEGER DEFAULT 0,
    status         TEXT    DEFAULT '결제완료',
    payment_method TEXT    DEFAULT '가짜페이',           -- 목업 결제수단
    address        TEXT    DEFAULT '',
    invoice_file   TEXT    DEFAULT '',                  -- 거래명세서 파일명
    created_at     TEXT    DEFAULT (datetime('now'))
);

-- ─── 주문 상세 (주문 1건에 담긴 상품들) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL,                      -- 주문 ID
    product_id   INTEGER NOT NULL,
    product_name TEXT    NOT NULL,
    price        INTEGER NOT NULL,
    quantity     INTEGER NOT NULL
);

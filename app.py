"""
담다몰 - 쇼핑몰 웹 애플리케이션
==========================================
※ 반드시 localhost / 격리된 네트워크에서만 구동하세요.
"""
import hashlib
import os
import random
import secrets
import string
import time
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for, render_template,
    flash, g, abort, Response, send_from_directory, render_template_string
)
from werkzeug.utils import secure_filename

from db import get_db, init_db
from seed import seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

app = Flask(__name__)
app.config["SECRET_KEY"] = "ooshop-dev-secret-key-2024"
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

# Flask 기본 세션은 로그인 유지용 일부 기능에 사용하고,
# 로그인 판별은 커스텀 sid 세션 테이블을 사용한다.
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_HTTPONLY"] = True

_sid_counter = {"n": 1000}


def _next_sid():
    _sid_counter["n"] += 1
    return f"sess_{_sid_counter['n']:06d}"


@app.before_request
def load_session_and_user():
    g.user = None

    fixed_sid = request.args.get("sid")
    resp_sid_to_set = None
    if fixed_sid:
        sid = fixed_sid
        resp_sid_to_set = fixed_sid
    else:
        sid = request.cookies.get("sid")

    g.incoming_sid = sid
    g.force_set_sid = resp_sid_to_set

    if sid:
        conn = get_db()
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.sid = ?",
            (sid,),
        ).fetchone()
        conn.close()
        if row:
            g.user = row


@app.after_request
def maybe_set_sid_cookie(resp):
    if getattr(g, "force_set_sid", None):
        resp.set_cookie("sid", g.force_set_sid, httponly=True, samesite="Strict")
    return resp


@app.context_processor
def inject_globals():
    cart = session.get("cart", {})
    cart_count = sum(cart.values()) if cart else 0
    return dict(current_user=g.get("user"), cart_count=cart_count, brand_name="담다몰")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("로그인이 필요합니다.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def md5(pw):
    return hashlib.md5(pw.encode()).hexdigest()


# ------------------------------------------------------------------
# 정적 업로드 파일 제공 (아바타 등 일반 접근용 - 프리뷰/다운로드는 별도 라우트)
# ------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/img/<seed_key>")
def placeholder_img(seed_key):
    """실제 상품 이미지 대신 브랜드 컬러 기반 플레이스홀더 SVG를 즉석에서 생성."""
    conn = get_db()
    color = "#5b7fff"
    label = seed_key
    if seed_key.isdigit():
        row = conn.execute("SELECT name, color FROM products WHERE id = ?", (seed_key,)).fetchone()
        if row:
            color = row["color"]
            label = row["name"][:10]
    conn.close()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480">
        <rect width="100%" height="100%" fill="{color}"/>
        <text x="50%" y="50%" font-size="28" fill="white" text-anchor="middle"
              dominant-baseline="middle" font-family="sans-serif">{label}</text>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml")


# ------------------------------------------------------------------
# 인증
# ------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        pw = request.form.get("password", "")
        nickname = request.form.get("nickname", "").strip() or username

        if not username or not email or not pw:
            flash("모든 필드를 입력해주세요.", "error")
            return render_template("register.html")

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, nickname) VALUES (?, ?, ?, ?)",
                (username, email, md5(pw), nickname),
            )
            conn.commit()
        except Exception:
            flash("이미 존재하는 아이디입니다.", "error")
            conn.close()
            return render_template("register.html")
        conn.close()
        flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pw = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password_hash = ?",
            (username, md5(pw)),
        ).fetchone()

        if not user:
            conn.close()
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return render_template("login.html")

        sid = g.incoming_sid or _next_sid()
        conn.execute("INSERT OR REPLACE INTO sessions (sid, user_id) VALUES (?, ?)", (sid, user["id"]))
        conn.commit()
        conn.close()

        g.force_set_sid = sid
        flash(f"{user['nickname']}님 환영합니다!", "success")
        nxt = request.args.get("next") or request.form.get("next")
        return redirect(nxt or url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    sid = request.cookies.get("sid")
    if sid:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
        conn.commit()
        conn.close()
    resp = redirect(url_for("index"))
    resp.delete_cookie("sid")
    flash("로그아웃 되었습니다.", "success")
    return resp


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user:
            cur = conn.execute("INSERT INTO reset_tokens (user_id) VALUES (?)", (user["id"],))
            conn.commit()
            token_id = cur.lastrowid
            conn.close()
            reset_link = url_for("reset_password", token_id=token_id, _external=True)
            flash(f"비밀번호 재설정 링크가 이메일로 전송되었습니다. ({reset_link})", "success")
            return redirect(url_for("login"))
        conn.close()
        flash("해당 아이디를 찾을 수 없습니다.", "error")
    return render_template("forgot_password.html")


@app.route("/reset-password/<int:token_id>", methods=["GET", "POST"])
def reset_password(token_id):
    conn = get_db()
    token = conn.execute(
        "SELECT * FROM reset_tokens WHERE id = ? AND used = 0", (token_id,)
    ).fetchone()
    if not token:
        conn.close()
        flash("유효하지 않거나 만료된 링크입니다.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_pw = request.form.get("password", "")
        if len(new_pw) < 4:
            flash("비밀번호는 4자 이상이어야 합니다.", "error")
            return render_template("reset_password.html", token_id=token_id)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (md5(new_pw), token["user_id"]))
        conn.execute("UPDATE reset_tokens SET used = 1 WHERE id = ?", (token_id,))
        conn.commit()
        conn.close()
        flash("비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요.", "success")
        return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html", token_id=token_id)


# ------------------------------------------------------------------
# ------------------------------------------------------------------
@app.route("/redirect")
def open_redirect():
    to = request.args.get("to", "/")
    return redirect(to)


# ------------------------------------------------------------------
# 계정 / 프로필 / 배송지 / 아바타
# ------------------------------------------------------------------
@app.route("/account")
@login_required
def account():
    conn = get_db()
    addresses = conn.execute("SELECT * FROM addresses WHERE user_id = ?", (g.user["id"],)).fetchall()
    conn.close()
    return render_template("account.html", addresses=addresses)


@app.route("/account/update", methods=["POST"])
@login_required
def account_update():
    target_id = request.form.get("user_id", g.user["id"])
    nickname = request.form.get("nickname", "").strip()
    bio = request.form.get("bio", "").strip()
    address = request.form.get("address", "").strip()

    conn = get_db()
    conn.execute(
        "UPDATE users SET nickname = ?, bio = ?, address = ? WHERE id = ?",
        (nickname, bio, address, target_id),
    )
    conn.commit()
    conn.close()
    flash("프로필이 수정되었습니다.", "success")
    return redirect(url_for("account"))


@app.route("/account/change-password", methods=["POST"])
@login_required
def change_password():
    new_pw = request.form.get("new_password", "")
    if len(new_pw) < 4:
        flash("비밀번호는 4자 이상이어야 합니다.", "error")
        return redirect(url_for("account"))
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (md5(new_pw), g.user["id"]))
    conn.commit()
    conn.close()
    flash("비밀번호가 변경되었습니다.", "success")
    return redirect(url_for("account"))


ALLOWED_AVATAR_EXT_CHECKED_ONLY_CLIENT_SIDE = {"png", "jpg", "jpeg", "gif"}


@app.route("/account/avatar", methods=["POST"])
@login_required
def upload_avatar():
    file = request.files.get("avatar")
    if not file or file.filename == "":
        flash("파일을 선택해주세요.", "error")
        return redirect(url_for("account"))

    filename = file.filename
    save_dir = os.path.join(UPLOAD_DIR, "avatars")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    file.save(save_path)

    rel_path = f"avatars/{filename}"
    conn = get_db()
    conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (rel_path, g.user["id"]))
    conn.commit()
    conn.close()
    flash("프로필 사진이 변경되었습니다.", "success")
    return redirect(url_for("account"))


@app.route("/account/addresses/add", methods=["POST"])
@login_required
def add_address():
    recipient = request.form.get("recipient", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    is_default = 1 if request.form.get("is_default") else 0
    conn = get_db()
    if is_default:
        conn.execute("UPDATE addresses SET is_default = 0 WHERE user_id = ?", (g.user["id"],))
    conn.execute(
        "INSERT INTO addresses (user_id, recipient, phone, address, is_default) VALUES (?, ?, ?, ?, ?)",
        (g.user["id"], recipient, phone, address, is_default),
    )
    conn.commit()
    conn.close()
    flash("배송지가 추가되었습니다.", "success")
    return redirect(url_for("account"))


@app.route("/account/addresses/<int:addr_id>")
@login_required
def view_address(addr_id):
    conn = get_db()
    addr = conn.execute("SELECT * FROM addresses WHERE id = ?", (addr_id,)).fetchone()
    conn.close()
    if not addr:
        abort(404)
    return render_template("address_detail.html", addr=addr)


@app.route("/account/addresses/<int:addr_id>/delete", methods=["POST"])
@login_required
def delete_address(addr_id):
    conn = get_db()
    conn.execute("DELETE FROM addresses WHERE id = ?", (addr_id,))
    conn.commit()
    conn.close()
    flash("배송지가 삭제되었습니다.", "success")
    return redirect(url_for("account"))


# ------------------------------------------------------------------
# ------------------------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    products = conn.execute(
        "SELECT * FROM products ORDER BY RANDOM() LIMIT 8"
    ).fetchall()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template("index.html", products=products, categories=categories)


@app.route("/products")
def products_list():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db()

    base_sql = "SELECT id, name, description, price, category, stock, color FROM products WHERE 1=1 "
    if q:
        base_sql += f" AND (name LIKE '%{q}%' OR description LIKE '%{q}%') "
    if category:
        base_sql += f" AND category = '{category}' "
    base_sql += " ORDER BY id DESC"

    error_message = None
    try:
        products = conn.execute(base_sql).fetchall()
    except Exception as e:
        products = []
        error_message = f"쿼리 실행 중 오류가 발생했습니다: {e}"

    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template(
        "products.html", products=products, categories=categories,
        q=q, selected_category=category, error_message=error_message,
    )


@app.route("/products/<int:pid>")
def product_detail(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not product:
        conn.close()
        abort(404)
    reviews = conn.execute(
        "SELECT r.*, u.nickname FROM reviews r JOIN users u ON u.id = r.user_id "
        "WHERE r.product_id = ? ORDER BY r.created_at DESC", (pid,),
    ).fetchall()
    conn.close()
    return render_template("product_detail.html", product=product, reviews=reviews)


# ------------------------------------------------------------------
# ------------------------------------------------------------------
@app.route("/products/<int:pid>/reviews", methods=["POST"])
@login_required
def add_review(pid):
    content = request.form.get("content", "").strip()
    rating = int(request.form.get("rating", 5) or 5)
    if not content:
        flash("리뷰 내용을 입력해주세요.", "error")
        return redirect(url_for("product_detail", pid=pid))

    conn = get_db()
    conn.execute(
        "INSERT INTO reviews (product_id, user_id, rating, content) VALUES (?, ?, ?, ?)",
        (pid, g.user["id"], rating, content),
    )
    conn.commit()
    conn.close()
    flash("리뷰가 등록되었습니다.", "success")
    return redirect(url_for("product_detail", pid=pid))


@app.route("/reviews/<int:rid>/delete", methods=["POST"])
@login_required
def delete_review(rid):
    conn = get_db()
    review = conn.execute("SELECT product_id FROM reviews WHERE id = ?", (rid,)).fetchone()
    conn.execute("DELETE FROM reviews WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    flash("리뷰가 삭제되었습니다.", "success")
    return redirect(url_for("product_detail", pid=review["product_id"] if review else 0))


@app.route("/reviews/<int:rid>/report", methods=["POST"])
@login_required
def report_review(rid):
    conn = get_db()
    review = conn.execute("SELECT product_id FROM reviews WHERE id = ?", (rid,)).fetchone()
    conn.execute("UPDATE reviews SET reported = 1 WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    flash("신고가 접수되었습니다. 운영팀이 확인 후 조치할 예정입니다.", "success")
    return redirect(url_for("product_detail", pid=review["product_id"] if review else 0))


# ------------------------------------------------------------------
# Q&A 게시판 (특정 상품과 무관한 고객센터 문의 게시판)
# ------------------------------------------------------------------
BOARD_QNA_CATEGORIES = ["배송문의", "상품문의", "환불/교환", "회원/주문", "기타"]


@app.route("/board/qna")
def board_qna_list():
    conn = get_db()
    posts = conn.execute(
        "SELECT b.*, u.nickname FROM board_qna b JOIN users u ON u.id = b.user_id "
        "ORDER BY b.created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("board_qna_list.html", posts=posts, categories=BOARD_QNA_CATEGORIES)


@app.route("/board/qna/write", methods=["GET", "POST"])
@login_required
def board_qna_write():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category", "기타")
        is_secret = 1 if request.form.get("is_secret") else 0
        if not title or not content:
            flash("제목과 내용을 입력해주세요.", "error")
            return render_template("board_qna_write.html", categories=BOARD_QNA_CATEGORIES)

        conn = get_db()
        cur = conn.execute(
            "INSERT INTO board_qna (user_id, category, title, content, is_secret) VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], category, title, content, is_secret),
        )
        conn.commit()
        post_id = cur.lastrowid
        conn.close()
        flash("문의가 등록되었습니다.", "success")
        return redirect(url_for("board_qna_detail", post_id=post_id))

    return render_template("board_qna_write.html", categories=BOARD_QNA_CATEGORIES)


@app.route("/board/qna/<int:post_id>")
def board_qna_detail(post_id):
    conn = get_db()
    post = conn.execute(
        "SELECT b.*, u.nickname, u.id AS author_id FROM board_qna b JOIN users u ON u.id = b.user_id "
        "WHERE b.id = ?", (post_id,),
    ).fetchone()
    if not post:
        conn.close()
        abort(404)

    if post["is_secret"] and not g.user:
        conn.close()
        abort(403)

    comments = conn.execute(
        "SELECT c.*, u.nickname FROM board_qna_comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.post_id = ? ORDER BY c.created_at ASC", (post_id,),
    ).fetchall()
    conn.close()

    return render_template("board_qna_detail.html", post=post, comments=comments)


@app.route("/board/qna/<int:post_id>/answer", methods=["POST"])
def board_qna_answer(post_id):
    answer = request.form.get("answer", "").strip()
    conn = get_db()
    conn.execute(
        "UPDATE board_qna SET answer = ?, answered_at = datetime('now') WHERE id = ?",
        (answer, post_id),
    )
    conn.commit()
    conn.close()
    flash("답변이 등록되었습니다.", "success")
    return redirect(url_for("board_qna_detail", post_id=post_id))


@app.route("/board/qna/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def board_qna_edit(post_id):
    conn = get_db()
    post = conn.execute("SELECT * FROM board_qna WHERE id = ?", (post_id,)).fetchone()
    if not post:
        conn.close()
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category", "기타")
        is_secret = 1 if request.form.get("is_secret") else 0
        if not title or not content:
            conn.close()
            flash("제목과 내용을 입력해주세요.", "error")
            return render_template("board_qna_edit.html", post=post, categories=BOARD_QNA_CATEGORIES)

        conn.execute(
            "UPDATE board_qna SET title = ?, content = ?, category = ?, is_secret = ? WHERE id = ?",
            (title, content, category, is_secret, post_id),
        )
        conn.commit()
        conn.close()
        flash("게시글이 수정되었습니다.", "success")
        return redirect(url_for("board_qna_detail", post_id=post_id))

    conn.close()
    return render_template("board_qna_edit.html", post=post, categories=BOARD_QNA_CATEGORIES)


@app.route("/board/qna/<int:post_id>/delete", methods=["POST"])
@login_required
def board_qna_delete(post_id):
    conn = get_db()
    conn.execute("DELETE FROM board_qna WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    flash("글이 삭제되었습니다.", "success")
    return redirect(url_for("board_qna_list"))


@app.route("/board/qna/<int:post_id>/report", methods=["POST"])
@login_required
def board_qna_report(post_id):
    conn = get_db()
    conn.execute("UPDATE board_qna SET reported = 1 WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    flash("신고가 접수되었습니다.", "success")
    return redirect(url_for("board_qna_detail", post_id=post_id))


@app.route("/notice")
def notice_list():
    conn = get_db()
    notices = conn.execute(
        "SELECT n.*, u.nickname FROM notices n JOIN users u ON u.id = n.user_id "
        "ORDER BY n.created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("notice_list.html", notices=notices)


@app.route("/notice/<int:notice_id>")
def notice_detail(notice_id):
    conn = get_db()
    notice = conn.execute(
        "SELECT n.*, u.nickname FROM notices n JOIN users u ON u.id = n.user_id WHERE n.id = ?",
        (notice_id,),
    ).fetchone()
    conn.close()
    if not notice:
        abort(404)
    return render_template("notice_detail.html", notice=notice)


@app.route("/notice/write", methods=["GET", "POST"])
@login_required
def notice_write():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        attachment = ""

        file = request.files.get("attachment")
        if file and file.filename:
            save_dir = os.path.join(UPLOAD_DIR, "notices")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, file.filename)
            file.save(save_path)
            attachment = file.filename

        conn = get_db()
        cur = conn.execute(
            "INSERT INTO notices (user_id, title, content, attachment) VALUES (?, ?, ?, ?)",
            (g.user["id"], title, content, attachment),
        )
        notice_id = cur.lastrowid
        conn.commit()
        conn.close()
        flash("공지사항이 등록되었습니다.", "success")
        return redirect(url_for("notice_detail", notice_id=notice_id))

    return render_template("notice_write.html")


@app.route("/notice/download")
def notice_download():
    filename = request.args.get("file", "")
    if not filename:
        abort(404)

    base = os.path.join(UPLOAD_DIR, "notices")
    target = os.path.join(base, filename)

    with open(target, "rb") as f:
        data = f.read()
    return Response(
        data, mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(filename)}"},
    )


@app.route("/board/qna/<int:post_id>/comment", methods=["POST"])
@login_required
def board_qna_comment(post_id):
    conn = get_db()
    post = conn.execute("SELECT is_secret FROM board_qna WHERE id = ?", (post_id,)).fetchone()
    if not post:
        conn.close()
        abort(404)

    # 비밀글에는 댓글을 열어두지 않는다 (요청사항: 비밀글이 아닌 글만 회원이 댓글 가능).
    if post["is_secret"]:
        conn.close()
        flash("비밀글에는 댓글을 남길 수 없습니다.", "error")
        return redirect(url_for("board_qna_detail", post_id=post_id))

    content = request.form.get("content", "").strip()
    if not content:
        conn.close()
        flash("댓글 내용을 입력해주세요.", "error")
        return redirect(url_for("board_qna_detail", post_id=post_id))

    conn.execute(
        "INSERT INTO board_qna_comments (post_id, user_id, content) VALUES (?, ?, ?)",
        (post_id, g.user["id"], content),
    )
    conn.commit()
    conn.close()
    flash("댓글이 등록되었습니다.", "success")
    return redirect(url_for("board_qna_detail", post_id=post_id))


# ------------------------------------------------------------------
# ------------------------------------------------------------------
def _cart_items(conn):
    cart = session.get("cart", {})
    items = []
    subtotal = 0
    for pid_str, qty in cart.items():
        product = conn.execute("SELECT * FROM products WHERE id = ?", (int(pid_str),)).fetchone()
        if not product:
            continue
        line_total = product["price"] * qty
        subtotal += line_total
        items.append({"product": product, "qty": qty, "line_total": line_total})
    return items, subtotal


@app.route("/cart")
def cart_view():
    conn = get_db()
    items, subtotal = _cart_items(conn)
    conn.close()
    coupons = session.get("coupons", [])
    discount_pct = sum(c["discount_percent"] for c in coupons)
    discount_amount = subtotal * discount_pct // 100
    total = max(subtotal - discount_amount, 0)
    return render_template(
        "cart.html", items=items, subtotal=subtotal, coupons=coupons,
        discount_amount=discount_amount, total=total,
    )


@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = request.form.get("product_id")
    qty = int(request.form.get("quantity", 1) or 1)
    cart = session.get("cart", {})
    cart[pid] = cart.get(pid, 0) + max(qty, 1)
    session["cart"] = cart
    flash("장바구니에 담았습니다.", "success")
    return redirect(request.referrer or url_for("products_list"))


@app.route("/cart/update", methods=["POST"])
def cart_update():
    pid = request.form.get("product_id")
    qty = int(request.form.get("quantity", 1) or 1)
    cart = session.get("cart", {})
    if qty <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    pid = request.form.get("product_id")
    cart = session.get("cart", {})
    cart.pop(pid, None)
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/apply-coupon", methods=["POST"])
def apply_coupon():
    code = request.form.get("code", "").strip().upper()
    conn = get_db()
    coupon = conn.execute("SELECT * FROM coupons WHERE code = ?", (code,)).fetchone()
    conn.close()
    if not coupon:
        flash("존재하지 않는 쿠폰 코드입니다.", "error")
        return redirect(url_for("cart_view"))

    coupons = session.get("coupons", [])
    coupons.append(dict(coupon))
    session["coupons"] = coupons
    flash(f"쿠폰 '{code}' 이(가) 적용되었습니다. ({coupon['discount_percent']}% 할인)", "success")
    return redirect(url_for("cart_view"))


@app.route("/cart/remove-coupon", methods=["POST"])
def remove_coupons():
    session["coupons"] = []
    return redirect(url_for("cart_view"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    conn = get_db()
    items, subtotal = _cart_items(conn)
    if not items:
        conn.close()
        flash("장바구니가 비어있습니다.", "error")
        return redirect(url_for("products_list"))

    coupons = session.get("coupons", [])
    discount_pct = sum(c["discount_percent"] for c in coupons)
    server_discount = subtotal * discount_pct // 100
    server_total = max(subtotal - server_discount, 0)

    if request.method == "POST":
        final_total = int(request.form.get("final_total", server_total))
        final_discount = int(request.form.get("final_discount", server_discount))
        address_text = request.form.get("address", "").strip()
        payment_method = "가짜페이"

        for item in items:
            pid = item["product"]["id"]
            qty = item["qty"]
            stock_row = conn.execute("SELECT stock FROM products WHERE id = ?", (pid,)).fetchone()
            current_stock = stock_row["stock"] if stock_row else 0
            if current_stock < qty:
                flash(f"{item['product']['name']} 재고가 부족합니다.", "error")
                conn.close()
                return redirect(url_for("cart_view"))
            time.sleep(0.3)
            conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, pid))
            conn.commit()

        cur = conn.execute(
            "INSERT INTO orders (user_id, total_price, discount, status, payment_method, address) "
            "VALUES (?, ?, ?, '결제완료', ?, ?)",
            (g.user["id"], final_total, final_discount, payment_method, address_text),
        )
        order_id = cur.lastrowid
        for item in items:
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, price, quantity) "
                "VALUES (?, ?, ?, ?, ?)",
                (order_id, item["product"]["id"], item["product"]["name"], item["product"]["price"], item["qty"]),
            )

        misc_dir = os.path.join(UPLOAD_DIR, "misc")
        os.makedirs(misc_dir, exist_ok=True)
        invoice_filename = f"invoice_{order_id}.txt"
        lines = [f"{app.config.get('BRAND_NAME', '담다몰')} 거래명세서", f"주문번호: {order_id}",
                 f"주문자: {g.user['nickname']} ({g.user['email']})", f"배송지: {address_text}",
                 f"결제수단: {payment_method}", "-" * 30]
        for item in items:
            lines.append(f"{item['product']['name']} x {item['qty']} = {item['line_total']:,}원")
        lines += ["-" * 30, f"할인: -{final_discount:,}원", f"총 결제금액: {final_total:,}원"]
        with open(os.path.join(misc_dir, invoice_filename), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        conn.execute("UPDATE orders SET invoice_file = ? WHERE id = ?", (invoice_filename, order_id))

        conn.commit()
        conn.close()

        session["cart"] = {}
        session["coupons"] = []
        flash("결제가 완료되었습니다!", "success")
        return redirect(url_for("order_detail", oid=order_id))

    conn.close()
    default_address = g.user["address"] or ""
    return render_template(
        "checkout.html", items=items, subtotal=subtotal, discount_amount=server_discount,
        total=server_total, default_address=default_address,
    )


@app.route("/orders")
@login_required
def order_list():
    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (g.user["id"],)
    ).fetchall()
    conn.close()
    return render_template("orders.html", orders=orders)


@app.route("/orders/<int:oid>")
@login_required
def order_detail(oid):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        abort(404)
    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (oid,)).fetchall()
    buyer = conn.execute("SELECT nickname, email FROM users WHERE id = ?", (order["user_id"],)).fetchone()
    conn.close()
    return render_template("order_detail.html", order=order, items=items, buyer=buyer)


# ------------------------------------------------------------------
# ------------------------------------------------------------------
@app.route("/preview")
@login_required
def preview_file():
    filename = request.args.get("file", "")
    path = os.path.join(UPLOAD_DIR, "avatars", filename)
    if not os.path.isfile(path):
        abort(404)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        abort(400)

    if ext in ("html", "htm"):
        return render_template_string(content)

    return Response(content, mimetype="text/plain")


@app.route("/download")
@login_required
def download_file():
    filename = request.args.get("file", "")
    if not filename:
        abort(404)

    base = os.path.join(UPLOAD_DIR, "misc")
    target = os.path.join(base, filename)

    if not os.path.isfile(target):
        abort(404)

    with open(target, "rb") as f:
        data = f.read()
    return Response(
        data, mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(filename)}"},
    )


# ------------------------------------------------------------------
# 관리자 페이지
# ------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    stats = {
        "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "products": conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
        "orders": conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "reported_reviews": conn.execute("SELECT COUNT(*) c FROM reviews WHERE reported = 1").fetchone()["c"],
    }
    conn.close()
    return render_template("admin/dashboard.html", stats=stats)


@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/<int:uid>/points", methods=["POST"])
def admin_adjust_points(uid):
    amount = int(request.form.get("amount", 0) or 0)
    conn = get_db()
    conn.execute("UPDATE users SET points = points + ? WHERE id = ?", (amount, uid))
    conn.commit()
    conn.close()
    flash("포인트가 조정되었습니다.", "success")
    return redirect(request.referrer or url_for("account"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db()
    orders = conn.execute(
        "SELECT o.*, u.nickname FROM orders o JOIN users u ON u.id = o.user_id ORDER BY o.created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/reported")
@admin_required
def admin_reported():
    conn = get_db()
    reported_reviews = conn.execute(
        "SELECT r.*, u.nickname, p.name AS product_name FROM reviews r "
        "JOIN users u ON u.id = r.user_id JOIN products p ON p.id = r.product_id "
        "WHERE r.reported = 1 ORDER BY r.created_at DESC"
    ).fetchall()
    board_flagged = conn.execute(
        "SELECT b.*, u.nickname FROM board_qna b JOIN users u ON u.id = b.user_id "
        "WHERE b.reported = 1 OR b.content LIKE '%문의%' OR b.content LIKE '%환불%' "
        "ORDER BY b.created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin/reported.html", reviews=reported_reviews, board_list=board_flagged)


@app.route("/admin/products")
@admin_required
def admin_products():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("admin/products.html", products=products)


@app.route("/admin/products/add", methods=["GET", "POST"])
def admin_add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = int(request.form.get("price", 0) or 0)
        category = request.form.get("category", "").strip()
        stock = int(request.form.get("stock", 0) or 0)
        conn = get_db()
        conn.execute(
            "INSERT INTO products (name, description, price, category, stock) VALUES (?, ?, ?, ?, ?)",
            (name, description, price, category, stock),
        )
        conn.commit()
        conn.close()
        flash("상품이 등록되었습니다.", "success")
        return redirect(url_for("admin_products"))

    conn = get_db()
    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template("admin/product_form.html", categories=categories, product=None)


@app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
def admin_edit_product(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not product:
        conn.close()
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = int(request.form.get("price", 0) or 0)
        category = request.form.get("category", "").strip()
        stock = int(request.form.get("stock", 0) or 0)
        conn.execute(
            "UPDATE products SET name=?, description=?, price=?, category=?, stock=? WHERE id=?",
            (name, description, price, category, stock, pid),
        )
        conn.commit()
        conn.close()
        flash("상품이 수정되었습니다.", "success")
        return redirect(url_for("admin_products"))

    categories = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template("admin/product_form.html", categories=categories, product=product)


@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
def admin_delete_product(pid):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    flash("상품이 삭제되었습니다.", "success")
    return redirect(url_for("admin_products"))


@app.route("/admin/products/<int:pid>/stock", methods=["POST"])
def admin_adjust_stock(pid):
    new_stock = int(request.form.get("stock", 0) or 0)
    conn = get_db()
    conn.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, pid))
    conn.commit()
    conn.close()
    flash("재고가 수정되었습니다.", "success")
    return redirect(url_for("admin_products"))


@app.errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


if __name__ == "__main__":
    is_first_run = init_db()
    seed()

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not app.debug:
        pass
    from admin_bot import start_bot_thread
    start_bot_thread()

    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from functools import wraps
from os import getenv
from pathlib import Path

from flask import (
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class TeacherUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    join_code = db.Column(db.String(10), unique=True, nullable=False)
    time_limit = db.Column(db.Integer, default=15, nullable=False)
    questions = db.relationship(
        "Question",
        backref="quiz",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Question.id.asc()",
    )
    results = db.relationship(
        "QuizResult",
        backref="quiz",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="QuizResult.date_submitted.desc()",
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)

    def options(self) -> dict[str, str]:
        return {
            "A": self.option_a,
            "B": self.option_b,
            "C": self.option_c,
            "D": self.option_d,
        }


class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=True)
    student_name = db.Column(db.String(100), default="Thí sinh tự do")
    student_code = db.Column(db.String(30))
    quiz_title = db.Column(db.String(100))
    join_code = db.Column(db.String(10))
    score = db.Column(db.Float)
    correct_count = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    cheat_count = db.Column(db.Integer, default=0)
    date_submitted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


LEGACY_TEXT_FIXES = {
    "Kiem tra Tin hoc dai cuong": "Kiểm tra Tin học đại cương",
    "Don vi nho nhat cua thong tin la gi?": "Đơn vị nhỏ nhất của thông tin là gì?",
    "Phan cung may tinh goi la gi?": "Phần cứng máy tính gọi là gì?",
    "To hop phim dung de sao chep noi dung la gi?": "Tổ hợp phím dùng để sao chép nội dung là gì?",
    "Thi sinh tu do": "Thí sinh tự do",
}


def normalize_join_code(raw_value: str | None) -> str:
    source = (raw_value or "").strip().upper()
    return "".join(char for char in source if char.isalnum())[:10]


def generate_join_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(length))
        if not Quiz.query.filter_by(join_code=code).first():
            return code


def parse_time_limit(raw_value: object, default: int = 15) -> int:
    try:
        minutes = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(1, min(minutes, 180))


def parse_non_negative_int(raw_value: object, default: int = 0) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(0, value)


def normalize_person_name(raw_value: object, default: str = "Thí sinh tự do") -> str:
    value = " ".join(str(raw_value or "").strip().split())
    return (value or default)[:100]


def normalize_student_code(raw_value: object) -> str:
    return "".join(str(raw_value or "").strip().upper().split())[:30]


def normalize_database_uri(raw_value: str | None, fallback_uri: str) -> str:
    candidate = (raw_value or "").strip()
    if not candidate:
        return fallback_uri

    if candidate.startswith("postgres://"):
        return "postgresql+psycopg://" + candidate[len("postgres://") :]

    if candidate.startswith("postgresql://"):
        return "postgresql+psycopg://" + candidate[len("postgresql://") :]

    return candidate


def is_teacher_logged_in() -> bool:
    return bool(session.get("teacher_user_id"))


def is_student_logged_in() -> bool:
    return bool(session.get("student_name") and session.get("student_code"))


def clear_teacher_session() -> None:
    for key in ("teacher_user_id", "teacher_display_name", "teacher_username"):
        session.pop(key, None)


def clear_student_session() -> None:
    for key in ("student_name", "student_code"):
        session.pop(key, None)


def teacher_required(api: bool = False):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if is_teacher_logged_in():
                return func(*args, **kwargs)

            if api:
                return jsonify({"status": "error", "message": "Bạn cần đăng nhập giảng viên."}), 401

            return redirect(url_for("teacher_login", next=request.path))

        return wrapper

    return decorator


def student_required():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if is_student_logged_in():
                return func(*args, **kwargs)

            return redirect(url_for("student_login", next=request.path))

        return wrapper

    return decorator


def serialize_question_public(question: Question) -> dict[str, object]:
    return {
        "id": question.id,
        "content": question.content,
        "options": question.options(),
    }


def serialize_quiz_admin(quiz: Quiz) -> dict[str, object]:
    scores = [result.score for result in quiz.results if result.score is not None]
    average_score = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "id": quiz.id,
        "title": quiz.title,
        "join_code": quiz.join_code,
        "time_limit": quiz.time_limit,
        "question_count": len(quiz.questions),
        "attempt_count": len(quiz.results),
        "average_score": average_score,
        "questions": [
            {
                "id": question.id,
                "content": question.content,
                "option_a": question.option_a,
                "option_b": question.option_b,
                "option_c": question.option_c,
                "option_d": question.option_d,
                "correct_option": question.correct_option,
            }
            for question in quiz.questions
        ],
        "results": [
            {
                "student_name": result.student_name or "Thí sinh tự do",
                "student_code": result.student_code or "-",
                "score": result.score,
                "correct_count": result.correct_count,
                "total_questions": result.total_questions,
                "cheat_count": result.cheat_count,
                "submitted_at": result.date_submitted.strftime("%H:%M %d/%m/%Y")
                if result.date_submitted
                else "-",
            }
            for result in quiz.results
        ],
    }


def snapshot_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def get_snapshot_path() -> Path | None:
    raw_path = current_app.config.get("QUIZ_SNAPSHOT_PATH")
    return Path(raw_path) if raw_path else None


def save_snapshot() -> None:
    if current_app.config.get("QUIZ_STORAGE_MODE") != "snapshot-memory":
        return

    snapshot_path = get_snapshot_path()
    if not snapshot_path:
        return

    payload = {
        "teachers": [],
        "quizzes": [],
        "results": [],
    }

    for teacher in TeacherUser.query.order_by(TeacherUser.id.asc()).all():
        payload["teachers"].append(
            {
                "username": teacher.username,
                "password_hash": teacher.password_hash,
                "display_name": teacher.display_name,
            }
        )

    for quiz in Quiz.query.order_by(Quiz.id.asc()).all():
        payload["quizzes"].append(
            {
                "title": quiz.title,
                "join_code": quiz.join_code,
                "time_limit": quiz.time_limit,
                "questions": [
                    {
                        "content": question.content,
                        "option_a": question.option_a,
                        "option_b": question.option_b,
                        "option_c": question.option_c,
                        "option_d": question.option_d,
                        "correct_option": question.correct_option,
                    }
                    for question in quiz.questions
                ],
            }
        )

    for result in QuizResult.query.order_by(QuizResult.id.asc()).all():
        payload["results"].append(
            {
                "quiz_join_code": result.join_code,
                "student_name": result.student_name,
                "student_code": result.student_code,
                "quiz_title": result.quiz_title,
                "score": result.score,
                "correct_count": result.correct_count,
                "total_questions": result.total_questions,
                "cheat_count": result.cheat_count,
                "date_submitted": snapshot_datetime(result.date_submitted),
            }
        )

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_snapshot() -> bool:
    if current_app.config.get("QUIZ_STORAGE_MODE") != "snapshot-memory":
        return False

    snapshot_path = get_snapshot_path()
    if not snapshot_path or not snapshot_path.exists() or Quiz.query.first():
        return False

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    for teacher_data in payload.get("teachers", []):
        db.session.add(
            TeacherUser(
                username=teacher_data["username"],
                password_hash=teacher_data["password_hash"],
                display_name=teacher_data["display_name"],
            )
        )
    db.session.flush()

    quiz_map: dict[str, Quiz] = {}
    for quiz_data in payload.get("quizzes", []):
        quiz = Quiz(
            title=quiz_data["title"],
            join_code=quiz_data["join_code"],
            time_limit=parse_time_limit(quiz_data.get("time_limit"), default=15),
        )
        db.session.add(quiz)
        db.session.flush()
        quiz_map[quiz.join_code] = quiz

        for question_data in quiz_data.get("questions", []):
            db.session.add(
                Question(
                    quiz_id=quiz.id,
                    content=question_data["content"],
                    option_a=question_data["option_a"],
                    option_b=question_data["option_b"],
                    option_c=question_data["option_c"],
                    option_d=question_data["option_d"],
                    correct_option=question_data["correct_option"],
                )
            )

    for result_data in payload.get("results", []):
        quiz = quiz_map.get(result_data.get("quiz_join_code", ""))
        submitted_raw = result_data.get("date_submitted")
        submitted_at = (
            datetime.fromisoformat(submitted_raw)
            if submitted_raw
            else datetime.now(timezone.utc)
        )
        db.session.add(
            QuizResult(
                quiz_id=quiz.id if quiz else None,
                student_name=result_data.get("student_name") or "Thí sinh tự do",
                student_code=result_data.get("student_code"),
                quiz_title=result_data.get("quiz_title"),
                join_code=result_data.get("quiz_join_code"),
                score=result_data.get("score"),
                correct_count=parse_non_negative_int(result_data.get("correct_count"), 0),
                total_questions=parse_non_negative_int(result_data.get("total_questions"), 0),
                cheat_count=parse_non_negative_int(result_data.get("cheat_count"), 0),
                date_submitted=submitted_at,
            )
        )

    db.session.commit()
    return True


def ensure_database_shape() -> None:
    db.create_all()

    if db.engine.dialect.name != "sqlite":
        return

    quiz_result_columns = {
        row[1] for row in db.session.execute(text("PRAGMA table_info(quiz_result)")).fetchall()
    }
    required_result_columns = {
        "quiz_id": "INTEGER",
        "student_code": "VARCHAR(30)",
        "join_code": "VARCHAR(10)",
        "correct_count": "INTEGER DEFAULT 0",
        "total_questions": "INTEGER DEFAULT 0",
        "cheat_count": "INTEGER DEFAULT 0",
    }

    updated = False
    for column_name, definition in required_result_columns.items():
        if column_name not in quiz_result_columns:
            db.session.execute(text(f"ALTER TABLE quiz_result ADD COLUMN {column_name} {definition}"))
            updated = True

    if updated:
        db.session.commit()


def normalize_legacy_texts() -> bool:
    changed = False

    for quiz in Quiz.query.all():
        fixed_title = LEGACY_TEXT_FIXES.get(quiz.title)
        if fixed_title and fixed_title != quiz.title:
            quiz.title = fixed_title
            changed = True

        for question in quiz.questions:
            fixed_content = LEGACY_TEXT_FIXES.get(question.content)
            if fixed_content and fixed_content != question.content:
                question.content = fixed_content
                changed = True

    for result in QuizResult.query.all():
        fixed_student_name = LEGACY_TEXT_FIXES.get(result.student_name or "")
        if fixed_student_name and fixed_student_name != result.student_name:
            result.student_name = fixed_student_name
            changed = True

        fixed_quiz_title = LEGACY_TEXT_FIXES.get(result.quiz_title or "")
        if fixed_quiz_title and fixed_quiz_title != result.quiz_title:
            result.quiz_title = fixed_quiz_title
            changed = True

    if changed:
        db.session.commit()
    return changed


def seed_default_teacher() -> bool:
    if TeacherUser.query.filter_by(username="giangvien").first():
        return False

    teacher = TeacherUser(username="giangvien", display_name="Giảng viên mặc định")
    teacher.set_password("123456")
    db.session.add(teacher)
    db.session.commit()
    return True


def seed_sample_data() -> bool:
    if Quiz.query.filter_by(join_code="NHOM02").first():
        return False

    quiz = Quiz(
        title="Kiểm tra Tin học đại cương",
        join_code="NHOM02",
        time_limit=10,
    )
    db.session.add(quiz)
    db.session.flush()

    db.session.add_all(
        [
            Question(
                quiz_id=quiz.id,
                content="Đơn vị nhỏ nhất của thông tin là gì?",
                option_a="Byte",
                option_b="Bit",
                option_c="MB",
                option_d="GB",
                correct_option="B",
            ),
            Question(
                quiz_id=quiz.id,
                content="Phần cứng máy tính gọi là gì?",
                option_a="Software",
                option_b="Firmware",
                option_c="Hardware",
                option_d="Malware",
                correct_option="C",
            ),
            Question(
                quiz_id=quiz.id,
                content="Tổ hợp phím dùng để sao chép nội dung là gì?",
                option_a="Ctrl+V",
                option_b="Ctrl+X",
                option_c="Ctrl+A",
                option_d="Ctrl+C",
                correct_option="D",
            ),
        ]
    )
    db.session.commit()
    return True


def validate_questions_payload(
    questions_payload: list[dict[str, object]],
) -> tuple[list[dict[str, str]] | None, str | None]:
    if not questions_payload:
        return None, "Cần ít nhất 1 câu hỏi để tạo đề thi."

    prepared_questions = []
    for index, raw_question in enumerate(questions_payload, start=1):
        content = str(raw_question.get("content") or "").strip()
        option_a = str(raw_question.get("option_a") or "").strip()
        option_b = str(raw_question.get("option_b") or "").strip()
        option_c = str(raw_question.get("option_c") or "").strip()
        option_d = str(raw_question.get("option_d") or "").strip()
        correct_option = str(raw_question.get("correct_option") or "").strip().upper()

        if not all([content, option_a, option_b, option_c, option_d]):
            return None, f"Câu hỏi {index} chưa đủ nội dung và 4 đáp án."

        if correct_option not in {"A", "B", "C", "D"}:
            return None, f"Câu hỏi {index} chưa chọn đáp án đúng hợp lệ."

        prepared_questions.append(
            {
                "content": content,
                "option_a": option_a,
                "option_b": option_b,
                "option_c": option_c,
                "option_d": option_d,
                "correct_option": correct_option,
            }
        )

    return prepared_questions, None


def apply_quiz_payload(
    quiz: Quiz | None,
    payload: dict[str, object],
) -> tuple[Quiz | None, str | None]:
    title = str(payload.get("title") or "").strip()
    if not title:
        return None, "Bạn phải nhập tên đề thi."

    prepared_questions, question_error = validate_questions_payload(payload.get("questions") or [])
    if question_error:
        return None, question_error

    time_limit = parse_time_limit(payload.get("time_limit"), default=15)
    join_code = normalize_join_code(payload.get("join_code"))

    if quiz is None and not join_code:
        join_code = generate_join_code()
    elif quiz is not None and not join_code:
        join_code = quiz.join_code

    existing_quiz = Quiz.query.filter_by(join_code=join_code).first()
    if existing_quiz and (quiz is None or existing_quiz.id != quiz.id):
        return None, "Mã phòng thi đã tồn tại, vui lòng dùng mã khác."

    target_quiz = quiz or Quiz(title=title, join_code=join_code, time_limit=time_limit)
    target_quiz.title = title
    target_quiz.join_code = join_code
    target_quiz.time_limit = time_limit
    db.session.add(target_quiz)
    db.session.flush()

    if quiz is not None:
        for result in target_quiz.results:
            result.quiz_title = title
            result.join_code = join_code

        for question in list(target_quiz.questions):
            db.session.delete(question)
        db.session.flush()

    db.session.add_all(
        [
            Question(
                quiz_id=target_quiz.id,
                content=question_data["content"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_option=question_data["correct_option"],
            )
            for question_data in prepared_questions or []
        ]
    )

    return target_quiz, None


def get_storage_label() -> str:
    return (
        "SQLite file"
        if current_app.config.get("QUIZ_STORAGE_MODE") == "database"
        else "Bộ nhớ + snapshot"
    )


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    default_db_path = instance_path / "quiz_platform.db"
    default_snapshot_path = instance_path / "quiz_snapshot.json"
    default_db_uri = f"sqlite:///{default_db_path.resolve().as_posix()}"
    configured_db_uri = normalize_database_uri(
        getenv("QUIZ_DATABASE_URI") or getenv("DATABASE_URL"),
        default_db_uri,
    )

    app.config.update(
        SECRET_KEY=getenv("QUIZ_SECRET_KEY", "quiz-platform-dev-secret"),
        SQLALCHEMY_DATABASE_URI=configured_db_uri,
        SQLALCHEMY_ENGINE_OPTIONS={},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTO_SEED_SAMPLE_DATA=True,
        QUIZ_STORAGE_MODE="database",
        QUIZ_SNAPSHOT_PATH=str(default_snapshot_path.resolve()),
    )

    if test_config:
        app.config.update(test_config)

    app.json.ensure_ascii = False
    db.init_app(app)

    @app.route("/")
    def index():
        if is_student_logged_in():
            return redirect(url_for("student_home"))
        return redirect(url_for("student_login"))

    @app.route("/student/login", methods=["GET", "POST"])
    def student_login():
        if is_student_logged_in():
            return redirect(url_for("student_home"))

        error_message = ""
        default_name = ""
        default_code = ""
        if request.method == "POST":
            default_name = request.form.get("student_name") or ""
            default_code = request.form.get("student_code") or ""
            student_name = normalize_person_name(default_name, default="")
            student_code = normalize_student_code(default_code)

            if not student_name:
                error_message = "Bạn cần nhập họ và tên để tiếp tục."
            elif not student_code:
                error_message = "Bạn cần nhập mã sinh viên để tiếp tục."
            else:
                session["student_name"] = student_name
                session["student_code"] = student_code
                return redirect(request.args.get("next") or url_for("student_home"))

        return render_template(
            "student_login.html",
            error_message=error_message,
            default_name=default_name,
            default_code=default_code,
        )

    @app.route("/student/logout")
    def student_logout():
        clear_student_session()
        return redirect(url_for("student_login"))

    @app.route("/student")
    @student_required()
    def student_home():
        return render_template(
            "student_home.html",
            student_name=session.get("student_name", "Thí sinh tự do"),
            student_code=session.get("student_code", "-"),
        )

    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "storage_mode": current_app.config.get("QUIZ_STORAGE_MODE"),
                "quiz_count": Quiz.query.count(),
                "teacher_logged_in": is_teacher_logged_in(),
                "student_logged_in": is_student_logged_in(),
            }
        )

    @app.route("/teacher/login", methods=["GET", "POST"])
    def teacher_login():
        if is_teacher_logged_in():
            return redirect(url_for("teacher_dashboard"))

        error_message = ""
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            teacher = TeacherUser.query.filter_by(username=username).first()

            if teacher and teacher.check_password(password):
                session["teacher_user_id"] = teacher.id
                session["teacher_display_name"] = teacher.display_name
                session["teacher_username"] = teacher.username
                return redirect(request.args.get("next") or url_for("teacher_dashboard"))

            error_message = "Sai tên đăng nhập hoặc mật khẩu."

        return render_template(
            "teacher_login.html",
            error_message=error_message,
            default_username="giangvien",
            default_password="123456",
        )

    @app.route("/teacher/logout")
    def teacher_logout():
        clear_teacher_session()
        return redirect(url_for("teacher_login"))

    @app.route("/teacher")
    @teacher_required()
    def teacher_dashboard():
        quizzes = [serialize_quiz_admin(quiz) for quiz in Quiz.query.order_by(Quiz.id.desc()).all()]
        return render_template(
            "teacher_dashboard.html",
            quizzes_data=quizzes,
            sample_join_code="NHOM02",
            teacher_name=session.get("teacher_display_name", "Giảng viên"),
            teacher_username=session.get("teacher_username", "giangvien"),
            storage_label=get_storage_label(),
        )

    @app.route("/quiz-room/<join_code>")
    @student_required()
    def quiz_room(join_code: str):
        normalized_code = normalize_join_code(join_code)
        Quiz.query.filter_by(join_code=normalized_code).first_or_404()
        return render_template(
            "exam_room.html",
            join_code=normalized_code,
            student_name=session.get("student_name", "Thí sinh tự do"),
            student_code=session.get("student_code", "-"),
        )

    @app.route("/api/check-room/<code>")
    def check_room(code: str):
        normalized_code = normalize_join_code(code)
        quiz = Quiz.query.filter_by(join_code=normalized_code).first()
        if not quiz:
            return jsonify({"status": "error", "message": "Mã phòng thi không tồn tại."}), 404

        return jsonify(
            {
                "status": "success",
                "data": {
                    "quiz_id": quiz.id,
                    "title": quiz.title,
                    "time_limit": quiz.time_limit,
                },
            }
        )

    @app.route("/api/get-quiz/<code>")
    def get_quiz(code: str):
        normalized_code = normalize_join_code(code)
        quiz = Quiz.query.filter_by(join_code=normalized_code).first()
        if not quiz:
            return jsonify({"status": "error", "message": "Không tìm thấy đề thi."}), 404

        return jsonify(
            {
                "status": "success",
                "data": {
                    "id": quiz.id,
                    "title": quiz.title,
                    "join_code": quiz.join_code,
                    "time_limit": quiz.time_limit,
                    "question_count": len(quiz.questions),
                    "questions": [serialize_question_public(question) for question in quiz.questions],
                },
            }
        )

    @app.route("/api/submit-quiz", methods=["POST"])
    def submit_quiz():
        payload = request.get_json(silent=True) or {}
        join_code = normalize_join_code(payload.get("join_code"))
        student_name = normalize_person_name(
            session.get("student_name") or payload.get("student_name")
        )
        student_code = normalize_student_code(
            session.get("student_code") or payload.get("student_code")
        )
        cheat_count = parse_non_negative_int(payload.get("cheat_count"), default=0)
        user_answers = payload.get("answers") or {}

        quiz = Quiz.query.filter_by(join_code=join_code).first()
        if not quiz:
            return jsonify({"status": "error", "message": "Mã phòng thi không hợp lệ."}), 404

        if not quiz.questions:
            return jsonify({"status": "error", "message": "Đề thi hiện chưa có câu hỏi."}), 400

        correct_count = 0
        details = []
        for question in quiz.questions:
            options = question.options()
            selected_option = user_answers.get(str(question.id))
            if selected_option not in options:
                selected_option = None

            is_correct = selected_option == question.correct_option
            if is_correct:
                correct_count += 1

            details.append(
                {
                    "question": question.content,
                    "your_answer": selected_option,
                    "your_answer_text": options.get(selected_option) if selected_option else "Bỏ trống",
                    "correct_answer": question.correct_option,
                    "correct_answer_text": options[question.correct_option],
                    "is_correct": is_correct,
                }
            )

        total_questions = len(quiz.questions)
        score = round((correct_count / total_questions) * 10, 2)
        result = QuizResult(
            quiz_id=quiz.id,
            student_name=student_name or "Thí sinh tự do",
            student_code=student_code or None,
            quiz_title=quiz.title,
            join_code=quiz.join_code,
            score=score,
            correct_count=correct_count,
            total_questions=total_questions,
            cheat_count=cheat_count,
        )
        db.session.add(result)
        db.session.commit()
        save_snapshot()

        return jsonify(
            {
                "status": "success",
                "score": score,
                "correct_count": correct_count,
                "total": total_questions,
                "cheat_count": cheat_count,
                "student_name": result.student_name,
                "student_code": result.student_code or "-",
                "submitted_at": result.date_submitted.strftime("%H:%M %d/%m/%Y"),
                "details": details,
            }
        )

    @app.route("/api/teacher/quizzes", methods=["POST"])
    @teacher_required(api=True)
    def create_quiz():
        payload = request.get_json(silent=True) or {}
        quiz, error_message = apply_quiz_payload(None, payload)
        if error_message:
            db.session.rollback()
            return jsonify({"status": "error", "message": error_message}), 400

        db.session.commit()
        save_snapshot()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Đã tạo đề thi thành công.",
                    "quiz_id": quiz.id,
                    "join_code": quiz.join_code,
                }
            ),
            201,
        )

    @app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["GET"])
    @teacher_required(api=True)
    def get_teacher_quiz(quiz_id: int):
        quiz = db.get_or_404(Quiz, quiz_id)
        return jsonify({"status": "success", "data": serialize_quiz_admin(quiz)})

    @app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["PUT"])
    @teacher_required(api=True)
    def update_quiz(quiz_id: int):
        quiz = db.get_or_404(Quiz, quiz_id)
        payload = request.get_json(silent=True) or {}
        updated_quiz, error_message = apply_quiz_payload(quiz, payload)
        if error_message:
            db.session.rollback()
            return jsonify({"status": "error", "message": error_message}), 400

        db.session.commit()
        save_snapshot()
        return jsonify(
            {
                "status": "success",
                "message": "Đã cập nhật đề thi thành công.",
                "quiz_id": updated_quiz.id,
                "join_code": updated_quiz.join_code,
            }
        )

    @app.route("/api/teacher/quizzes/<int:quiz_id>", methods=["DELETE"])
    @teacher_required(api=True)
    def delete_quiz(quiz_id: int):
        quiz = db.get_or_404(Quiz, quiz_id)
        db.session.delete(quiz)
        db.session.commit()
        save_snapshot()
        return jsonify({"status": "success", "message": "Đã xóa đề thi."})

    @app.route("/api/init-all")
    @teacher_required(api=True)
    def init_all():
        created_teacher = seed_default_teacher()
        created_quiz = seed_sample_data()
        if created_teacher or created_quiz:
            save_snapshot()
        return jsonify(
            {
                "status": "success",
                "seeded_teacher": created_teacher,
                "seeded_quiz": created_quiz,
                "join_code": "NHOM02",
                "message": "Hệ thống đã sẵn sàng sử dụng.",
            }
        )

    with app.app_context():
        try:
            ensure_database_shape()
        except OperationalError:
            if test_config:
                raise
            fallback_config = dict(app.config)
            fallback_config.update(
                SQLALCHEMY_DATABASE_URI="sqlite://",
                SQLALCHEMY_ENGINE_OPTIONS={
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                },
                QUIZ_STORAGE_MODE="snapshot-memory",
            )
            return create_app(fallback_config)

        load_snapshot()
        normalized_legacy = normalize_legacy_texts()
        seeded_teacher = seed_default_teacher()
        seeded_quiz = False
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True) and not Quiz.query.first():
            seeded_quiz = seed_sample_data()

        if normalized_legacy or seeded_teacher or seeded_quiz:
            save_snapshot()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)

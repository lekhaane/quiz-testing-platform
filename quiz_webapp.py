from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from os import getenv
from pathlib import Path

from flask import Flask, current_app, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

db = SQLAlchemy()


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
    )
    results = db.relationship("QuizResult", backref="quiz", lazy=True)


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
    quiz_title = db.Column(db.String(100))
    join_code = db.Column(db.String(10))
    score = db.Column(db.Float)
    correct_count = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    cheat_count = db.Column(db.Integer, default=0)
    date_submitted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


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


LEGACY_TEXT_FIXES = {
    "Kiem tra Tin hoc dai cuong": "Kiểm tra Tin học đại cương",
    "Don vi nho nhat cua thong tin la gi?": "Đơn vị nhỏ nhất của thông tin là gì?",
    "Phan cung may tinh goi la gi?": "Phần cứng máy tính gọi là gì?",
    "To hop phim dung de sao chep noi dung la gi?": "Tổ hợp phím dùng để sao chép nội dung là gì?",
    "Thi sinh tu do": "Thí sinh tự do",
}


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


def ensure_database_shape() -> None:
    db.create_all()

    quiz_result_columns = {
        row[1] for row in db.session.execute(text("PRAGMA table_info(quiz_result)")).fetchall()
    }
    required_result_columns = {
        "quiz_id": "INTEGER",
        "join_code": "VARCHAR(10)",
        "correct_count": "INTEGER DEFAULT 0",
        "total_questions": "INTEGER DEFAULT 0",
        "cheat_count": "INTEGER DEFAULT 0",
    }

    updated = False
    for column_name, definition in required_result_columns.items():
        if column_name not in quiz_result_columns:
            db.session.execute(
                text(f"ALTER TABLE quiz_result ADD COLUMN {column_name} {definition}")
            )
            updated = True

    if updated:
        db.session.commit()


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


def serialize_question_public(question: Question) -> dict[str, object]:
    return {
        "id": question.id,
        "content": question.content,
        "options": question.options(),
    }


def fetch_results_for_quiz(quiz: Quiz) -> list[QuizResult]:
    return (
        QuizResult.query.filter(
            or_(
                QuizResult.quiz_id == quiz.id,
                and_(
                    QuizResult.quiz_id.is_(None),
                    QuizResult.quiz_title == quiz.title,
                ),
            )
        )
        .order_by(QuizResult.date_submitted.desc())
        .all()
    )


def build_teacher_dashboard() -> list[dict[str, object]]:
    dashboard = []
    quizzes = Quiz.query.order_by(Quiz.id.desc()).all()

    for quiz in quizzes:
        questions = sorted(quiz.questions, key=lambda item: item.id)
        results = fetch_results_for_quiz(quiz)
        scores = [result.score for result in results if result.score is not None]
        average_score = round(sum(scores) / len(scores), 2) if scores else None

        dashboard.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "join_code": quiz.join_code,
                "time_limit": quiz.time_limit,
                "question_count": len(questions),
                "attempt_count": len(results),
                "average_score": average_score,
                "questions": [
                    {
                        "content": question.content,
                        "options": question.options(),
                        "correct_option": question.correct_option,
                    }
                    for question in questions
                ],
                "results": [
                    {
                        "student_name": result.student_name or "Thí sinh tự do",
                        "score": result.score,
                        "correct_count": result.correct_count,
                        "total_questions": result.total_questions,
                        "cheat_count": result.cheat_count,
                        "submitted_at": (
                            result.date_submitted.strftime("%H:%M %d/%m/%Y")
                            if result.date_submitted
                            else "-"
                        ),
                    }
                    for result in results
                ],
            }
        )

    return dashboard


def snapshot_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


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
        "quizzes": [],
        "results": [],
    }

    quizzes = Quiz.query.order_by(Quiz.id.asc()).all()
    for quiz in quizzes:
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
                    for question in sorted(quiz.questions, key=lambda item: item.id)
                ],
            }
        )

    results = QuizResult.query.order_by(QuizResult.id.asc()).all()
    for result in results:
        payload["results"].append(
            {
                "quiz_join_code": result.join_code,
                "student_name": result.student_name,
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
            datetime.fromisoformat(submitted_raw) if submitted_raw else datetime.now(timezone.utc)
        )
        db.session.add(
            QuizResult(
                quiz_id=quiz.id if quiz else None,
                student_name=result_data.get("student_name") or "Thí sinh tự do",
                quiz_title=result_data.get("quiz_title"),
                join_code=result_data.get("quiz_join_code"),
                score=result_data.get("score"),
                correct_count=parse_non_negative_int(result_data.get("correct_count"), default=0),
                total_questions=parse_non_negative_int(
                    result_data.get("total_questions"), default=0
                ),
                cheat_count=parse_non_negative_int(result_data.get("cheat_count"), default=0),
                date_submitted=submitted_at,
            )
        )

    db.session.commit()
    return True


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    default_db_uri = getenv("QUIZ_DATABASE_URI")
    default_engine_options = {}
    storage_mode = "database"
    snapshot_path = instance_path / "quiz_snapshot.json"

    if not default_db_uri:
        default_db_uri = "sqlite://"
        default_engine_options = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
        storage_mode = "snapshot-memory"

    app.config.update(
        SQLALCHEMY_DATABASE_URI=default_db_uri,
        SQLALCHEMY_ENGINE_OPTIONS=default_engine_options,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTO_SEED_SAMPLE_DATA=True,
        QUIZ_STORAGE_MODE=storage_mode,
        QUIZ_SNAPSHOT_PATH=str(snapshot_path),
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.route("/")
    def index() -> str:
        return render_template("student_dashboard.html")

    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "storage_mode": app.config.get("QUIZ_STORAGE_MODE"),
                "quiz_count": Quiz.query.count(),
            }
        )

    @app.route("/teacher")
    def teacher_dashboard() -> str:
        return render_template(
            "teacher.html",
            quizzes=build_teacher_dashboard(),
            sample_join_code="NHOM02",
        )

    @app.route("/quiz-room/<join_code>")
    def quiz_room(join_code: str) -> str:
        normalized_code = normalize_join_code(join_code)
        Quiz.query.filter_by(join_code=normalized_code).first_or_404()
        return render_template("quiz_room.html", join_code=normalized_code)

    @app.route("/api/check-room/<code>")
    def check_room(code: str):
        normalized_code = normalize_join_code(code)
        quiz = Quiz.query.filter_by(join_code=normalized_code).first()
        if not quiz:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Mã phòng thi không tồn tại.",
                    }
                ),
                404,
            )

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
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Không tìm thấy đề thi.",
                    }
                ),
                404,
            )

        questions = sorted(quiz.questions, key=lambda item: item.id)
        return jsonify(
            {
                "status": "success",
                "data": {
                    "id": quiz.id,
                    "title": quiz.title,
                    "join_code": quiz.join_code,
                    "time_limit": quiz.time_limit,
                    "question_count": len(questions),
                    "questions": [serialize_question_public(question) for question in questions],
                },
            }
        )

    @app.route("/api/submit-quiz", methods=["POST"])
    def submit_quiz():
        payload = request.get_json(silent=True) or {}
        join_code = normalize_join_code(payload.get("join_code"))
        student_name = (payload.get("student_name") or "Thí sinh tự do").strip()[:100]
        cheat_count = parse_non_negative_int(payload.get("cheat_count"), default=0)
        user_answers = payload.get("answers") or {}

        quiz = Quiz.query.filter_by(join_code=join_code).first()
        if not quiz:
            return jsonify({"status": "error", "message": "Mã phòng thi không hợp lệ."}), 404

        questions = sorted(quiz.questions, key=lambda item: item.id)
        if not questions:
            return jsonify({"status": "error", "message": "Đề thi hiện chưa có câu hỏi."}), 400

        correct_count = 0
        details = []

        for question in questions:
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
                    "your_answer_text": (
                        options.get(selected_option) if selected_option else "Bỏ trống"
                    ),
                    "correct_answer": question.correct_option,
                    "correct_answer_text": options[question.correct_option],
                    "is_correct": is_correct,
                }
            )

        total_questions = len(questions)
        score = round((correct_count / total_questions) * 10, 2)

        new_result = QuizResult(
            quiz_id=quiz.id,
            student_name=student_name or "Thí sinh tự do",
            quiz_title=quiz.title,
            join_code=quiz.join_code,
            score=score,
            correct_count=correct_count,
            total_questions=total_questions,
            cheat_count=cheat_count,
        )
        db.session.add(new_result)
        db.session.commit()
        save_snapshot()

        return jsonify(
            {
                "status": "success",
                "score": score,
                "correct_count": correct_count,
                "total": total_questions,
                "cheat_count": cheat_count,
                "submitted_at": new_result.date_submitted.strftime("%H:%M %d/%m/%Y"),
                "details": details,
            }
        )

    @app.route("/api/teacher/quizzes", methods=["POST"])
    def create_quiz():
        payload = request.get_json(silent=True) or {}
        title = (payload.get("title") or "").strip()
        join_code = normalize_join_code(payload.get("join_code"))
        time_limit = parse_time_limit(payload.get("time_limit"), default=15)
        questions_payload = payload.get("questions") or []

        if not title:
            return jsonify({"status": "error", "message": "Bạn phải nhập tên đề thi."}), 400

        if not questions_payload:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Cần ít nhất 1 câu hỏi để tạo đề thi.",
                    }
                ),
                400,
            )

        if not join_code:
            join_code = generate_join_code()

        if Quiz.query.filter_by(join_code=join_code).first():
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Mã phòng thi đã tồn tại, vui lòng dùng mã khác.",
                    }
                ),
                400,
            )

        quiz = Quiz(title=title, join_code=join_code, time_limit=time_limit)
        db.session.add(quiz)
        db.session.flush()

        prepared_questions = []
        for index, raw_question in enumerate(questions_payload, start=1):
            content = (raw_question.get("content") or "").strip()
            option_a = (raw_question.get("option_a") or "").strip()
            option_b = (raw_question.get("option_b") or "").strip()
            option_c = (raw_question.get("option_c") or "").strip()
            option_d = (raw_question.get("option_d") or "").strip()
            correct_option = (raw_question.get("correct_option") or "").strip().upper()

            if not all([content, option_a, option_b, option_c, option_d]):
                db.session.rollback()
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Câu hỏi {index} chưa đủ nội dung và 4 đáp án.",
                        }
                    ),
                    400,
                )

            if correct_option not in {"A", "B", "C", "D"}:
                db.session.rollback()
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Câu hỏi {index} chưa chọn đáp án đúng hợp lệ.",
                        }
                    ),
                    400,
                )

            prepared_questions.append(
                Question(
                    quiz_id=quiz.id,
                    content=content,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                    correct_option=correct_option,
                )
            )

        db.session.add_all(prepared_questions)
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

    @app.route("/api/init-all")
    def init_all():
        created = seed_sample_data()
        save_snapshot()
        return jsonify(
            {
                "status": "success",
                "seeded": created,
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
            app.config.update(
                SQLALCHEMY_DATABASE_URI="sqlite://",
                SQLALCHEMY_ENGINE_OPTIONS={
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                },
                QUIZ_STORAGE_MODE="snapshot-memory",
                QUIZ_SNAPSHOT_PATH=str(snapshot_path),
            )
            return create_app(app.config)

        loaded_from_snapshot = load_snapshot()
        normalized_legacy = normalize_legacy_texts()
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True) and not Quiz.query.first():
            if seed_sample_data() or not loaded_from_snapshot:
                save_snapshot()
        elif normalized_legacy:
            save_snapshot()

    return app
if __name__ == "__main__":
    create_app().run(debug=True)

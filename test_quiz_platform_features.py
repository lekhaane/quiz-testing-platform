import unittest

from sqlalchemy.pool import StaticPool

from quiz_platform_core import QuestionBankItem, Quiz, QuizResult, create_app, db


class QuizPlatformFeatureTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "AUTO_SEED_SAMPLE_DATA": False,
                "AUTO_SEED_QUESTION_BANK": False,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                },
                "QUIZ_STORAGE_MODE": "test-memory",
                "QUIZ_SNAPSHOT_PATH": "",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()

    def login_teacher(self):
        return self.client.post(
            "/teacher/login",
            data={"username": "giangvien", "password": "123456"},
            follow_redirects=False,
        )

    def login_student(self):
        return self.client.post(
            "/student/login",
            data={"student_name": "Nguyễn Văn A", "student_code": "SV001"},
            follow_redirects=False,
        )

    def test_default_seed_contains_seeded_question_bank_and_demo_quiz(self):
        seeded_app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                },
                "QUIZ_STORAGE_MODE": "test-memory",
                "QUIZ_SNAPSHOT_PATH": "",
            }
        )

        with seeded_app.app_context():
            self.assertGreaterEqual(QuestionBankItem.query.count(), 15)
            quiz = Quiz.query.filter_by(join_code="NHOM02").first()
            self.assertIsNotNone(quiz)
            self.assertGreaterEqual(len(quiz.questions), 15)

        with seeded_app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()

    def test_default_seed_contains_twenty_quiz_sets_and_four_unique_group_codes(self):
        seeded_app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                },
                "QUIZ_STORAGE_MODE": "test-memory",
                "QUIZ_SNAPSHOT_PATH": "",
            }
        )

        with seeded_app.app_context():
            preset_sets = [
                Quiz.query.filter_by(join_code=f"DE{i:02d}").first()
                for i in range(1, 21)
            ]
            self.assertTrue(all(preset_sets))
            self.assertTrue(all(len(quiz.questions) == 20 for quiz in preset_sets if quiz))

            group_quizzes = [
                Quiz.query.filter_by(join_code=f"NHOM{i:02d}").first()
                for i in range(1, 5)
            ]
            self.assertTrue(all(group_quizzes))
            self.assertTrue(all(len(quiz.questions) == 20 for quiz in group_quizzes if quiz))

            group_signatures = {
                tuple(sorted(question.content for question in quiz.questions))
                for quiz in group_quizzes
                if quiz
            }
            self.assertEqual(len(group_signatures), 4)

        with seeded_app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()

    def test_teacher_can_manage_question_bank(self):
        self.login_teacher()

        create_response = self.client.post(
            "/api/teacher/question-bank",
            json={
                "content": "SQL dùng để làm gì?",
                "category": "Cơ sở dữ liệu",
                "difficulty": "Cơ bản",
                "option_a": "Thiết kế ảnh",
                "option_b": "Quản lý dữ liệu",
                "option_c": "Soạn nhạc",
                "option_d": "Vẽ biểu đồ",
                "correct_option": "B",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        created_item = create_response.get_json()["data"]
        self.assertEqual(created_item["category"], "Cơ sở dữ liệu")

        list_response = self.client.get("/api/teacher/question-bank")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.get_json()["data"]), 1)

        update_response = self.client.put(
            f"/api/teacher/question-bank/{created_item['id']}",
            json={
                "content": "SQL thường được dùng để làm gì?",
                "category": "Cơ sở dữ liệu",
                "difficulty": "Trung bình",
                "option_a": "Quản lý dữ liệu",
                "option_b": "Dựng video",
                "option_c": "Chỉnh ảnh",
                "option_d": "Soạn nhạc",
                "correct_option": "A",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()["data"]["difficulty"], "Trung bình")

        with self.app.app_context():
            item = QuestionBankItem.query.one()
            self.assertEqual(item.correct_option, "A")
            self.assertEqual(item.difficulty, "Trung bình")

    def test_student_cannot_submit_same_quiz_twice(self):
        self.login_teacher()

        create_quiz_response = self.client.post(
            "/api/teacher/quizzes",
            json={
                "title": "Kiểm tra Python",
                "join_code": "PY999",
                "time_limit": 10,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Trình duyệt",
                        "option_d": "Cơ sở dữ liệu",
                        "correct_option": "A",
                    }
                ],
            },
        )
        self.assertEqual(create_quiz_response.status_code, 201)

        self.login_student()
        quiz_response = self.client.get("/api/get-quiz/PY999")
        self.assertEqual(quiz_response.status_code, 200)
        question_id = quiz_response.get_json()["data"]["questions"][0]["id"]

        first_submit = self.client.post(
            "/api/submit-quiz",
            json={
                "join_code": "PY999",
                "cheat_count": 0,
                "answers": {str(question_id): "A"},
            },
        )
        self.assertEqual(first_submit.status_code, 200)
        self.assertEqual(first_submit.get_json()["status"], "success")

        second_submit = self.client.post(
            "/api/submit-quiz",
            json={
                "join_code": "PY999",
                "cheat_count": 2,
                "answers": {str(question_id): "A"},
            },
        )
        self.assertEqual(second_submit.status_code, 409)
        self.assertEqual(second_submit.get_json()["status"], "error")

        with self.app.app_context():
            results = QuizResult.query.all()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].student_code, "SV001")


if __name__ == "__main__":
    unittest.main()

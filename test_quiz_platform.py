import unittest

from sqlalchemy.pool import StaticPool

from quiz_platform_app import Quiz, QuizResult, TeacherUser, create_app, db


class QuizPlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "AUTO_SEED_SAMPLE_DATA": False,
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

    def test_protected_routes_require_login(self):
        home_page = self.client.get("/")
        self.assertEqual(home_page.status_code, 302)
        self.assertIn("/student/login", home_page.headers["Location"])

        student_page = self.client.get("/student")
        self.assertEqual(student_page.status_code, 302)
        self.assertIn("/student/login", student_page.headers["Location"])

        quiz_room_page = self.client.get("/quiz-room/NHOM02")
        self.assertEqual(quiz_room_page.status_code, 302)
        self.assertIn("/student/login", quiz_room_page.headers["Location"])

        teacher_page = self.client.get("/teacher")
        self.assertEqual(teacher_page.status_code, 302)
        self.assertIn("/teacher/login", teacher_page.headers["Location"])

        api_response = self.client.post(
            "/api/teacher/quizzes",
            json={"title": "Không hợp lệ", "questions": []},
        )
        self.assertEqual(api_response.status_code, 401)
        self.assertEqual(api_response.get_json()["status"], "error")

        with self.app.app_context():
            teacher = TeacherUser.query.filter_by(username="giangvien").first()
            self.assertIsNotNone(teacher)

    def test_teacher_can_create_update_and_delete_quiz(self):
        health_response = self.client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.get_json()["status"], "ok")
        self.assertFalse(health_response.get_json()["student_logged_in"])

        student_login_response = self.login_student()
        self.assertEqual(student_login_response.status_code, 302)
        self.assertTrue(student_login_response.headers["Location"].endswith("/student"))

        student_page = self.client.get("/student")
        self.assertEqual(student_page.status_code, 200)
        student_html = student_page.get_data(as_text=True)
        self.assertIn("Nguyễn Văn A", student_html)
        self.assertIn("SV001", student_html)

        teacher_login_response = self.login_teacher()
        self.assertEqual(teacher_login_response.status_code, 302)
        self.assertTrue(teacher_login_response.headers["Location"].endswith("/teacher"))

        create_response = self.client.post(
            "/api/teacher/quizzes",
            json={
                "title": "Kiểm tra Python",
                "join_code": "PY101",
                "time_limit": 12,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Cơ sở dữ liệu",
                        "option_d": "Trình duyệt",
                        "correct_option": "A",
                    },
                    {
                        "content": "Lệnh in ra màn hình trong Python là gì?",
                        "option_a": "echo()",
                        "option_b": "show()",
                        "option_c": "print()",
                        "option_d": "write()",
                        "correct_option": "C",
                    },
                ],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.get_json()
        self.assertEqual(create_payload["status"], "success")
        self.assertEqual(create_payload["join_code"], "PY101")
        quiz_id = create_payload["quiz_id"]

        teacher_quiz_response = self.client.get(f"/api/teacher/quizzes/{quiz_id}")
        self.assertEqual(teacher_quiz_response.status_code, 200)
        self.assertEqual(teacher_quiz_response.get_json()["data"]["question_count"], 2)

        update_response = self.client.put(
            f"/api/teacher/quizzes/{quiz_id}",
            json={
                "title": "Kiểm tra Python nâng cao",
                "join_code": "PY202",
                "time_limit": 20,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Cơ sở dữ liệu",
                        "option_d": "Trình duyệt",
                        "correct_option": "A",
                    },
                    {
                        "content": "Hàm dùng để lấy độ dài chuỗi là gì?",
                        "option_a": "count()",
                        "option_b": "len()",
                        "option_c": "size()",
                        "option_d": "measure()",
                        "correct_option": "B",
                    },
                ],
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()["join_code"], "PY202")

        old_room_response = self.client.get("/api/check-room/PY101")
        self.assertEqual(old_room_response.status_code, 404)

        room_response = self.client.get("/api/check-room/PY202")
        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.get_json()["data"]["title"], "Kiểm tra Python nâng cao")

        quiz_room_page = self.client.get("/quiz-room/PY202")
        self.assertEqual(quiz_room_page.status_code, 200)
        quiz_room_html = quiz_room_page.get_data(as_text=True)
        self.assertIn("Nguyễn Văn A", quiz_room_html)
        self.assertIn("SV001", quiz_room_html)

        quiz_response = self.client.get("/api/get-quiz/PY202")
        self.assertEqual(quiz_response.status_code, 200)
        quiz_payload = quiz_response.get_json()["data"]
        self.assertEqual(quiz_payload["question_count"], 2)

        answers = {
            str(quiz_payload["questions"][0]["id"]): "A",
            str(quiz_payload["questions"][1]["id"]): "B",
        }
        submit_response = self.client.post(
            "/api/submit-quiz",
            json={
                "join_code": "PY202",
                "cheat_count": 1,
                "answers": answers,
            },
        )

        self.assertEqual(submit_response.status_code, 200)
        submit_payload = submit_response.get_json()
        self.assertEqual(submit_payload["status"], "success")
        self.assertEqual(submit_payload["score"], 10.0)
        self.assertEqual(submit_payload["correct_count"], 2)
        self.assertEqual(submit_payload["cheat_count"], 1)
        self.assertEqual(submit_payload["student_name"], "Nguyễn Văn A")
        self.assertEqual(submit_payload["student_code"], "SV001")

        refreshed_teacher_view = self.client.get(f"/api/teacher/quizzes/{quiz_id}")
        refreshed_payload = refreshed_teacher_view.get_json()["data"]
        self.assertEqual(len(refreshed_payload["results"]), 1)
        self.assertEqual(refreshed_payload["results"][0]["student_name"], "Nguyễn Văn A")
        self.assertEqual(refreshed_payload["results"][0]["student_code"], "SV001")

        with self.app.app_context():
            quiz = Quiz.query.filter_by(join_code="PY202").one()
            self.assertEqual(quiz.title, "Kiểm tra Python nâng cao")

            result = QuizResult.query.one()
            self.assertEqual(result.student_name, "Nguyễn Văn A")
            self.assertEqual(result.student_code, "SV001")
            self.assertEqual(result.score, 10.0)
            self.assertEqual(result.cheat_count, 1)

        delete_response = self.client.delete(f"/api/teacher/quizzes/{quiz_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json()["status"], "success")

        deleted_room_response = self.client.get("/api/check-room/PY202")
        self.assertEqual(deleted_room_response.status_code, 404)
        return

        login_response = self.login_teacher()
        self.assertEqual(login_response.status_code, 302)
        self.assertTrue(login_response.headers["Location"].endswith("/teacher"))

        create_response = self.client.post(
            "/api/teacher/quizzes",
            json={
                "title": "Kiểm tra Python",
                "join_code": "PY101",
                "time_limit": 12,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Cơ sở dữ liệu",
                        "option_d": "Trình duyệt",
                        "correct_option": "A",
                    },
                    {
                        "content": "Lệnh in ra màn hình trong Python là gì?",
                        "option_a": "echo()",
                        "option_b": "show()",
                        "option_c": "print()",
                        "option_d": "write()",
                        "correct_option": "C",
                    },
                ],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.get_json()
        self.assertEqual(create_payload["status"], "success")
        self.assertEqual(create_payload["join_code"], "PY101")
        quiz_id = create_payload["quiz_id"]

        teacher_quiz_response = self.client.get(f"/api/teacher/quizzes/{quiz_id}")
        self.assertEqual(teacher_quiz_response.status_code, 200)
        self.assertEqual(teacher_quiz_response.get_json()["data"]["question_count"], 2)

        update_response = self.client.put(
            f"/api/teacher/quizzes/{quiz_id}",
            json={
                "title": "Kiểm tra Python nâng cao",
                "join_code": "PY202",
                "time_limit": 20,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Cơ sở dữ liệu",
                        "option_d": "Trình duyệt",
                        "correct_option": "A",
                    },
                    {
                        "content": "Hàm dùng để lấy độ dài chuỗi là gì?",
                        "option_a": "count()",
                        "option_b": "len()",
                        "option_c": "size()",
                        "option_d": "measure()",
                        "correct_option": "B",
                    },
                ],
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json()["join_code"], "PY202")

        old_room_response = self.client.get("/api/check-room/PY101")
        self.assertEqual(old_room_response.status_code, 404)

        room_response = self.client.get("/api/check-room/PY202")
        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.get_json()["data"]["title"], "Kiểm tra Python nâng cao")

        quiz_response = self.client.get("/api/get-quiz/PY202")
        self.assertEqual(quiz_response.status_code, 200)
        quiz_payload = quiz_response.get_json()["data"]
        self.assertEqual(quiz_payload["question_count"], 2)

        answers = {
            str(quiz_payload["questions"][0]["id"]): "A",
            str(quiz_payload["questions"][1]["id"]): "B",
        }
        submit_response = self.client.post(
            "/api/submit-quiz",
            json={
                "join_code": "PY202",
                "student_name": "Nguyễn Văn A",
                "cheat_count": 1,
                "answers": answers,
            },
        )

        self.assertEqual(submit_response.status_code, 200)
        submit_payload = submit_response.get_json()
        self.assertEqual(submit_payload["status"], "success")
        self.assertEqual(submit_payload["score"], 10.0)
        self.assertEqual(submit_payload["correct_count"], 2)
        self.assertEqual(submit_payload["cheat_count"], 1)

        refreshed_teacher_view = self.client.get(f"/api/teacher/quizzes/{quiz_id}")
        refreshed_payload = refreshed_teacher_view.get_json()["data"]
        self.assertEqual(len(refreshed_payload["results"]), 1)
        self.assertEqual(refreshed_payload["results"][0]["student_name"], "Nguyễn Văn A")

        with self.app.app_context():
            quiz = Quiz.query.filter_by(join_code="PY202").one()
            self.assertEqual(quiz.title, "Kiểm tra Python nâng cao")

            result = QuizResult.query.one()
            self.assertEqual(result.student_name, "Nguyễn Văn A")
            self.assertEqual(result.score, 10.0)
            self.assertEqual(result.cheat_count, 1)

        delete_response = self.client.delete(f"/api/teacher/quizzes/{quiz_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json()["status"], "success")

        deleted_room_response = self.client.get("/api/check-room/PY202")
        self.assertEqual(deleted_room_response.status_code, 404)
        return
        """

        create_response = self.client.post(
            "/api/teacher/quizzes",
            json={
                "title": "Kiểm tra Python",
                "join_code": "PY101",
                "time_limit": 12,
                "questions": [
                    {
                        "content": "Python là ngôn ngữ gì?",
                        "option_a": "Lập trình",
                        "option_b": "Hệ điều hành",
                        "option_c": "Cơ sở dữ liệu",
                        "option_d": "Trình duyệt",
                        "correct_option": "A",
                    },
                    {
                        "content": "Lệnh in ra màn hình trong Python là gì?",
                        "option_a": "echo()",
                        "option_b": "show()",
                        "option_c": "print()",
                        "option_d": "write()",
                        "correct_option": "C",
                    },
                ],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.get_json()
        self.assertEqual(create_payload["status"], "success")
        self.assertEqual(create_payload["join_code"], "PY101")

        room_response = self.client.get("/api/check-room/PY101")
        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.get_json()["status"], "success")

        quiz_response = self.client.get("/api/get-quiz/PY101")
        self.assertEqual(quiz_response.status_code, 200)
        quiz_payload = quiz_response.get_json()["data"]
        self.assertEqual(quiz_payload["question_count"], 2)

        answers = {str(quiz_payload["questions"][0]["id"]): "A", str(quiz_payload["questions"][1]["id"]): "C"}
        submit_response = self.client.post(
            "/api/submit-quiz",
            json={
                "join_code": "PY101",
                "student_name": "Nguyễn Văn A",
                "cheat_count": 1,
                "answers": answers,
            },
        )

        self.assertEqual(submit_response.status_code, 200)
        submit_payload = submit_response.get_json()
        self.assertEqual(submit_payload["status"], "success")
        self.assertEqual(submit_payload["score"], 10.0)
        self.assertEqual(submit_payload["correct_count"], 2)
        self.assertEqual(submit_payload["cheat_count"], 1)

        with self.app.app_context():
            result = QuizResult.query.one()
            self.assertEqual(result.student_name, "Nguyễn Văn A")
            self.assertEqual(result.score, 10.0)
            self.assertEqual(result.cheat_count, 1)

        """

if __name__ == "__main__":
    unittest.main()

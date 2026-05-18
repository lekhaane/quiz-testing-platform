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
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

PRESET_QUIZ_SET_COUNT = 20
PRESET_QUESTIONS_PER_SET = 20
PRESET_QUIZ_TIME_LIMIT = 25
PRESET_SET_JOIN_CODES = [f"DE{i:02d}" for i in range(1, PRESET_QUIZ_SET_COUNT + 1)]
GROUP_JOIN_CODES = [f"NHOM{i:02d}" for i in range(1, 5)]
PRESET_RANDOM_SEED = 20260510

QUESTION_DIFFICULTIES = ["Cơ bản", "Trung bình", "Nâng cao"]
LEGACY_TEXT_FIXES = {
    "Kiem tra Tin hoc dai cuong": "Kiểm tra Tin học đại cương",
    "Don vi nho nhat cua thong tin la gi?": "Đơn vị nhỏ nhất của thông tin là gì?",
    "Phan cung may tinh goi la gi?": "Phần cứng máy tính gọi là gì?",
    "To hop phim dung de sao chep noi dung la gi?": "Tổ hợp phím dùng để sao chép nội dung là gì?",
    "Thi sinh tu do": "Thí sinh tự do",
}


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


class QuestionBankItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="Chung")
    difficulty = db.Column(db.String(30), nullable=False, default="Cơ bản")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def options(self) -> dict[str, str]:
        return {
            "A": self.option_a,
            "B": self.option_b,
            "C": self.option_c,
            "D": self.option_d,
        }


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


def make_seed_question(
    content: str,
    correct: str,
    wrong_1: str,
    wrong_2: str,
    wrong_3: str,
    category: str,
    difficulty: str = "Cơ bản",
) -> dict[str, str]:
    return {
        "content": content,
        "option_a": correct,
        "option_b": wrong_1,
        "option_c": wrong_2,
        "option_d": wrong_3,
        "correct_option": "A",
        "category": category,
        "difficulty": difficulty,
    }


def get_seed_question_bank_questions() -> list[dict[str, str]]:
    rows = [
        ("Đơn vị nhỏ nhất của thông tin là gì?", "Bit", "Byte", "MB", "GB", "Tin học đại cương", "Cơ bản"),
        ("Phần cứng máy tính là gì?", "Các thiết bị vật lý của máy tính", "Các ứng dụng văn phòng", "Dữ liệu trên Internet", "Tài khoản người dùng", "Tin học đại cương", "Cơ bản"),
        ("Tổ hợp phím nào dùng để sao chép nội dung?", "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+P", "Tin học đại cương", "Cơ bản"),
        ("Thiết bị nào dùng để nhập dữ liệu vào máy tính?", "Bàn phím", "Màn hình", "Loa", "Máy in", "Tin học đại cương", "Cơ bản"),
        ("RAM có vai trò chính là gì?", "Lưu trữ tạm thời dữ liệu khi máy đang chạy", "Lưu trữ dữ liệu vĩnh viễn", "Kết nối Internet", "In tài liệu", "Tin học đại cương", "Cơ bản"),
        ("CPU thường được ví như bộ phận nào của máy tính?", "Bộ não xử lý lệnh", "Kho lưu trữ ảnh", "Nguồn điện dự phòng", "Thiết bị phát Wi-Fi", "Tin học đại cương", "Cơ bản"),
        ("Hệ điều hành có chức năng chính nào?", "Quản lý tài nguyên và điều phối hoạt động máy tính", "Chỉ dùng để gửi email", "Chỉ dùng để vẽ hình", "Chỉ dùng để in ấn", "Tin học đại cương", "Trung bình"),
        ("Tệp Word hiện nay thường có phần mở rộng nào?", ".docx", ".xlsx", ".pptx", ".jpg", "Tin học đại cương", "Cơ bản"),
        ("Thiết bị nào dùng để hiển thị hình ảnh từ máy tính?", "Màn hình", "Máy in", "USB", "Bộ định tuyến", "Tin học đại cương", "Cơ bản"),
        ("Ổ SSD thường dùng để làm gì?", "Lưu trữ dữ liệu lâu dài", "Tăng âm lượng loa", "Chụp ảnh webcam", "Sạc pin laptop", "Tin học đại cương", "Cơ bản"),
        ("Địa chỉ IP dùng để làm gì trong mạng máy tính?", "Xác định thiết bị trên mạng", "Tăng tốc độ gõ phím", "Lưu mật khẩu trình duyệt", "Nén hình ảnh", "Mạng máy tính", "Trung bình"),
        ("Thiết bị nào thường dùng để kết nối nhiều máy trong cùng mạng LAN?", "Switch", "Scanner", "Projector", "UPS", "Mạng máy tính", "Cơ bản"),
        ("HTTP chủ yếu dùng để làm gì?", "Truy cập và truyền tải nội dung web", "Điều khiển chuột không dây", "Sạc pin laptop", "Nén cơ sở dữ liệu", "Mạng máy tính", "Cơ bản"),
        ("DNS có nhiệm vụ gì?", "Phân giải tên miền thành địa chỉ IP", "Mã hóa toàn bộ ổ cắm", "Tạo slide thuyết trình", "Chống rung chuột", "Mạng máy tính", "Trung bình"),
        ("Router thường dùng để làm gì?", "Định tuyến dữ liệu giữa các mạng", "In tài liệu", "Chụp ảnh webcam", "Tăng âm lượng loa", "Mạng máy tính", "Trung bình"),
        ("Mô hình client-server mô tả điều gì?", "Sự trao đổi giữa máy yêu cầu và máy cung cấp dịch vụ", "Cách văn bản được in ra giấy", "Quá trình nén ảnh JPG", "Cấu tạo pin laptop", "Mạng máy tính", "Trung bình"),
        ("Wi-Fi là công nghệ dùng để làm gì?", "Kết nối mạng không dây", "Tạo khóa chính", "Biên dịch chương trình", "Xóa bảng dữ liệu", "Mạng máy tính", "Cơ bản"),
        ("Băng thông mạng biểu thị điều gì?", "Khả năng truyền dữ liệu trong một khoảng thời gian", "Độ sáng màn hình", "Dung lượng pin", "Số trang in được", "Mạng máy tính", "Trung bình"),
        ("Firewall dùng để làm gì?", "Lọc và kiểm soát lưu lượng mạng", "Tạo bảng tính", "Lưu file PDF", "Phát nhạc nền", "Bảo mật", "Trung bình"),
        ("HTTPS khác HTTP ở điểm nào?", "HTTPS có mã hóa dữ liệu truyền tải", "HTTPS không dùng trên web", "HTTPS chỉ dùng cho email", "HTTPS là hệ điều hành", "Bảo mật", "Trung bình"),
        ("Mật khẩu mạnh nên có đặc điểm gì?", "Kết hợp chữ hoa, chữ thường, số và ký tự đặc biệt", "Chỉ có tên người dùng", "Chỉ có 4 ký tự", "Luôn là 123456", "Bảo mật", "Cơ bản"),
        ("Phishing là hình thức tấn công nào?", "Lừa người dùng cung cấp thông tin nhạy cảm", "Tải pin nhanh hơn", "Nén file cực đại", "Tăng số lượng RAM", "Bảo mật", "Trung bình"),
        ("Xác thực hai yếu tố giúp ích gì?", "Tăng lớp bảo vệ khi đăng nhập", "Làm màn hình sáng hơn", "Tự động cài driver", "Giảm kích thước ảnh", "Bảo mật", "Trung bình"),
        ("Mã độc máy tính thường gây rủi ro gì?", "Đánh cắp, phá hoại hoặc làm gián đoạn dữ liệu", "Tăng tốc độ Internet", "Sửa lỗi chính tả", "Tự tạo bài thuyết trình", "Bảo mật", "Trung bình"),
        ("Trong cơ sở dữ liệu quan hệ, bảng dùng để làm gì?", "Lưu trữ dữ liệu theo hàng và cột", "Chạy chương trình Java", "Vẽ sơ đồ mạng", "Tăng tốc trình duyệt", "Cơ sở dữ liệu", "Cơ bản"),
        ("Khóa chính có vai trò gì?", "Phân biệt duy nhất mỗi bản ghi", "Ẩn toàn bộ bảng dữ liệu", "Tăng âm lượng máy tính", "Tự động xóa dữ liệu trùng", "Cơ sở dữ liệu", "Trung bình"),
        ("Câu lệnh SQL nào dùng để lấy dữ liệu từ bảng?", "SELECT", "INSERT", "UPDATE", "DELETE", "Cơ sở dữ liệu", "Cơ bản"),
        ("Lệnh SQL nào dùng để thêm bản ghi mới?", "INSERT", "SELECT", "DROP", "ALTER", "Cơ sở dữ liệu", "Cơ bản"),
        ("Lệnh SQL nào dùng để cập nhật dữ liệu?", "UPDATE", "SELECT", "COUNT", "RENAME", "Cơ sở dữ liệu", "Cơ bản"),
        ("Quan hệ một-nhiều trong CSDL nghĩa là gì?", "Một bản ghi ở bảng A liên kết với nhiều bản ghi ở bảng B", "Mọi bảng chỉ có một cột", "Không thể có khóa ngoại", "Không thể có truy vấn", "Cơ sở dữ liệu", "Trung bình"),
        ("Khóa ngoại dùng để làm gì?", "Liên kết dữ liệu giữa các bảng", "Xóa tất cả bảng", "Đặt mật khẩu cho CSDL", "Tạo file backup PDF", "Cơ sở dữ liệu", "Trung bình"),
        ("Hàm COUNT() trong SQL dùng để làm gì?", "Đếm số bản ghi", "Sắp xếp tăng dần", "Xóa bảng", "Thay đổi tên cột", "Cơ sở dữ liệu", "Cơ bản"),
        ("Trong lập trình, biến dùng để làm gì?", "Lưu trữ giá trị để sử dụng trong chương trình", "Xóa hệ điều hành", "Tăng kích thước màn hình", "Kết nối Wi-Fi", "Lập trình cơ bản", "Cơ bản"),
        ("Cấu trúc lặp dùng để làm gì?", "Lặp lại một khối lệnh nhiều lần", "Tắt chương trình ngay lập tức", "Chỉ khai báo biến số thực", "Lưu ảnh lên máy in", "Lập trình cơ bản", "Cơ bản"),
        ("Câu lệnh if-else dùng để làm gì?", "Rẽ nhánh xử lý theo điều kiện", "Tạo kết nối mạng LAN", "Lưu dữ liệu vào RAM vĩnh viễn", "Mở file PDF", "Lập trình cơ bản", "Cơ bản"),
        ("Mảng thường được dùng để làm gì?", "Lưu nhiều giá trị cùng kiểu dữ liệu", "Tạo tài khoản email", "Phát nhạc nền", "Mã hóa địa chỉ IP", "Lập trình cơ bản", "Trung bình"),
        ("Hàm trong lập trình dùng để làm gì?", "Đóng gói một nhóm lệnh có thể tái sử dụng", "Tắt máy tính", "Nén file ảnh", "Cắm USB", "Lập trình cơ bản", "Cơ bản"),
        ("Kiểu dữ liệu boolean thường chứa giá trị nào?", "True hoặc False", "1, 2, 3", "A, B, C", "Ngày tháng năm", "Lập trình cơ bản", "Cơ bản"),
        ("Toán tử so sánh dùng để làm gì?", "So sánh hai giá trị", "Nạp pin laptop", "Mở trình duyệt", "Chụp ảnh webcam", "Lập trình cơ bản", "Cơ bản"),
        ("Lỗi cú pháp trong lập trình là gì?", "Lỗi do viết sai quy tắc ngôn ngữ", "Lỗi mất kết nối mạng", "Lỗi hết giấy máy in", "Lỗi sai mật khẩu Wi-Fi", "Lập trình cơ bản", "Trung bình"),
        ("Thuật toán là gì?", "Tập hữu hạn các bước giải quyết một bài toán", "Một loại phần cứng", "Tên trình duyệt web", "Thiết bị kết nối Internet", "Thuật toán", "Trung bình"),
        ("Tìm kiếm tuyến tính hoạt động như thế nào?", "Duyệt lần lượt từng phần tử để tìm giá trị", "Luôn chia đôi mảng", "Chỉ dùng cho cây", "Chỉ dùng cho đồ họa", "Thuật toán", "Trung bình"),
        ("Thuật toán sắp xếp dùng để làm gì?", "Sắp xếp dữ liệu theo thứ tự mong muốn", "Xóa tất cả file", "Kết nối Wi-Fi", "Nén file video", "Thuật toán", "Cơ bản"),
        ("Big O dùng để mô tả điều gì?", "Độ phức tạp thời gian hoặc bộ nhớ của thuật toán", "Kích thước màn hình", "Dung lượng pin", "Tốc độ chuột", "Thuật toán", "Nâng cao"),
        ("Tìm kiếm nhị phân yêu cầu dữ liệu như thế nào?", "Dữ liệu đã được sắp xếp", "Dữ liệu phải là ảnh", "Dữ liệu phải rỗng", "Dữ liệu phải mã hóa", "Thuật toán", "Nâng cao"),
        ("HTML chủ yếu dùng để làm gì?", "Tạo cấu trúc trang web", "Quản lý CSDL quan hệ", "Mã hóa file exe", "Điều khiển router", "Web cơ bản", "Cơ bản"),
        ("CSS chủ yếu dùng để làm gì?", "Định dạng giao diện trang web", "Khởi động máy chủ", "Tạo khóa chính", "Xử lý truy vấn SQL", "Web cơ bản", "Cơ bản"),
        ("JavaScript trên web thường dùng để làm gì?", "Xử lý tương tác và logic trên giao diện", "Thay pin máy tính", "Tạo cáp mạng", "Sửa loa", "Web cơ bản", "Trung bình"),
        ("Form đăng nhập sinh viên cần thông tin gì?", "Mã sinh viên và tên sinh viên", "Số seri màn hình", "Địa chỉ MAC của router", "Mã màu CSS", "Web cơ bản", "Cơ bản"),
        ("Mã phòng thi trong hệ thống dùng để làm gì?", "Cho phép sinh viên vào đúng đề thi", "Tự động tăng điểm", "Đổi mật khẩu giảng viên", "Xóa ngân hàng câu hỏi", "Nền tảng kiểm tra", "Cơ bản"),
        ("Đồng hồ đếm ngược giúp sinh viên biết điều gì?", "Thời gian còn lại để nộp bài", "Số lượng giảng viên online", "Tốc độ mạng hiện tại", "Dung lượng RAM còn trống", "Nền tảng kiểm tra", "Cơ bản"),
        ("Chấm điểm tự động hoạt động dựa trên yếu tố nào?", "So sánh đáp án sinh viên chọn với đáp án đúng", "Đo độ sáng màn hình", "Đếm số lần cuộn trang", "Tự đoán theo tên sinh viên", "Nền tảng kiểm tra", "Cơ bản"),
        ("Chống gian lận cơ bản có thể ghi nhận điều gì?", "Số lần rời khỏi cửa sổ làm bài", "Màu áo của sinh viên", "Kích thước bàn phím", "Loại ghế đang ngồi", "Nền tảng kiểm tra", "Trung bình"),
        ("Giảng viên cần ngân hàng câu hỏi để làm gì?", "Quản lý và tái sử dụng câu hỏi khi tạo đề", "Tự động thay đổi font máy tính", "Xóa lịch sử trình duyệt", "Tạo ảnh đại diện", "Nền tảng kiểm tra", "Cơ bản"),
        ("Kết quả minh bạch sau khi nộp bài nên hiển thị gì?", "Điểm số, số câu đúng và tổng số câu", "Mật khẩu giảng viên", "Đáp án của sinh viên khác", "Mã nguồn hệ thống", "Nền tảng kiểm tra", "Cơ bản"),
        ("Một mã sinh viên nộp lại nhiều lần cùng đề thi nên được xử lý thế nào?", "Chặn nộp lặp để đảm bảo công bằng", "Tự cộng thêm điểm", "Tạo đề thi mới", "Xóa toàn bộ kết quả", "Nền tảng kiểm tra", "Trung bình"),
        ("Giới hạn thời gian đề thi được dùng để làm gì?", "Kiểm soát thời lượng làm bài của sinh viên", "Tăng kích thước câu hỏi", "Đổi màu trình duyệt", "Tạo thêm tài khoản", "Nền tảng kiểm tra", "Cơ bản"),
        ("Báo cáo điểm số giúp giảng viên làm gì?", "Theo dõi kết quả từng sinh viên sau khi nộp bài", "Cài lại hệ điều hành", "Chỉnh độ phân giải màn hình", "Tạo mạng LAN mới", "Nền tảng kiểm tra", "Cơ bản"),
        ("Ghép câu hỏi thành đề thi nghĩa là gì?", "Chọn nhiều câu hỏi để tạo một bài kiểm tra hoàn chỉnh", "Đổi tên thư mục tải xuống", "Tăng âm lượng loa", "Nén file video", "Nền tảng kiểm tra", "Cơ bản"),
        ("Bốn mã nhóm thi nên được gán đề như thế nào?", "Mỗi mã nhóm nhận một bộ đề khác nhau", "Tất cả luôn dùng cùng một bộ đề", "Không cần mã phòng", "Chỉ giảng viên mới làm bài", "Nền tảng kiểm tra", "Trung bình"),
    ]
    return [make_seed_question(*row) for row in rows]


def get_sample_questions() -> list[dict[str, str]]:
    return get_seed_question_bank_questions()[:PRESET_QUESTIONS_PER_SET]

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


def serialize_question_bank_item(item: QuestionBankItem) -> dict[str, object]:
    return {
        "id": item.id,
        "content": item.content,
        "option_a": item.option_a,
        "option_b": item.option_b,
        "option_c": item.option_c,
        "option_d": item.option_d,
        "correct_option": item.correct_option,
        "category": item.category,
        "difficulty": item.difficulty,
        "created_at": item.created_at.strftime("%H:%M %d/%m/%Y") if item.created_at else "-",
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
        "question_bank": [],
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

    for item in QuestionBankItem.query.order_by(QuestionBankItem.id.asc()).all():
        payload["question_bank"].append(
            {
                "content": item.content,
                "option_a": item.option_a,
                "option_b": item.option_b,
                "option_c": item.option_c,
                "option_d": item.option_d,
                "correct_option": item.correct_option,
                "category": item.category,
                "difficulty": item.difficulty,
                "created_at": snapshot_datetime(item.created_at),
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
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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

    for item_data in payload.get("question_bank", []):
        created_at_raw = item_data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if created_at_raw
            else datetime.now(timezone.utc)
        )
        db.session.add(
            QuestionBankItem(
                content=item_data["content"],
                option_a=item_data["option_a"],
                option_b=item_data["option_b"],
                option_c=item_data["option_c"],
                option_d=item_data["option_d"],
                correct_option=item_data["correct_option"],
                category=item_data.get("category") or "Chung",
                difficulty=item_data.get("difficulty") or "Cơ bản",
                created_at=created_at,
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

    result_columns = {
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
        if column_name not in result_columns:
            db.session.execute(text(f"ALTER TABLE quiz_result ADD COLUMN {column_name} {definition}"))
            updated = True

    if updated:
        db.session.commit()


def fix_legacy_text(value: str | None) -> str | None:
    if value is None:
        return None
    return LEGACY_TEXT_FIXES.get(value, value)


def normalize_legacy_texts() -> bool:
    changed = False

    for teacher in TeacherUser.query.all():
        fixed_display_name = fix_legacy_text(teacher.display_name)
        if fixed_display_name != teacher.display_name:
            teacher.display_name = fixed_display_name or teacher.display_name
            changed = True

    for item in QuestionBankItem.query.all():
        fixed_content = fix_legacy_text(item.content)
        if fixed_content != item.content:
            item.content = fixed_content or item.content
            changed = True

    for quiz in Quiz.query.all():
        fixed_title = fix_legacy_text(quiz.title)
        if fixed_title != quiz.title:
            quiz.title = fixed_title or quiz.title
            changed = True

        for question in quiz.questions:
            fixed_content = fix_legacy_text(question.content)
            if fixed_content != question.content:
                question.content = fixed_content or question.content
                changed = True

    for result in QuizResult.query.all():
        fixed_student_name = fix_legacy_text(result.student_name)
        if fixed_student_name != result.student_name:
            result.student_name = fixed_student_name or result.student_name
            changed = True

        fixed_quiz_title = fix_legacy_text(result.quiz_title)
        if fixed_quiz_title != result.quiz_title:
            result.quiz_title = fixed_quiz_title or result.quiz_title
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


def seed_sample_question_bank() -> bool:
    changed = False
    for question_data in get_seed_question_bank_questions():
        if QuestionBankItem.query.filter_by(content=question_data["content"]).first():
            continue

        db.session.add(
            QuestionBankItem(
                content=question_data["content"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_option=question_data["correct_option"],
                category=question_data["category"],
                difficulty=question_data["difficulty"],
            )
        )
        changed = True

    if changed:
        db.session.commit()
    return changed


def seed_sample_data() -> bool:
    if Quiz.query.filter_by(join_code="NHOM02").first():
        return False
    seed_questions = get_seed_question_bank_questions()[:PRESET_QUESTIONS_PER_SET]

    quiz = Quiz(
        title="Kiểm tra Tin học đại cương",
        join_code="NHOM02",
        time_limit=PRESET_QUIZ_TIME_LIMIT,
    )
    db.session.add(quiz)
    db.session.flush()

    db.session.add_all(
        [
            Question(
                quiz_id=quiz.id,
                content=question_data["content"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_option=question_data["correct_option"],
            )
            for question_data in seed_questions
        ]
    )
    db.session.commit()
    return True


def sync_sample_quiz_if_needed() -> bool:
    quiz = Quiz.query.filter_by(join_code="NHOM02").first()
    if not quiz:
        return False

    sample_questions = get_seed_question_bank_questions()[:PRESET_QUESTIONS_PER_SET]
    if len(quiz.questions) >= len(sample_questions):
        return False

    quiz.title = "Kiểm tra Tin học đại cương"
    quiz.time_limit = max(quiz.time_limit, PRESET_QUIZ_TIME_LIMIT)

    for question in list(quiz.questions):
        db.session.delete(question)
    db.session.flush()

    db.session.add_all(
        [
            Question(
                quiz_id=quiz.id,
                content=question_data["content"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_option=question_data["correct_option"],
            )
            for question_data in sample_questions
        ]
    )
    db.session.commit()
    return True


def build_preset_question_sets(
    question_bank: list[dict[str, str]],
    set_count: int = PRESET_QUIZ_SET_COUNT,
    question_count: int = PRESET_QUESTIONS_PER_SET,
) -> list[list[dict[str, str]]]:
    if len(question_bank) < question_count:
        raise ValueError("Ngân hàng câu hỏi chưa đủ để tạo bộ đề mẫu.")

    used_signatures: set[tuple[str, ...]] = set()
    preset_sets: list[list[dict[str, str]]] = []

    for set_index in range(set_count):
        for attempt in range(50):
            rng = random.Random(PRESET_RANDOM_SEED + (set_index * 100) + attempt)
            selected_questions = rng.sample(question_bank, question_count)
            signature = tuple(sorted(question["content"] for question in selected_questions))
            if signature in used_signatures:
                continue

            used_signatures.add(signature)
            preset_sets.append(selected_questions)
            break

    if len(preset_sets) < set_count:
        raise ValueError("Không tạo đủ số bộ đề mẫu từ ngân hàng câu hỏi hiện tại.")

    return preset_sets


def upsert_quiz_from_seed_questions(
    join_code: str,
    title: str,
    time_limit: int,
    questions_payload: list[dict[str, str]],
) -> bool:
    quiz = Quiz.query.filter_by(join_code=join_code).first()
    created = False
    if quiz is None:
        quiz = Quiz(title=title, join_code=join_code, time_limit=time_limit)
        db.session.add(quiz)
        db.session.flush()
        created = True

    current_signature = sorted(question.content for question in quiz.questions)
    new_signature = sorted(question_data["content"] for question_data in questions_payload)
    if (
        not created
        and quiz.title == title
        and quiz.time_limit == time_limit
        and current_signature == new_signature
        and len(quiz.questions) == len(questions_payload)
    ):
        return False

    quiz.title = title
    quiz.time_limit = time_limit

    for result in quiz.results:
        result.quiz_title = title
        result.join_code = join_code

    for question in list(quiz.questions):
        db.session.delete(question)
    db.session.flush()

    db.session.add_all(
        [
            Question(
                quiz_id=quiz.id,
                content=question_data["content"],
                option_a=question_data["option_a"],
                option_b=question_data["option_b"],
                option_c=question_data["option_c"],
                option_d=question_data["option_d"],
                correct_option=question_data["correct_option"],
            )
            for question_data in questions_payload
        ]
    )
    return True


def ensure_preset_quiz_library() -> bool:
    question_bank = get_seed_question_bank_questions()
    preset_sets = build_preset_question_sets(question_bank)
    changed = False

    for set_index, set_questions in enumerate(preset_sets, start=1):
        changed = (
            upsert_quiz_from_seed_questions(
                join_code=PRESET_SET_JOIN_CODES[set_index - 1],
                title=f"Bộ đề {set_index:02d}",
                time_limit=PRESET_QUIZ_TIME_LIMIT,
                questions_payload=set_questions,
            )
            or changed
        )

    assigned_indices = random.Random(PRESET_RANDOM_SEED).sample(
        range(len(preset_sets)),
        len(GROUP_JOIN_CODES),
    )
    for group_code, set_index in zip(GROUP_JOIN_CODES, assigned_indices):
        set_number = set_index + 1
        changed = (
            upsert_quiz_from_seed_questions(
                join_code=group_code,
                title=f"Phòng thi {group_code} - Bộ đề {set_number:02d}",
                time_limit=PRESET_QUIZ_TIME_LIMIT,
                questions_payload=preset_sets[set_index],
            )
            or changed
        )

    if changed:
        db.session.commit()

    return changed


def normalize_preset_quiz_titles() -> bool:
    changed = False

    for set_index, join_code in enumerate(PRESET_SET_JOIN_CODES, start=1):
        quiz = Quiz.query.filter_by(join_code=join_code).first()
        expected_title = f"Bộ đề {set_index:02d}"
        if quiz and quiz.title != expected_title:
            quiz.title = expected_title
            for result in quiz.results:
                result.quiz_title = expected_title
            changed = True

    assigned_indices = random.Random(PRESET_RANDOM_SEED).sample(
        range(PRESET_QUIZ_SET_COUNT),
        len(GROUP_JOIN_CODES),
    )
    for group_code, set_index in zip(GROUP_JOIN_CODES, assigned_indices):
        quiz = Quiz.query.filter_by(join_code=group_code).first()
        expected_title = f"Phòng thi {group_code} - Bộ đề {set_index + 1:02d}"
        if quiz and quiz.title != expected_title:
            quiz.title = expected_title
            for result in quiz.results:
                result.quiz_title = expected_title
            changed = True

    if changed:
        db.session.commit()

    return changed


def prepare_question_payload(
    raw_question: dict[str, object],
    question_label: str,
) -> tuple[dict[str, str] | None, str | None]:
    content = str(raw_question.get("content") or "").strip()
    option_a = str(raw_question.get("option_a") or "").strip()
    option_b = str(raw_question.get("option_b") or "").strip()
    option_c = str(raw_question.get("option_c") or "").strip()
    option_d = str(raw_question.get("option_d") or "").strip()
    correct_option = str(raw_question.get("correct_option") or "").strip().upper()

    if not all([content, option_a, option_b, option_c, option_d]):
        return None, f"{question_label} chưa đủ nội dung và 4 đáp án."

    if correct_option not in {"A", "B", "C", "D"}:
        return None, f"{question_label} chưa chọn đáp án đúng hợp lệ."

    return (
        {
            "content": content,
            "option_a": option_a,
            "option_b": option_b,
            "option_c": option_c,
            "option_d": option_d,
            "correct_option": correct_option,
        },
        None,
    )


def validate_question_bank_payload(
    payload: dict[str, object],
) -> tuple[dict[str, str] | None, str | None]:
    prepared_question, error_message = prepare_question_payload(payload, "Câu hỏi trong ngân hàng")
    if error_message:
        return None, error_message

    category = " ".join(str(payload.get("category") or "").strip().split())[:80] or "Chung"
    difficulty = " ".join(str(payload.get("difficulty") or "").strip().split())[:30] or "Cơ bản"
    if difficulty not in QUESTION_DIFFICULTIES:
        return None, "Độ khó phải là Cơ bản, Trung bình hoặc Nâng cao."

    prepared_question["category"] = category
    prepared_question["difficulty"] = difficulty
    return prepared_question, None


def validate_questions_payload(
    questions_payload: list[dict[str, object]],
) -> tuple[list[dict[str, str]] | None, str | None]:
    if not questions_payload:
        return None, "Cần ít nhất 1 câu hỏi để tạo đề thi."

    prepared_questions: list[dict[str, str]] = []
    for index, raw_question in enumerate(questions_payload, start=1):
        prepared_question, error_message = prepare_question_payload(
            raw_question,
            f"Câu hỏi {index}",
        )
        if error_message:
            return None, error_message
        prepared_questions.append(prepared_question)

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
        AUTO_SEED_QUESTION_BANK=True,
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
                "question_bank_count": QuestionBankItem.query.count(),
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
        question_bank = [
            serialize_question_bank_item(item)
            for item in QuestionBankItem.query.order_by(QuestionBankItem.id.desc()).all()
        ]
        return render_template(
            "teacher_dashboard_v2.html",
            quizzes_data=quizzes,
            question_bank_data=question_bank,
            sample_join_code=GROUP_JOIN_CODES[0],
            sample_join_codes=GROUP_JOIN_CODES,
            teacher_name=session.get("teacher_display_name", "Giảng viên"),
            teacher_username=session.get("teacher_username", "giangvien"),
            storage_label=get_storage_label(),
            difficulty_options=QUESTION_DIFFICULTIES,
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

        already_submitted = False
        student_code = normalize_student_code(session.get("student_code"))
        if student_code:
            already_submitted = bool(
                QuizResult.query.filter_by(quiz_id=quiz.id, student_code=student_code).first()
            )

        return jsonify(
            {
                "status": "success",
                "data": {
                    "quiz_id": quiz.id,
                    "title": quiz.title,
                    "time_limit": quiz.time_limit,
                    "already_submitted": already_submitted,
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
        if not is_student_logged_in():
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Bạn cần đăng nhập sinh viên trước khi nộp bài.",
                    }
                ),
                401,
            )

        payload = request.get_json(silent=True) or {}
        join_code = normalize_join_code(payload.get("join_code"))
        student_name = normalize_person_name(session.get("student_name") or payload.get("student_name"))
        student_code = normalize_student_code(session.get("student_code") or payload.get("student_code"))
        cheat_count = parse_non_negative_int(payload.get("cheat_count"), default=0)
        user_answers = payload.get("answers") or {}

        if not student_code:
            return jsonify({"status": "error", "message": "Thiếu mã sinh viên."}), 400

        quiz = Quiz.query.filter_by(join_code=join_code).first()
        if not quiz:
            return jsonify({"status": "error", "message": "Mã phòng thi không hợp lệ."}), 404

        if not quiz.questions:
            return jsonify({"status": "error", "message": "Đề thi hiện chưa có câu hỏi."}), 400

        duplicate_result = QuizResult.query.filter_by(
            quiz_id=quiz.id,
            student_code=student_code,
        ).first()
        if duplicate_result:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Mã sinh viên này đã nộp bài cho đề thi này rồi.",
                    }
                ),
                409,
            )

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
            student_code=student_code,
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

    @app.route("/api/teacher/question-bank", methods=["GET"])
    @teacher_required(api=True)
    def get_question_bank():
        items = [
            serialize_question_bank_item(item)
            for item in QuestionBankItem.query.order_by(QuestionBankItem.id.desc()).all()
        ]
        return jsonify({"status": "success", "data": items})

    @app.route("/api/teacher/question-bank", methods=["POST"])
    @teacher_required(api=True)
    def create_question_bank_item():
        payload = request.get_json(silent=True) or {}
        prepared_question, error_message = validate_question_bank_payload(payload)
        if error_message:
            return jsonify({"status": "error", "message": error_message}), 400

        item = QuestionBankItem(**prepared_question)
        db.session.add(item)
        db.session.commit()
        save_snapshot()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Đã thêm câu hỏi vào ngân hàng.",
                    "data": serialize_question_bank_item(item),
                }
            ),
            201,
        )

    @app.route("/api/teacher/question-bank/<int:item_id>", methods=["PUT"])
    @teacher_required(api=True)
    def update_question_bank_item(item_id: int):
        item = db.get_or_404(QuestionBankItem, item_id)
        payload = request.get_json(silent=True) or {}
        prepared_question, error_message = validate_question_bank_payload(payload)
        if error_message:
            return jsonify({"status": "error", "message": error_message}), 400

        item.content = prepared_question["content"]
        item.option_a = prepared_question["option_a"]
        item.option_b = prepared_question["option_b"]
        item.option_c = prepared_question["option_c"]
        item.option_d = prepared_question["option_d"]
        item.correct_option = prepared_question["correct_option"]
        item.category = prepared_question["category"]
        item.difficulty = prepared_question["difficulty"]
        db.session.commit()
        save_snapshot()
        return jsonify(
            {
                "status": "success",
                "message": "Đã cập nhật câu hỏi trong ngân hàng.",
                "data": serialize_question_bank_item(item),
            }
        )

    @app.route("/api/teacher/question-bank/<int:item_id>", methods=["DELETE"])
    @teacher_required(api=True)
    def delete_question_bank_item(item_id: int):
        item = db.get_or_404(QuestionBankItem, item_id)
        db.session.delete(item)
        db.session.commit()
        save_snapshot()
        return jsonify({"status": "success", "message": "Đã xóa câu hỏi khỏi ngân hàng."})

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
        seeded_bank = seed_sample_question_bank()
        seeded_quiz = seed_sample_data()
        synced_demo_quiz = sync_sample_quiz_if_needed()
        preset_quiz_library_ready = ensure_preset_quiz_library()
        normalized_preset_titles = normalize_preset_quiz_titles()
        if (
            created_teacher
            or seeded_bank
            or seeded_quiz
            or synced_demo_quiz
            or preset_quiz_library_ready
            or normalized_preset_titles
        ):
            save_snapshot()
        return jsonify(
            {
                "status": "success",
                "seeded_teacher": created_teacher,
                "seeded_question_bank": seeded_bank,
                "seeded_quiz": seeded_quiz,
                "synced_demo_quiz": synced_demo_quiz,
                "preset_quiz_library_ready": preset_quiz_library_ready,
                "normalized_preset_titles": normalized_preset_titles,
                "join_codes": GROUP_JOIN_CODES,
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
        seeded_bank = False
        if app.config.get("AUTO_SEED_QUESTION_BANK", True):
            seeded_bank = seed_sample_question_bank()
        seeded_quiz = False
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True) and not Quiz.query.first():
            seeded_quiz = seed_sample_data()
        synced_demo_quiz = False
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True):
            synced_demo_quiz = sync_sample_quiz_if_needed()
        preset_quiz_library_ready = False
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True):
            preset_quiz_library_ready = ensure_preset_quiz_library()
        normalized_preset_titles = False
        if app.config.get("AUTO_SEED_SAMPLE_DATA", True):
            normalized_preset_titles = normalize_preset_quiz_titles()

        if (
            normalized_legacy
            or seeded_teacher
            or seeded_bank
            or seeded_quiz
            or synced_demo_quiz
            or preset_quiz_library_ready
            or normalized_preset_titles
        ):
            save_snapshot()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)

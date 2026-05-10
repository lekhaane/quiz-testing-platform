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
    "ThÃ­ sinh tá»± do": "Thí sinh tự do",
    "Kiá»ƒm tra Tin há»c Ä‘áº¡i cÆ°Æ¡ng": "Kiểm tra Tin học đại cương",
    "ÄÆ¡n vá»‹ nhá» nháº¥t cá»§a thÃ´ng tin lÃ  gÃ¬?": "Đơn vị nhỏ nhất của thông tin là gì?",
    "Pháº§n cá»©ng mÃ¡y tÃ­nh gá»i lÃ  gÃ¬?": "Phần cứng máy tính gọi là gì?",
    "Tá»• há»£p phÃ­m dÃ¹ng Ä‘á»ƒ sao chÃ©p ná»™i dung lÃ  gÃ¬?": "Tổ hợp phím dùng để sao chép nội dung là gì?",
    "Giáº£ng viÃªn máº·c Ä‘á»‹nh": "Giảng viên mặc định",
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


def get_sample_questions() -> list[dict[str, str]]:
    return [
        {
            "content": "Đơn vị nhỏ nhất của thông tin là gì?",
            "option_a": "Byte",
            "option_b": "Bit",
            "option_c": "MB",
            "option_d": "GB",
            "correct_option": "B",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Phần cứng máy tính gọi là gì?",
            "option_a": "Software",
            "option_b": "Firmware",
            "option_c": "Hardware",
            "option_d": "Malware",
            "correct_option": "C",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Tổ hợp phím dùng để sao chép nội dung là gì?",
            "option_a": "Ctrl+V",
            "option_b": "Ctrl+X",
            "option_c": "Ctrl+A",
            "option_d": "Ctrl+C",
            "correct_option": "D",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Thiết bị nào dùng để nhập dữ liệu vào máy tính?",
            "option_a": "Màn hình",
            "option_b": "Bàn phím",
            "option_c": "Loa",
            "option_d": "Máy in",
            "correct_option": "B",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Bộ nhớ RAM dùng để làm gì?",
            "option_a": "Lưu trữ tạm thời dữ liệu khi máy đang chạy",
            "option_b": "Lưu trữ vĩnh viễn hệ điều hành",
            "option_c": "Kết nối Internet",
            "option_d": "Điều khiển chuột",
            "correct_option": "A",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Phần mở rộng phổ biến của tệp văn bản Word là gì?",
            "option_a": ".xlsx",
            "option_b": ".pptx",
            "option_c": ".docx",
            "option_d": ".jpg",
            "correct_option": "C",
            "category": "Tin học đại cương",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Địa chỉ IP dùng để làm gì trong mạng máy tính?",
            "option_a": "Xác định thiết bị trên mạng",
            "option_b": "Tăng tốc độ gõ bàn phím",
            "option_c": "Lưu trữ dữ liệu lâu dài",
            "option_d": "Nén hình ảnh",
            "correct_option": "A",
            "category": "Mạng máy tính",
            "difficulty": "Trung bình",
        },
        {
            "content": "Thiết bị nào thường dùng để kết nối nhiều máy tính trong cùng mạng LAN?",
            "option_a": "Switch",
            "option_b": "Scanner",
            "option_c": "Projector",
            "option_d": "UPS",
            "correct_option": "A",
            "category": "Mạng máy tính",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Giao thức HTTP chủ yếu dùng để làm gì?",
            "option_a": "Truy cập và truyền tải nội dung web",
            "option_b": "Điều khiển chuột không dây",
            "option_c": "Sạc pin laptop",
            "option_d": "Nén cơ sở dữ liệu",
            "correct_option": "A",
            "category": "Mạng máy tính",
            "difficulty": "Trung bình",
        },
        {
            "content": "Trong cơ sở dữ liệu quan hệ, bảng dùng để làm gì?",
            "option_a": "Lưu trữ dữ liệu theo hàng và cột",
            "option_b": "Chạy chương trình Java",
            "option_c": "Vẽ sơ đồ mạng",
            "option_d": "Tăng tốc trình duyệt",
            "correct_option": "A",
            "category": "Cơ sở dữ liệu",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Khóa chính (Primary Key) có vai trò gì?",
            "option_a": "Phân biệt duy nhất mỗi bản ghi",
            "option_b": "Ẩn toàn bộ bảng dữ liệu",
            "option_c": "Tăng âm lượng máy tính",
            "option_d": "Tự động xóa dữ liệu trùng",
            "correct_option": "A",
            "category": "Cơ sở dữ liệu",
            "difficulty": "Trung bình",
        },
        {
            "content": "Câu lệnh SQL nào dùng để lấy dữ liệu từ bảng?",
            "option_a": "INSERT",
            "option_b": "UPDATE",
            "option_c": "SELECT",
            "option_d": "DELETE",
            "correct_option": "C",
            "category": "Cơ sở dữ liệu",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Trong lập trình, biến dùng để làm gì?",
            "option_a": "Lưu trữ giá trị để sử dụng trong chương trình",
            "option_b": "Xóa hệ điều hành",
            "option_c": "Tăng kích thước màn hình",
            "option_d": "Kết nối Wi-Fi",
            "correct_option": "A",
            "category": "Lập trình cơ bản",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Cấu trúc lặp dùng để làm gì?",
            "option_a": "Lặp lại một khối lệnh nhiều lần",
            "option_b": "Tắt chương trình ngay lập tức",
            "option_c": "Chỉ khai báo biến số thực",
            "option_d": "Lưu ảnh lên máy in",
            "correct_option": "A",
            "category": "Lập trình cơ bản",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Điều kiện if-else trong lập trình dùng để làm gì?",
            "option_a": "Rẽ nhánh xử lý theo điều kiện",
            "option_b": "Tạo kết nối mạng LAN",
            "option_c": "Lưu dữ liệu vào RAM vĩnh viễn",
            "option_d": "Mở file PDF",
            "correct_option": "A",
            "category": "Lập trình cơ bản",
            "difficulty": "Cơ bản",
        },
        {
            "content": "Mảng (array) thường được dùng để làm gì?",
            "option_a": "Lưu nhiều giá trị cùng kiểu dữ liệu",
            "option_b": "Tạo tài khoản email",
            "option_c": "Phát nhạc nền",
            "option_d": "Mã hóa địa chỉ IP",
            "correct_option": "A",
            "category": "Lập trình cơ bản",
            "difficulty": "Trung bình",
        },
        {
            "content": "Thuật toán là gì?",
            "option_a": "Tập hữu hạn các bước giải quyết một bài toán",
            "option_b": "Một loại phần cứng của máy tính",
            "option_c": "Tên của trình duyệt web",
            "option_d": "Thiết bị kết nối Internet",
            "correct_option": "A",
            "category": "Thuật toán",
            "difficulty": "Trung bình",
        },
    ]


def get_seed_question_bank_questions() -> list[dict[str, str]]:
    questions = list(get_sample_questions())
    questions.extend(
        [
            {
                "content": "Thiáº¿t bá»‹ nÃ o dÃ¹ng Ä‘á»ƒ hiá»ƒn thá»‹ hÃ¬nh áº£nh tá»« mÃ¡y tÃ­nh?",
                "option_a": "MÃ¡y in",
                "option_b": "MÃ n hÃ¬nh",
                "option_c": "Scanner",
                "option_d": "USB",
                "correct_option": "B",
                "category": "Tin há»c Ä‘áº¡i cÆ°Æ¡ng",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Há»‡ Ä‘iá»u hÃ nh cÃ³ chá»©c nÄƒng chÃ­nh nÃ o?",
                "option_a": "Quáº£n lÃ½ tÃ i nguyÃªn vÃ  Ä‘iá»u phá»‘i hoáº¡t Ä‘á»™ng mÃ¡y tÃ­nh",
                "option_b": "Chá»‰ dÃ¹ng Ä‘á»ƒ gá»­i email",
                "option_c": "Chá»‰ dÃ¹ng Ä‘á»ƒ váº½ hÃ¬nh",
                "option_d": "Chá»‰ dÃ¹ng Ä‘á»ƒ in áº¥n",
                "correct_option": "A",
                "category": "Tin há»c Ä‘áº¡i cÆ°Æ¡ng",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Bá»™ xá»­ lÃ½ trung tÃ¢m cá»§a mÃ¡y tÃ­nh lÃ  gÃ¬?",
                "option_a": "RAM",
                "option_b": "CPU",
                "option_c": "SSD",
                "option_d": "GPU",
                "correct_option": "B",
                "category": "Tin há»c Ä‘áº¡i cÆ°Æ¡ng",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Thiáº¿t bá»‹ nÃ o thÆ°á»ng dÃ¹ng Ä‘á»ƒ lÆ°u trá»¯ dá»¯ liá»‡u lÃ¢u dÃ i?",
                "option_a": "RAM",
                "option_b": "Cache",
                "option_c": "SSD",
                "option_d": "Register",
                "correct_option": "C",
                "category": "Tin há»c Ä‘áº¡i cÆ°Æ¡ng",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "DNS cÃ³ nhiá»‡m vá»¥ gÃ¬?",
                "option_a": "PhÃ¢n giáº£i tÃªn miá»n thÃ nh Ä‘á»‹a chá»‰ IP",
                "option_b": "MÃ£ hÃ³a toÃ n bá»™ á»• cÃ¡m",
                "option_c": "Sáº¡c pin laptop",
                "option_d": "Chá»‘ng rung chuá»™t",
                "correct_option": "A",
                "category": "Máº¡ng mÃ¡y tÃ­nh",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Router thÆ°á»ng dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Äá»‹nh tuyáº¿n dá»¯ liá»‡u giá»¯a cÃ¡c máº¡ng",
                "option_b": "In tÃ i liá»‡u",
                "option_c": "Chá»¥p áº£nh webcam",
                "option_d": "TÄƒng Ã¢m lÆ°á»£ng loa",
                "correct_option": "A",
                "category": "Máº¡ng mÃ¡y tÃ­nh",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "MÃ´ hÃ¬nh client-server mÃ´ táº£ Ä‘iá»u gÃ¬?",
                "option_a": "Sá»± trao Ä‘á»•i giá»¯a mÃ¡y cung cáº¥p vÃ  mÃ¡y yÃªu cáº§u dá»‹ch vá»¥",
                "option_b": "CÃ¡ch vÄƒn báº£n Ä‘Æ°á»£c in ra giáº¥y",
                "option_c": "QuÃ¡ trÃ¬nh nÃ©n áº£nh JPG",
                "option_d": "Cáº¥u táº¡o cá»§a pin laptop",
                "correct_option": "A",
                "category": "Máº¡ng mÃ¡y tÃ­nh",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Firewall dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Lá»c vÃ  kiá»ƒm soÃ¡t lÆ°u lÆ°á»£ng máº¡ng",
                "option_b": "Táº¡o slide thuyáº¿t trÃ¬nh",
                "option_c": "LÆ°u file PDF",
                "option_d": "Táº¡o báº£ng tÃ­nh",
                "correct_option": "A",
                "category": "Báº£o máº­t",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Lá»‡nh SQL nÃ o dÃ¹ng Ä‘á»ƒ thÃªm báº£n ghi má»›i?",
                "option_a": "SELECT",
                "option_b": "INSERT",
                "option_c": "DROP",
                "option_d": "ALTER",
                "correct_option": "B",
                "category": "CÆ¡ sá»Ÿ dá»¯ liá»‡u",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Lá»‡nh SQL nÃ o dÃ¹ng Ä‘á»ƒ cáº­p nháº­t dá»¯ liá»‡u?",
                "option_a": "UPDATE",
                "option_b": "SELECT",
                "option_c": "COUNT",
                "option_d": "RENAME",
                "correct_option": "A",
                "category": "CÆ¡ sá»Ÿ dá»¯ liá»‡u",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "MÃ³i quan há»‡ 1-n trong CSDL nghÄ©a lÃ  gÃ¬?",
                "option_a": "Má»™t báº£n ghi á»Ÿ báº£ng A liÃªn káº¿t vá»›i nhiá»u báº£n ghi á»Ÿ báº£ng B",
                "option_b": "Má»i báº£ng chá»‰ cÃ³ má»™t cá»™t",
                "option_c": "KhÃ´ng thá»ƒ cÃ³ khÃ³a ngoáº¡i",
                "option_d": "KhÃ´ng thá»ƒ cÃ³ truy váº¥n",
                "correct_option": "A",
                "category": "CÆ¡ sá»Ÿ dá»¯ liá»‡u",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "KhÃ³a ngoáº¡i (Foreign Key) dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "LiÃªn káº¿t dá»¯ liá»‡u giá»¯a cÃ¡c báº£ng",
                "option_b": "XÃ³a táº¥t cáº£ báº£ng",
                "option_c": "Äáº·t máº­t kháº©u cho CSDL",
                "option_d": "Táº¡o file backup PDF",
                "correct_option": "A",
                "category": "CÆ¡ sá»Ÿ dá»¯ liá»‡u",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "HÃ m COUNT() trong SQL dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Äáº¿m sá»‘ báº£n ghi",
                "option_b": "Sáº¯p xáº¿p táº£ng dáº§n",
                "option_c": "XÃ³a báº£ng",
                "option_d": "Thay Ä‘á»•i tÃªn cá»™t",
                "correct_option": "A",
                "category": "CÆ¡ sá»Ÿ dá»¯ liá»‡u",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "HÃ m trong láº­p trÃ¬nh dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "ÄÃ³ng gÃ³i má»™t nhÃ³m lá»‡nh cÃ³ thá»ƒ tÃ¡i sá»­ dá»¥ng",
                "option_b": "Táº¯t mÃ¡y tÃ­nh",
                "option_c": "NÃ©n file áº£nh",
                "option_d": "Cáº¯m USB",
                "correct_option": "A",
                "category": "Láº­p trÃ¬nh cÆ¡ báº£n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Kiá»ƒu dá»¯ liá»‡u boolean thÆ°á»ng chá»©a giÃ¡ trá»‹ nÃ o?",
                "option_a": "True/False",
                "option_b": "1/2/3",
                "option_c": "A/B/C",
                "option_d": "ngÃ y/thÃ¡ng/nÄƒm",
                "correct_option": "A",
                "category": "Láº­p trÃ¬nh cÆ¡ báº£n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "ToÃ¡n tá»­ so sÃ¡nh dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "So sÃ¡nh hai giÃ¡ trá»‹",
                "option_b": "Náº¡p pin laptop",
                "option_c": "Má»Ÿ trÃ¬nh duyá»‡t",
                "option_d": "Chá»¥p áº£nh webcam",
                "correct_option": "A",
                "category": "Láº­p trÃ¬nh cÆ¡ báº£n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Thuáº­t toÃ¡n tÃ¬m kiáº¿m tuyáº¿n tÃ­nh hoáº¡t Ä‘á»™ng nhÆ° tháº¿ nÃ o?",
                "option_a": "Duyá»‡t láº§n lÆ°á»£t tá»«ng pháº§n tá»­ Ä‘á»ƒ tÃ¬m giáº£ trá»‹",
                "option_b": "LuÃ´n chia Ä‘Ã´i máº£ng",
                "option_c": "Chá»‰ dÃ¹ng cho cÃ¢y",
                "option_d": "Chá»‰ dÃ¹ng cho Ä‘á»“ há»a",
                "correct_option": "A",
                "category": "Thuáº­t toÃ¡n",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Thuáº­t toÃ¡n sáº¯p xáº¿p dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Sáº¯p xáº¿p dá»¯ liá»‡u theo thá»© tá»± mong muá»‘n",
                "option_b": "XÃ³a táº¥t cáº£ file",
                "option_c": "Káº¿t ná»‘i wifi",
                "option_d": "NÃ©n file video",
                "correct_option": "A",
                "category": "Thuáº­t toÃ¡n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Big O dÃ¹ng Ä‘á»ƒ mÃ´ táº£ Ä‘iá»u gÃ¬?",
                "option_a": "Äá»™ phá»©c táº¡p thá»i gian hoáº·c bá»™ nhá»› cá»§a thuáº­t toÃ¡n",
                "option_b": "KÃ­ch thÆ°á»›c mÃ n hÃ¬nh",
                "option_c": "Dung lÆ°á»£ng pin",
                "option_d": "Tá»‘c Ä‘á»™ chuá»™t",
                "correct_option": "A",
                "category": "Thuáº­t toÃ¡n",
                "difficulty": "NÃ¢ng cao",
            },
            {
                "content": "HTML chá»§ yáº¿u dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Táº¡o cáº¥u trÃºc trang web",
                "option_b": "Quáº£n lÃ½ CSDL quan há»‡",
                "option_c": "MÃ£ hÃ³a file exe",
                "option_d": "Äiá»u khiá»ƒn router",
                "correct_option": "A",
                "category": "Web cÆ¡ báº£n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "CSS chá»§ yáº¿u dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Äá»‹nh dáº¡ng giao diá»‡n trang web",
                "option_b": "Khá»Ÿi Ä‘á»™ng mÃ¡y chá»§",
                "option_c": "Táº¡o khÃ³a chÃ­nh",
                "option_d": "Xá»­ lÃ½ truy váº¥n SQL",
                "correct_option": "A",
                "category": "Web cÆ¡ báº£n",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "JavaScript trÃªn web thÆ°á»ng dÃ¹ng Ä‘á»ƒ lÃ m gÃ¬?",
                "option_a": "Xá»­ lÃ½ tÆ°Æ¡ng tÃ¡c vÃ  logic trÃªn giao diá»‡n",
                "option_b": "Thay pin mÃ¡y tÃ­nh",
                "option_c": "Táº¡o cÃ¡p máº¡ng",
                "option_d": "Sá»­a loa",
                "correct_option": "A",
                "category": "Web cÆ¡ báº£n",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "HTTPS khÃ¡c HTTP á»Ÿ Ä‘iá»ƒm nÃ o?",
                "option_a": "HTTPS cÃ³ mÃ£ hÃ³a dá»¯ liá»‡u truyá»n táº£i",
                "option_b": "HTTPS khÃ´ng dÃ¹ng trÃªn web",
                "option_c": "HTTPS chá»‰ dÃ¹ng cho email",
                "option_d": "HTTPS lÃ  há»‡ Ä‘iá»u hÃ nh",
                "correct_option": "A",
                "category": "Báº£o máº­t",
                "difficulty": "Trung bÃ¬nh",
            },
            {
                "content": "Máº­t kháº©u máº¡nh thÆ°á»ng nÃªn cÃ³ Ä‘iá»u gÃ¬?",
                "option_a": "Chá»¯ hoa, chá»¯ thÆ°á»ng, sá»‘ vÃ  kÃ½ tá»± Ä‘áº·c biá»‡t",
                "option_b": "Chá»‰ cÃ³ tÃªn cá»§a ngÆ°á»i dÃ¹ng",
                "option_c": "Chá»‰ cÃ³ 4 kÃ½ tá»±",
                "option_d": "LuÃ´n lÃ  123456",
                "correct_option": "A",
                "category": "Báº£o máº­t",
                "difficulty": "CÆ¡ báº£n",
            },
            {
                "content": "Phishing lÃ  hÃ¬nh thá»©c táº¥n cÃ´ng nÃ o?",
                "option_a": "Lá»«a ngÆ°á»i dÃ¹ng cung cáº¥p thÃ´ng tin nháº¡y cáº£m",
                "option_b": "Táº£i pin nhanh hÆ¡n",
                "option_c": "NÃ©n file cá»±c Ä‘áº¡i",
                "option_d": "TÄƒng sá»‘ lÆ°á»£ng RAM",
                "correct_option": "A",
                "category": "Báº£o máº­t",
                "difficulty": "Trung bÃ¬nh",
            },
        ]
    )
    return questions


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
        raise ValueError("KhÃ´ng táº¡o Ä‘á»§ sá»‘ bá»™ Ä‘á» máº«u tá»« ngÃ¢n hÃ ng cÃ¢u há»i hiá»‡n táº¡i.")

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
                title=f"Bá»™ Ä‘á» {set_index:02d}",
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
                title=f"PhÃ²ng thi {group_code} - Bá»™ Ä‘á» {set_number:02d}",
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
        expected_title = f"Bo de {set_index:02d}"
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
        expected_title = f"Phong thi {group_code} - Bo de {set_index + 1:02d}"
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

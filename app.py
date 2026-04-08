from quiz_platform_app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

"""
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# Cấu hình hiển thị tiếng Việt và Database
app.json.ensure_ascii = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# PHẦN 1: THIẾT KẾ CƠ SỞ DỮ LIỆU (MODELS)
# ==========================================

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    join_code = db.Column(db.String(10), unique=True, nullable=False) # Mã phòng thi
    time_limit = db.Column(db.Integer, default=15)
    questions = db.relationship('Question', backref='quiz', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)

class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100), default="Thí sinh tự do")
    quiz_title = db.Column(db.String(100))
    score = db.Column(db.Float)
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# PHẦN 2: ĐIỀU HƯỚNG GIAO DIỆN (ROUTES)
# ==========================================

@app.route('/')
def index():
    # Trang nhập mã phòng thi
    return render_template('dashboard.html')

@app.route('/quiz-room/<join_code>')
def quiz_room(join_code):
    # Trang làm bài thi thực tế
    quiz = Quiz.query.filter_by(join_code=join_code.upper()).first_or_404()
    return render_template('index.html', join_code=join_code)

# ==========================================
# PHẦN 3: CÁC API XỬ LÝ DỮ LIỆU
# ==========================================

# 1. Kiểm tra mã phòng thi
@app.route('/api/check-room/<code>')
def check_room(code):
    quiz = Quiz.query.filter_by(join_code=code.upper()).first()
    if quiz:
        return jsonify({"status": "success", "quiz_id": quiz.id})
    return jsonify({"status": "error", "message": "Mã phòng thi không tồn tại!"})

# 2. Lấy bộ câu hỏi dựa trên mã phòng
@app.route('/api/get-quiz/<code>')
def get_quiz(code):
    quiz = Quiz.query.filter_by(join_code=code.upper()).first()
    if not quiz:
        return jsonify({"status": "error", "message": "Không tìm thấy đề thi"})

    questions_data = []
    for q in quiz.questions:
        questions_data.append({
            "id": q.id,
            "content": q.content,
            "options": {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
        })

    return jsonify({
        "status": "success",
        "data": {
            "title": quiz.title,
            "time_limit": quiz.time_limit,
            "questions": questions_data
        }
    })

# 3. Chấm điểm và lưu kết quả
@app.route('/api/submit-quiz', methods=['POST'])
def submit_quiz():
    data = request.json
    join_code = data.get('join_code')
    user_answers = data.get('answers')
    
    quiz = Quiz.query.filter_by(join_code=join_code.upper()).first()
    if not quiz: return jsonify({"status": "error"})

    correct_count = 0
    details = []
    
    for q in quiz.questions:
        u_ans = user_answers.get(str(q.id))
        is_correct = (u_ans == q.correct_option)
        if is_correct: correct_count += 1
        
        details.append({
            "question": q.content,
            "your_answer": u_ans,
            "correct_answer": q.correct_option,
            "is_correct": is_correct
        })

    score = round((correct_count / len(quiz.questions)) * 10, 2)
    
    # Lưu kết quả vào Database để giáo viên xem
    new_result = QuizResult(quiz_title=quiz.title, score=score)
    db.session.add(new_result)
    db.session.commit()

    return jsonify({
        "status": "success",
        "score": score,
        "correct_count": correct_count,
        "total": len(quiz.questions),
        "details": details
    })

# 4. Khởi tạo dữ liệu mẫu cho Nhóm 02
@app.route('/api/init-all')
def init_all():
    with app.app_context():
        db.create_all()
        if not Quiz.query.filter_by(join_code="NHOM02").first():
            # Tạo đề thi mẫu
            quiz = Quiz(title="Kiểm tra Tin học Đại cương", join_code="NHOM02", time_limit=10)
            db.session.add(quiz)
            db.session.commit()
            
            # Thêm câu hỏi
            db.session.add_all([
                Question(quiz_id=quiz.id, content="Đơn vị nhỏ nhất của thông tin là?", 
                         option_a="Byte", option_b="Bit", option_c="MB", option_d="GB", correct_option="B"),
                Question(quiz_id=quiz.id, content="Phần cứng máy tính gọi là gì?", 
                         option_a="Software", option_b="Firmware", option_c="Hardware", option_d="Malware", correct_option="C"),
                Question(quiz_id=quiz.id, content="Tổ hợp phím Copy là gì?", 
                         option_a="Ctrl+V", option_b="Ctrl+X", option_c="Ctrl+A", option_d="Ctrl+C", correct_option="D")
            ])
            db.session.commit()
    return "Hệ thống đã sẵn sàng! Mã phòng thi của bạn là: NHOM02"

if __name__ == '__main__':
    app.run(debug=True)
"""

# Quiz and Testing Platform

Ứng dụng web Flask cho bài toán trắc nghiệm và kiểm tra trực tuyến.

## Chức năng chính

- Sinh viên đăng nhập bằng họ tên và mã sinh viên trước khi vào hệ thống.
- Sinh viên nhập `Join Code` để vào phòng thi.
- Làm bài trắc nghiệm có `Timer` đếm ngược.
- Nộp bài và xem kết quả chi tiết ngay lập tức.
- Ghi nhận chống gian lận cơ bản khi rời khỏi màn hình thi.
- Giảng viên tạo đề thi, quản lý câu hỏi và xem bảng điểm.

## Trang chính

- `/`: Điều hướng tới đăng nhập sinh viên hoặc trang sinh viên nếu đã đăng nhập.
- `/student/login`: Trang đăng nhập sinh viên.
- `/student`: Trang sinh viên sau khi đăng nhập.
- `/quiz-room/<join_code>`: Trang làm bài.
- `/teacher`: Trang giảng viên.
- `/health`: Kiểm tra trạng thái app.

## Chạy dự án

```powershell
python -m pip install -r requirements.txt
python app.py
```

Sau đó mở trình duyệt tại:

- `http://127.0.0.1:5000/`

## Dữ liệu demo

Hệ thống tự seed đề thi mẫu với mã phòng:

- `NHOM02`

## Lưu trữ dữ liệu

- Mặc định: app ưu tiên SQLite file tại `instance/quiz_platform.db`.
- Nếu môi trường không cho ghi file SQLite, app sẽ tự rơi về chế độ bộ nhớ + snapshot tại `instance/quiz_snapshot.json`.
- Nếu muốn dùng database riêng: đặt biến môi trường `QUIZ_DATABASE_URI` hoặc `DATABASE_URL`.

Ví dụ SQLite file:

```powershell
$env:QUIZ_DATABASE_URI="sqlite:///quiz_platform.db"
python app.py
```

Ví dụ PostgreSQL:

```powershell
$env:QUIZ_DATABASE_URI="postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"
python app.py
```

## Deploy lên Render

Project đã có sẵn:

- `render.yaml`: cấu hình Web Service + PostgreSQL cho Render
- `wsgi.py`: entrypoint production cho Gunicorn
- `.python-version`: ghim Python 3.13 để gần với môi trường local

Các bước:

1. Đưa source code lên GitHub.
2. Đăng nhập Render và chọn tạo mới bằng `Blueprint`.
3. Chọn repository chứa project này.
4. Render sẽ đọc `render.yaml`, tự tạo web service và PostgreSQL.
5. Sau khi deploy xong, mở domain Render cấp sẵn để dùng.

Lưu ý:

- Start command production đang là `gunicorn --bind 0.0.0.0:$PORT wsgi:app`.
- Khi dùng Render, app sẽ lấy database từ `QUIZ_DATABASE_URI` được nối với PostgreSQL trong `render.yaml`.
- Có thể đổi tài khoản giảng viên mặc định sau khi deploy để an toàn hơn.

## Kiểm thử

```powershell
python -m unittest -v test_quiz_platform.py
```

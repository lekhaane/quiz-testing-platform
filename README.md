# Quiz and Testing Platform

Ứng dụng web Flask cho bài toán trắc nghiệm và kiểm tra trực tuyến. Dự án hỗ trợ giảng viên quản lý ngân hàng câu hỏi, ghép câu hỏi thành đề thi, tạo mã phòng thi, giới hạn thời gian làm bài và tự động thu thập điểm số.

## Chức năng chính

- Sinh viên đăng nhập bằng họ tên và mã sinh viên trước khi vào hệ thống.
- Sinh viên nhập mã phòng thi để vào đúng bài kiểm tra.
- Làm bài trắc nghiệm với đồng hồ đếm ngược.
- Tự động chấm điểm và hiển thị kết quả minh bạch sau khi nộp bài.
- Ghi nhận chống gian lận cơ bản khi sinh viên rời khỏi cửa sổ làm bài.
- Giảng viên quản lý ngân hàng câu hỏi, tạo đề thi, gán thời gian và xem bảng điểm.
- Hệ thống có sẵn 20 bộ đề, mỗi bộ 20 câu; 4 mã nhóm `NHOM01` đến `NHOM04` được gán 4 bộ đề khác nhau.

## Trang chính

- `/`: Điều hướng tới trang sinh viên.
- `/student/login`: Trang đăng nhập sinh viên.
- `/student`: Trang nhập mã phòng thi sau khi đăng nhập.
- `/quiz-room/<join_code>`: Trang làm bài trắc nghiệm.
- `/teacher/login`: Trang đăng nhập giảng viên.
- `/teacher`: Dashboard giảng viên.
- `/health`: Kiểm tra trạng thái ứng dụng.

## Chạy dự án

```powershell
python -m pip install -r requirements.txt
python app.py
```

Sau đó mở trình duyệt tại:

```text
http://127.0.0.1:5000/
```

## Tài khoản demo

- Tài khoản giảng viên: `giangvien`
- Mật khẩu: `123456`
- Mã nhóm sinh viên: `NHOM01`, `NHOM02`, `NHOM03`, `NHOM04`

## Lưu trữ dữ liệu

- Mặc định local: SQLite tại `instance/quiz_platform.db`.
- Khi deploy Render: PostgreSQL được cấu hình trong `render.yaml`.
- Có thể đặt `QUIZ_DATABASE_URI` hoặc `DATABASE_URL` nếu muốn dùng database riêng.

Ví dụ SQLite:

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

Dự án đã có sẵn:

- `render.yaml`: Cấu hình Web Service và PostgreSQL cho Render.
- `wsgi.py`: Entrypoint production cho Gunicorn.
- `.python-version`: Ghim phiên bản Python.

Các bước triển khai:

1. Đẩy source code lên GitHub.
2. Đăng nhập Render và tạo Blueprint mới.
3. Chọn repository của dự án.
4. Render sẽ đọc `render.yaml`, tự tạo Web Service và PostgreSQL.
5. Sau khi deploy xong, mở domain Render cấp để sử dụng.

Start command production:

```text
gunicorn --bind 0.0.0.0:$PORT wsgi:app
```

## Kiểm thử

```powershell
python -m unittest -v test_quiz_platform.py test_quiz_platform_features.py
```

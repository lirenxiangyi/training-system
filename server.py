#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冉鹏工作室 - 考试服务器 v2.19.0
管理员电脑当服务器，学员通过局域网IP参加考试
成绩实时汇总到服务器，无需手动导入回传码

使用方法：双击「启动考试服务器.bat」或运行 python server.py
"""

import http.server
import json
import os
import random
import socket
import threading
import webbrowser
from datetime import datetime
from urllib.parse import urlparse

PORT = 8080
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DATA_DIR, 'server_data.json')


class ExamServer:
    """考试服务器数据管理"""

    def __init__(self):
        self.students = []      # 学员列表（管理员同步过来的）
        self.exams = []         # 考试列表
        self.questions = []      # 题库
        self.levels = []        # 级别
        self.published_exam_id = None  # 当前发布的考试ID
        self.scores = []        # 已提交的成绩
        self.sign_ins = []      # 签到记录
        self._load()

    def _load(self):
        """从文件加载历史数据"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.students = data.get('students', [])
                self.exams = data.get('exams', [])
                self.questions = data.get('questions', [])
                self.levels = data.get('levels', [])
                self.published_exam_id = data.get('published_exam_id', None)
                # 加载历史成绩（如果发布新考试，需要清空）
                self.scores = data.get('scores', [])
                self.sign_ins = data.get('sign_ins', [])
            except Exception as e:
                print(f"  [警告] 加载历史数据失败: {e}")

    def _save(self):
        """保存数据到文件"""
        try:
            data = {
                'students': self.students,
                'exams': self.exams,
                'questions': self.questions,
                'levels': self.levels,
                'published_exam_id': self.published_exam_id,
                'scores': self.scores,
                'sign_ins': self.sign_ins
            }
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [错误] 保存数据失败: {e}")

    def sync_from_admin(self, admin_data):
        """管理员同步数据到服务器"""
        self.students = admin_data.get('students', [])
        self.exams = admin_data.get('exams', [])
        self.questions = admin_data.get('questions', [])
        self.levels = admin_data.get('levels', [])

        # v2.19.0-fix6: 自动清理题库中错误的 imageUrl（防止答案文本被当成图片URL）
        import re
        valid_url = re.compile(r'^(https?://|data:image/)', re.IGNORECASE)
        cleaned = 0
        for q in self.questions:
            url = q.get('imageUrl', '')
            if url and not valid_url.match(str(url)):
                q['imageUrl'] = ''
                cleaned += 1
        if cleaned > 0:
            print(f"  [清理] 已清除 {cleaned} 条无效图片URL")

        # v2.19.0-fix6: 如果当前发布的考试已不在同步列表中，自动取消发布
        if self.published_exam_id:
            exam_ids = [e.get('id') for e in self.exams]
            if self.published_exam_id not in exam_ids:
                print(f"  [清理] 已取消发布不存在的旧考试: {self.published_exam_id}")
                self.published_exam_id = None

        self._save()
        return {
            'status': 'ok',
            'students': len(self.students),
            'exams': len(self.exams),
            'questions': len(self.questions),
            'levels': len(self.levels)
        }

    def publish_exam(self, exam_id):
        """管理员发布一场考试"""
        exam = next((e for e in self.exams if e['id'] == exam_id), None)
        if not exam:
            return {'status': 'error', 'message': '考试不存在'}
        self.published_exam_id = exam_id
        self.scores = []       # 清空上次的成绩
        self.sign_ins = []     # 清空签到记录
        self._save()
        return {'status': 'ok', 'exam_name': exam.get('name', ''), 'exam_id': exam_id}

    def unpublish_exam(self):
        """取消发布考试"""
        self.published_exam_id = None
        self._save()
        return {'status': 'ok'}

    def get_published_exam(self):
        """获取当前发布的考试（学员端调用）"""
        if not self.published_exam_id:
            return None
        exam = next((e for e in self.exams if e['id'] == self.published_exam_id), None)
        if not exam:
            return None

        # v2.19.0-fix7: 服务器端生成考试题目，修复字段名不匹配问题
        exam_levels = exam.get('levels', [])
        type_counts = exam.get('typeCounts', {})
        # 从 typeCounts 提取数量>0的题型（而非不存在的 questionTypes）
        exam_types = [t for t, c in type_counts.items() if c > 0]
        all_questions = self.questions

        # 按级别和题型过滤题库（题目字段是 'level' 单数字符串，不是 'levels' 数组）
        available = [q for q in all_questions
                     if q.get('type') in exam_types
                     and q.get('level') in exam_levels]

        # 随机排序
        if exam.get('randomOrder', True):
            random.shuffle(available)

        # 截取指定数量
        count = exam.get('questionCount', 0)
        if count > 0 and len(available) > count:
            available = available[:count]

        # 把生成的题目嵌入考试对象中
        exam_copy = dict(exam)
        exam_copy['questions'] = available
        exam_copy['questionCount'] = len(available)

        return {
            'exam': exam_copy,
            'questions': available,
            'levels': self.levels
        }

    def validate_student(self, name, student_id):
        """验证学员登录"""
        for s in self.students:
            if s['id'].strip() == student_id.strip() and s['name'].strip() == name.strip():
                return {'valid': True, 'student': s}
        return {'valid': False}

    def sign_in(self, student_id, student_name, exam_id):
        """学员签到"""
        # 检查是否已签到
        for s in self.sign_ins:
            if s['studentId'] == student_id and s['examId'] == exam_id:
                return {'status': 'ok', 'message': '已签到', 'duplicate': True}

        self.sign_ins.append({
            'studentId': student_id,
            'studentName': student_name,
            'examId': exam_id,
            'signInTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        self._save()
        return {'status': 'ok', 'duplicate': False}

    def submit_score(self, score_data):
        """接收学员提交的成绩"""
        # 防止重复提交（同学员同考试同时间戳）
        ts = score_data.get('timestamp', 0)
        sid = score_data.get('studentId', '')
        eid = score_data.get('examId', '')
        for s in self.scores:
            if s['studentId'] == sid and s['examId'] == eid and s['timestamp'] == ts:
                return {'status': 'ok', 'message': '成绩已记录', 'duplicate': True}

        self.scores.append(score_data)
        self._save()
        return {'status': 'ok', 'duplicate': False}

    def get_monitor_data(self):
        """获取监控数据（管理员端调用）"""
        if not self.published_exam_id:
            return {
                'active': False,
                'publishedExamId': None,
                'signedIn': 0,
                'submitted': 0,
                'scores': [],
                'signIns': []
            }

        exam = next((e for e in self.exams if e['id'] == self.published_exam_id), None)
        pass_score = exam.get('passScore', 60) if exam else 60

        signed_in_count = len(self.sign_ins)
        submitted_count = len(self.scores)

        # 计算通过率和平均分
        passed = sum(1 for s in self.scores if s['score'] >= pass_score)
        avg = sum(s['score'] for s in self.scores) / submitted_count if submitted_count > 0 else 0
        pass_rate = (passed / submitted_count * 100) if submitted_count > 0 else 0

        return {
            'active': True,
            'publishedExamId': self.published_exam_id,
            'examName': exam.get('name', '') if exam else '',
            'passScore': pass_score,
            'signedIn': signed_in_count,
            'submitted': submitted_count,
            'avgScore': round(avg, 1),
            'passRate': round(pass_rate, 0),
            'scores': self.scores,
            'signIns': self.sign_ins
        }


# 全局服务器实例
server = ExamServer()


class ExamHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP请求处理器"""

    def _send_json(self, data, status=200):
        """发送JSON响应"""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        """读取JSON请求体"""
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode('utf-8')
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self._send_json({}, 200)

    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        # 服务器状态检测
        if path == '/api/status':
            self._send_json({
                'server': True,
                'publishedExamId': server.published_exam_id,
                'studentCount': len(server.students),
                'examCount': len(server.exams)
            })

        # 获取发布的考试（学员端）
        elif path == '/api/exam/published':
            data = server.get_published_exam()
            if data:
                self._send_json(data)
            else:
                self._send_json({'error': '当前没有发布的考试'}, 404)

        # 获取监控数据（管理员端）
        elif path == '/api/monitor':
            self._send_json(server.get_monitor_data())

        # 获取所有成绩（管理员端）
        elif path == '/api/scores':
            self._send_json({
                'status': 'ok',
                'scores': server.scores,
                'count': len(server.scores)
            })

        # 根路径：提供index.html（强制无缓存）
        elif path == '/' or path == '/index.html':
            try:
                with open('index.html', 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except Exception as e:
                self._send_json({'error': '无法读取index.html: ' + str(e)}, 500)

        # 其他静态文件
        else:
            super().do_GET()

    def do_POST(self):
        """处理POST请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()

        # 管理员同步数据
        if path == '/api/admin/sync':
            result = server.sync_from_admin(data)
            self._send_json(result)

        # 发布考试
        elif path == '/api/exam/publish':
            exam_id = data.get('examId', '')
            result = server.publish_exam(exam_id)
            self._send_json(result)

        # 取消发布
        elif path == '/api/exam/unpublish':
            result = server.unpublish_exam()
            self._send_json(result)

        # 学员登录验证
        elif path == '/api/login':
            name = data.get('name', '').strip()
            sid = data.get('id', '').strip()
            result = server.validate_student(name, sid)
            self._send_json(result)

        # 学员签到
        elif path == '/api/signin':
            result = server.sign_in(
                data.get('studentId', ''),
                data.get('studentName', ''),
                data.get('examId', '')
            )
            self._send_json(result)

        # 提交成绩
        elif path == '/api/submit':
            result = server.submit_score(data)
            self._send_json(result)

        else:
            self._send_json({'error': '接口不存在'}, 404)

    def log_message(self, format, *args):
        """自定义日志格式"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        # 正确格式化日志消息（处理含%的URL路径）
        try:
            msg = format % args if args else format
        except (TypeError, ValueError):
            msg = format

        # 简化API日志
        if '/api/' in msg:
            # 只显示关键操作
            if 'POST' in msg or 'sync' in msg or 'publish' in msg or 'submit' in msg:
                print(f"  [{timestamp}] {msg.split(' ')[0]}")
        else:
            # 只显示静态资源的错误日志（过滤掉正常的静态文件请求）
            if '404' in msg or '500' in msg or 'error' in msg.lower():
                print(f"  [{timestamp}] {msg}")


def get_local_ip():
    """获取本机局域网IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            hostname = socket.gethostname()
            return socket.gethostbyname(hostname)
        except Exception:
            return '127.0.0.1'


if __name__ == '__main__':
    ip = get_local_ip()

    print()
    print("=" * 58)
    print("       冉鹏工作室 - 考试服务器 v2.19.0")
    print("=" * 58)
    print()
    print(f"  [管理员] http://localhost:{PORT}")
    print(f"  [学  员] http://{ip}:{PORT}")
    print()
    print(f"  请将「学员地址」发送给参加考试的学员")
    print(f"  按 Ctrl+C 停止服务器")
    print()
    print("=" * 58)
    print()

    # 延迟1.5秒自动打开浏览器（管理员页面）
    def open_browser():
        try:
            webbrowser.open(f'http://localhost:{PORT}')
        except Exception:
            pass

    threading.Timer(1.5, open_browser).start()

    # 启动HTTP服务器
    httpd = http.server.HTTPServer(('0.0.0.0', PORT), ExamHTTPHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  服务器已停止。")
        httpd.server_close()

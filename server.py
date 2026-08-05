from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chirper.db'
app.config['UPLOAD_FOLDER'] = 'static/avatars'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    verified = db.Column(db.Boolean, default=False)
    badge_type = db.Column(db.String(10), default='blue')  # white, gray, blue
    bio = db.Column(db.String(200), default='')
    avatar_url = db.Column(db.String(300), default='')

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(280), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    likes = db.Column(db.Integer, default=0)
    author = db.relationship('User', backref='posts')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed = bcrypt.generate_password_hash('adminpass').decode('utf-8')
        admin = User(username='admin', email='admin@chirper.com', password=hashed, verified=True, badge_type='blue')
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def home():
    return jsonify({'status': 'online'})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Имя занято'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email занят'}), 400
    hashed = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(username=username, email=email, password=hashed)
    db.session.add(user)
    db.session.commit()
    return jsonify({'user_id': user.id, 'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '')
    password = data.get('password', '')
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        return jsonify({'user_id': user.id, 'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type})
    return jsonify({'error': 'Неверный email или пароль'}), 401

@app.route('/posts', methods=['GET'])
def get_posts():
    posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    result = []
    for p in posts:
        result.append({
            'id': p.id, 'content': p.content, 'likes': p.likes,
            'timestamp': p.timestamp.isoformat(),
            'author': {
                'username': p.author.username,
                'verified': p.author.verified,
                'badge_type': p.author.badge_type,
                'avatar_url': p.author.avatar_url
            }
        })
    return jsonify(result)

@app.route('/post', methods=['POST'])
def create_post():
    data = request.get_json()
    content = data.get('content', '').strip()
    user_id = data.get('user_id')
    if not user_id: return jsonify({'error': 'Не указан пользователь'}), 400
    if not content: return jsonify({'error': 'Пост пустой'}), 400
    user = User.query.get(user_id)
    if not user: return jsonify({'error': 'Пользователь не найден'}), 400
    post = Post(content=content, user_id=user_id)
    db.session.add(post)
    db.session.commit()
    return jsonify({
        'id': post.id, 'content': post.content, 'likes': 0,
        'timestamp': post.timestamp.isoformat(),
        'author': {'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type, 'avatar_url': user.avatar_url}
    })

@app.route('/like/<int:post_id>', methods=['POST'])
def like(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({'likes': post.likes})

@app.route('/user/<username>', methods=['GET'])
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).limit(30).all()
    return jsonify({
        'user': {
            'username': user.username,
            'verified': user.verified,
            'badge_type': user.badge_type,
            'bio': user.bio,
            'avatar_url': user.avatar_url
        },
        'posts': [{
            'id': p.id, 'content': p.content, 'likes': p.likes,
            'timestamp': p.timestamp.isoformat(),
            'author': {'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type, 'avatar_url': user.avatar_url}
        } for p in posts]
    })

@app.route('/verify', methods=['POST'])
def verify_user():
    data = request.get_json()
    target = data.get('username', '').strip()
    badge = data.get('badge_type', 'blue')
    if badge not in ('white', 'gray', 'blue'): badge = 'blue'
    user = User.query.filter_by(username=target).first()
    if not user: return jsonify({'error': 'Не найден'}), 404
    user.verified = True
    user.badge_type = badge
    db.session.commit()
    return jsonify({'message': f'{target} получил {badge} галочку!'})

@app.route('/update-profile', methods=['POST'])
def update_profile():
    data = request.get_json()
    user_id = data.get('user_id')
    user = User.query.get(user_id)
    if not user: return jsonify({'error': 'Не найден'}), 404
    if 'username' in data and data['username']:
        if User.query.filter_by(username=data['username']).first() and user.username != data['username']:
            return jsonify({'error': 'Имя занято'}), 400
        user.username = data['username']
    if 'bio' in data:
        user.bio = data['bio'][:200]
    db.session.commit()
    return jsonify({'message': 'Профиль обновлён'})

@app.route('/change-password', methods=['POST'])
def change_password():
    data = request.get_json()
    user_id = data.get('user_id')
    old = data.get('old_password', '')
    new = data.get('new_password', '')
    email = data.get('email', '')
    user = User.query.get(user_id)
    if not user: return jsonify({'error': 'Не найден'}), 404
    if not bcrypt.check_password_hash(user.password, old):
        return jsonify({'error': 'Неверный старый пароль'}), 400
    if email != user.email:
        return jsonify({'error': 'Email не совпадает'}), 400
    user.password = bcrypt.generate_password_hash(new).decode('utf-8')
    db.session.commit()
    return jsonify({'message': 'Пароль изменён'})

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    file = request.files['avatar']
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if not user: return jsonify({'error': 'Не найден'}), 404
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
        return jsonify({'error': 'Формат не поддерживается'}), 400
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    user.avatar_url = f"/static/avatars/{filename}"
    db.session.commit()
    return jsonify({'avatar_url': user.avatar_url})

@app.route('/static/avatars/<filename>')
def avatar(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

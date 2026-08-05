from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from datetime import timedelta
import os

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chirper.db'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    verified = db.Column(db.Boolean, default=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(280), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    likes = db.Column(db.Integer, default=0)
    author = db.relationship('User', backref='posts')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed = bcrypt.generate_password_hash('adminpass').decode('utf-8')
        admin = User(username='admin', email='admin@chirper.com', password=hashed, verified=True)
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def home():
    return jsonify({'status': 'online', 'message': 'Chirper API работает'})

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
    
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(username=username, email=email, password=hashed_pw)
    db.session.add(user)
    db.session.commit()
    
    token = create_access_token(identity=user.id)
    return jsonify({'token': token, 'user': {'id': user.id, 'username': user.username, 'verified': user.verified}})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '')
    password = data.get('password', '')
    user = User.query.filter_by(email=email).first()
    
    if user and bcrypt.check_password_hash(user.password, password):
        token = create_access_token(identity=user.id)
        return jsonify({'token': token, 'user': {'id': user.id, 'username': user.username, 'verified': user.verified}})
    return jsonify({'error': 'Неверный email или пароль'}), 401

@app.route('/posts', methods=['GET'])
def get_posts():
    posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    result = []
    for p in posts:
        result.append({
            'id': p.id,
            'content': p.content,
            'likes': p.likes,
            'timestamp': p.timestamp.isoformat(),
            'author': {'username': p.author.username, 'verified': p.author.verified}
        })
    return jsonify(result)

@app.route('/post', methods=['POST'])
@jwt_required()
def create_post():
    user_id = get_jwt_identity()
    content = request.get_json().get('content', '').strip()
    if not content or len(content) > 280:
        return jsonify({'error': 'Пост должен быть от 1 до 280 символов'}), 400
    
    post = Post(content=content, user_id=user_id)
    db.session.add(post)
    db.session.commit()
    return jsonify({'message': 'Пост создан!'})

@app.route('/like/<int:post_id>', methods=['POST'])
@jwt_required()
def like(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({'likes': post.likes})

@app.route('/user/<username>', methods=['GET'])
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).limit(30).all()
    result = {
        'user': {'username': user.username, 'verified': user.verified, 'bio': ''},
        'posts': []
    }
    for p in posts:
        result['posts'].append({
            'id': p.id,
            'content': p.content,
            'likes': p.likes,
            'timestamp': p.timestamp.isoformat(),
            'author': {'username': user.username, 'verified': user.verified}
        })
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)

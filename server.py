from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime, timedelta
import os, uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chirper.db'
app.config['UPLOAD_FOLDER'] = 'static/avatars'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ==================== МОДЕЛИ ====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    verified = db.Column(db.Boolean, default=False)
    badge_type = db.Column(db.String(10), default='blue')
    bio = db.Column(db.String(200), default='')
    avatar_url = db.Column(db.String(300), default='')
    online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)
    sent_requests = db.relationship('FriendRequest', foreign_keys='FriendRequest.from_id', backref='sender', lazy=True)
    received_requests = db.relationship('FriendRequest', foreign_keys='FriendRequest.to_id', backref='receiver', lazy=True)
    friendships1 = db.relationship('Friendship', foreign_keys='Friendship.user1_id', backref='user1', lazy=True)
    friendships2 = db.relationship('Friendship', foreign_keys='Friendship.user2_id', backref='user2', lazy=True)
    messages = db.relationship('Message', backref='sender', lazy=True)
    chat_members = db.relationship('ChatMember', backref='user', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(280), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    likes = db.Column(db.Integer, default=0)

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(10), default='pending')  # pending, accepted, rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='')
    description = db.Column(db.String(300), default='')
    avatar_url = db.Column(db.String(300), default='')
    is_group = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('ChatMember', backref='chat', lazy=True)
    messages = db.relationship('Message', backref='chat', lazy=True)

class ChatMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    can_invite = db.Column(db.Boolean, default=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    delivered = db.Column(db.Boolean, default=False)
    read = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed = bcrypt.generate_password_hash('adminpass').decode('utf-8')
        admin = User(username='admin', email='admin@chirper.com', password=hashed, verified=True, badge_type='blue')
        db.session.add(admin)
        db.session.commit()

# ==================== ХЕЛПЕРЫ ====================
def user_dict(u):
    return {
        'id': u.id, 'username': u.username, 'verified': u.verified,
        'badge_type': u.badge_type, 'bio': u.bio, 'avatar_url': u.avatar_url,
        'online': u.online, 'last_seen': u.last_seen.isoformat()
    }

def msg_dict(m):
    return {
        'id': m.id, 'chat_id': m.chat_id, 'sender_id': m.sender_id,
        'content': m.content, 'timestamp': m.timestamp.isoformat(),
        'delivered': m.delivered, 'read': m.read,
        'sender': user_dict(m.sender)
    }

def chat_dict(c, uid):
    members = [user_dict(m.user) for m in c.members]
    last_msg = Message.query.filter_by(chat_id=c.id).order_by(Message.timestamp.desc()).first()
    return {
        'id': c.id, 'name': c.name, 'description': c.description,
        'avatar_url': c.avatar_url, 'is_group': c.is_group,
        'created_by': c.created_by, 'members': members,
        'last_message': msg_dict(last_msg) if last_msg else None
    }

# ==================== АВТОРИЗАЦИЯ ====================
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    u = data.get('username', '').strip()
    e = data.get('email', '').strip()
    p = data.get('password', '')
    if User.query.filter_by(username=u).first(): return jsonify({'error': 'Имя занято'}), 400
    if User.query.filter_by(email=e).first(): return jsonify({'error': 'Email занят'}), 400
    user = User(username=u, email=e, password=bcrypt.generate_password_hash(p).decode('utf-8'))
    db.session.add(user); db.session.commit()
    return jsonify({'user_id': user.id, 'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email', '')).first()
    if user and bcrypt.check_password_hash(user.password, data.get('password', '')):
        user.online = True; user.last_seen = datetime.utcnow(); db.session.commit()
        return jsonify({'user_id': user.id, 'username': user.username, 'verified': user.verified, 'badge_type': user.badge_type})
    return jsonify({'error': 'Неверные данные'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    data = request.get_json()
    user = User.query.get(data.get('user_id'))
    if user: user.online = False; user.last_seen = datetime.utcnow(); db.session.commit()
    return jsonify({'ok': True})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json()
    user = User.query.get(data.get('user_id'))
    if user: user.online = True; user.last_seen = datetime.utcnow(); db.session.commit()
    return jsonify({'ok': True})

# ==================== ПОСТЫ ====================
@app.route('/posts', methods=['GET'])
def get_posts():
    posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    return jsonify([{
        'id': p.id, 'content': p.content, 'likes': p.likes,
        'timestamp': p.timestamp.isoformat(),
        'author': user_dict(p.author)
    } for p in posts])

@app.route('/post', methods=['POST'])
def create_post():
    data = request.get_json()
    user = User.query.get(data.get('user_id'))
    if not user: return jsonify({'error': 'Не найден'}), 400
    p = Post(content=data['content'][:280], user_id=user.id)
    db.session.add(p); db.session.commit()
    return jsonify({'id': p.id, 'content': p.content, 'author': user_dict(user)})

@app.route('/like/<int:pid>', methods=['POST'])
def like(pid):
    p = Post.query.get_or_404(pid); p.likes += 1; db.session.commit()
    return jsonify({'likes': p.likes})

@app.route('/user/<username>', methods=['GET'])
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).limit(30).all()
    friends = get_friends_list(user)
    return jsonify({
        'user': user_dict(user),
        'posts': [{'id': p.id, 'content': p.content, 'likes': p.likes, 'timestamp': p.timestamp.isoformat(), 'author': user_dict(user)} for p in posts],
        'friends': friends,
        'friends_count': len(friends)
    })

@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    if not user: return jsonify({'error': 'Не найден'}), 404
    user.verified = True; user.badge_type = data.get('badge_type', 'blue'); db.session.commit()
    return jsonify({'message': f'{user.username} получил галочку!'})

@app.route('/update-profile', methods=['POST'])
def update_profile():
    data = request.get_json()
    user = User.query.get(data['user_id'])
    if not user: return jsonify({'error': 'Не найден'}), 404
    if 'username' in data and data['username']:
        if User.query.filter_by(username=data['username']).first() and user.username != data['username']:
            return jsonify({'error': 'Имя занято'}), 400
        user.username = data['username']
    if 'bio' in data: user.bio = data['bio'][:200]
    db.session.commit(); return jsonify({'message': 'Обновлено'})

@app.route('/change-password', methods=['POST'])
def change_password():
    data = request.get_json()
    user = User.query.get(data['user_id'])
    if not user or not bcrypt.check_password_hash(user.password, data['old_password']):
        return jsonify({'error': 'Неверный пароль'}), 400
    if data['email'] != user.email: return jsonify({'error': 'Email не совпадает'}), 400
    user.password = bcrypt.generate_password_hash(data['new_password']).decode('utf-8')
    db.session.commit(); return jsonify({'message': 'Пароль изменён'})

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    file = request.files['avatar']
    user = User.query.get(request.form['user_id'])
    if not user: return jsonify({'error': 'Не найден'}), 404
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('jpg','jpeg','png','gif','webp'): return jsonify({'error': 'Формат не поддерживается'}), 400
    fn = f"{uuid.uuid4()}.{ext}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    user.avatar_url = f"/static/avatars/{fn}"; db.session.commit()
    return jsonify({'avatar_url': user.avatar_url})

@app.route('/static/avatars/<fn>')
def avatar(fn): return send_from_directory(app.config['UPLOAD_FOLDER'], fn)

# ==================== ДРУЗЬЯ ====================
def get_friends_list(user):
    friends = []
    for f in Friendship.query.filter((Friendship.user1_id == user.id) | (Friendship.user2_id == user.id)).all():
        friend = f.user2 if f.user1_id == user.id else f.user1
        friends.append(user_dict(friend))
    return friends

@app.route('/friends/<int:uid>', methods=['GET'])
def friends_list(uid):
    user = User.query.get_or_404(uid)
    return jsonify(get_friends_list(user))

@app.route('/friend-request', methods=['POST'])
def send_friend_request():
    data = request.get_json()
    from_u = User.query.get(data['from_id'])
    to_u = User.query.filter_by(username=data['to_username']).first()
    if not to_u: return jsonify({'error': 'Пользователь не найден'}), 404
    if from_u.id == to_u.id: return jsonify({'error': 'Нельзя добавить себя'}), 400
    existing = FriendRequest.query.filter_by(from_id=from_u.id, to_id=to_u.id, status='pending').first()
    if existing: return jsonify({'error': 'Заявка уже отправлена'}), 400
    are_friends = Friendship.query.filter(
        ((Friendship.user1_id == from_u.id) & (Friendship.user2_id == to_u.id)) |
        ((Friendship.user1_id == to_u.id) & (Friendship.user2_id == from_u.id))
    ).first()
    if are_friends: return jsonify({'error': 'Вы уже друзья'}), 400
    req = FriendRequest(from_id=from_u.id, to_id=to_u.id)
    db.session.add(req); db.session.commit()
    return jsonify({'message': 'Заявка отправлена'})

@app.route('/friend-requests/<int:uid>', methods=['GET'])
def get_friend_requests(uid):
    incoming = FriendRequest.query.filter_by(to_id=uid, status='pending').all()
    outgoing = FriendRequest.query.filter_by(from_id=uid, status='pending').all()
    return jsonify({
        'incoming': [{'id': r.id, 'from': user_dict(r.sender), 'timestamp': r.timestamp.isoformat()} for r in incoming],
        'outgoing': [{'id': r.id, 'to': user_dict(r.receiver), 'timestamp': r.timestamp.isoformat()} for r in outgoing]
    })

@app.route('/friend-request/<int:rid>/accept', methods=['POST'])
def accept_friend_request(rid):
    req = FriendRequest.query.get_or_404(rid)
    req.status = 'accepted'
    f = Friendship(user1_id=req.from_id, user2_id=req.to_id)
    db.session.add(f); db.session.commit()
    return jsonify({'message': 'Заявка принята'})

@app.route('/friend-request/<int:rid>/reject', methods=['POST'])
def reject_friend_request(rid):
    req = FriendRequest.query.get_or_404(rid)
    req.status = 'rejected'; db.session.commit()
    return jsonify({'message': 'Заявка отклонена'})

@app.route('/mutual-friends/<int:uid1>/<int:uid2>', methods=['GET'])
def mutual_friends(uid1, uid2):
    u1 = User.query.get_or_404(uid1); u2 = User.query.get_or_404(uid2)
    f1 = set(f['id'] for f in get_friends_list(u1))
    f2 = set(f['id'] for f in get_friends_list(u2))
    mutual_ids = f1 & f2
    mutual = [user_dict(User.query.get(i)) for i in mutual_ids]
    return jsonify(mutual)

# ==================== ЧАТЫ ====================
@app.route('/chats/<int:uid>', methods=['GET'])
def get_chats(uid):
    member_chats = ChatMember.query.filter_by(user_id=uid).all()
    chat_ids = [m.chat_id for m in member_chats]
    chats = Chat.query.filter(Chat.id.in_(chat_ids)).order_by(Chat.created_at.desc()).all()
    return jsonify([chat_dict(c, uid) for c in chats])

@app.route('/chat', methods=['POST'])
def create_chat():
    data = request.get_json()
    creator = User.query.get(data['creator_id'])
    if not creator: return jsonify({'error': 'Не найден'}), 404
    is_group = data.get('is_group', False)
    chat = Chat(name=data.get('name', ''), description=data.get('description', ''),
                is_group=is_group, created_by=creator.id)
    db.session.add(chat); db.session.flush()
    cm = ChatMember(chat_id=chat.id, user_id=creator.id, can_invite=True)
    db.session.add(cm)
    if not is_group:
        other = User.query.get(data.get('other_user_id'))
        if other:
            cm2 = ChatMember(chat_id=chat.id, user_id=other.id)
            db.session.add(cm2)
    db.session.commit()
    return jsonify(chat_dict(chat, creator.id))

@app.route('/chat/<int:cid>/invite', methods=['POST'])
def invite_to_chat(cid):
    data = request.get_json()
    chat = Chat.query.get_or_404(cid)
    if not chat.is_group: return jsonify({'error': 'Не групповой чат'}), 400
    new_user = User.query.filter_by(username=data['username']).first()
    if not new_user: return jsonify({'error': 'Пользователь не найден'}), 404
    if ChatMember.query.filter_by(chat_id=cid, user_id=new_user.id).first():
        return jsonify({'error': 'Уже в чате'}), 400
    cm = ChatMember(chat_id=cid, user_id=new_user.id)
    db.session.add(cm); db.session.commit()
    return jsonify({'message': f'{new_user.username} добавлен'})

@app.route('/chat/<int:cid>/settings', methods=['POST'])
def update_chat_settings(cid):
    data = request.get_json()
    chat = Chat.query.get_or_404(cid)
    if 'name' in data: chat.name = data['name']
    if 'description' in data: chat.description = data['description']
    if 'avatar_url' in data: chat.avatar_url = data['avatar_url']
    db.session.commit()
    return jsonify({'message': 'Настройки обновлены'})

@app.route('/chat/<int:cid>/messages', methods=['GET'])
def get_messages(cid):
    msgs = Message.query.filter_by(chat_id=cid).order_by(Message.timestamp.asc()).limit(100).all()
    return jsonify([msg_dict(m) for m in msgs])

@app.route('/chat/<int:cid>/message', methods=['POST'])
def send_message(cid):
    data = request.get_json()
    msg = Message(chat_id=cid, sender_id=data['sender_id'], content=data['content'])
    db.session.add(msg); db.session.commit()
    # Отмечаем доставку для всех онлайн-участников
    members = ChatMember.query.filter_by(chat_id=cid).all()
    for m in members:
        if m.user_id != data['sender_id'] and m.user.online:
            msg.delivered = True
    db.session.commit()
    return jsonify(msg_dict(msg))

@app.route('/message/<int:mid>/read', methods=['POST'])
def mark_read(mid):
    msg = Message.query.get_or_404(mid)
    msg.read = True; db.session.commit()
    return jsonify({'ok': True})

@app.route('/chat/<int:cid>/upload-avatar', methods=['POST'])
def upload_chat_avatar(cid):
    chat = Chat.query.get_or_404(cid)
    file = request.files['avatar']
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('jpg','jpeg','png','gif','webp'): return jsonify({'error': 'Формат не поддерживается'}), 400
    fn = f"chat_{uuid.uuid4()}.{ext}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    chat.avatar_url = f"/static/avatars/{fn}"; db.session.commit()
    return jsonify({'avatar_url': chat.avatar_url})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

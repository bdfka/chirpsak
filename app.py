from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime
import os, uuid

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-123')
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
    badge_type = db.Column(db.String(10), default='blue')
    bio = db.Column(db.String(200), default='')
    avatar_url = db.Column(db.String(300), default='')
    online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

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
    status = db.Column(db.String(10), default='pending')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='')
    is_group = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ChatMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

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
        admin = User(username='admin', email='admin@chirper.com', password=bcrypt.generate_password_hash('adminpass').decode('utf-8'), verified=True, badge_type='blue')
        db.session.add(admin); db.session.commit()

def u_dict(u):
    if not u: return {'username':'неизвестный','verified':False,'badge_type':'blue','bio':'','avatar_url':'','online':False,'last_seen':''}
    return {'id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type,'bio':u.bio or '','avatar_url':u.avatar_url or '','online':u.online,'last_seen':u.last_seen.isoformat() if u.last_seen else ''}

@app.route('/register', methods=['POST'])
def register():
    d=request.get_json()
    if not d.get('username') or not d.get('email') or not d.get('password'): return jsonify({'error':'Все поля обязательны'}),400
    if User.query.filter_by(username=d['username']).first():return jsonify({'error':'Имя занято'}),400
    if User.query.filter_by(email=d['email']).first():return jsonify({'error':'Email занят'}),400
    u=User(username=d['username'],email=d['email'],password=bcrypt.generate_password_hash(d['password']).decode('utf-8'))
    db.session.add(u);db.session.commit()
    return jsonify({'user_id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type})

@app.route('/login', methods=['POST'])
def login():
    d=request.get_json()
    u=User.query.filter_by(email=d.get('email','')).first()
    if u and bcrypt.check_password_hash(u.password,d.get('password','')):
        u.online=True;u.last_seen=datetime.utcnow();db.session.commit()
        return jsonify({'user_id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type})
    return jsonify({'error':'Неверные данные'}),401

@app.route('/logout', methods=['POST'])
def logout():
    u=User.query.get(request.get_json().get('user_id'))
    if u:u.online=False;u.last_seen=datetime.utcnow();db.session.commit()
    return jsonify({'ok':True})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    u=User.query.get(request.get_json().get('user_id'))
    if u:u.online=True;u.last_seen=datetime.utcnow();db.session.commit()
    return jsonify({'ok':True})

@app.route('/posts', methods=['GET'])
def posts():
    ps = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    result = []
    for p in ps:
        author = User.query.get(p.user_id)
        result.append({
            'id': p.id,
            'content': p.content,
            'likes': p.likes,
            'timestamp': p.timestamp.isoformat() if p.timestamp else '',
            'author': u_dict(author)
        })
    return jsonify(result)

@app.route('/post', methods=['POST'])
def create_post():
    d=request.get_json()
    user_id=d.get('user_id')
    if not user_id:return jsonify({'error':'user_id не передан'}),400
    u=User.query.get(int(user_id))
    if not u:return jsonify({'error':'Пользователь не найден'}),404
    content=d.get('content','').strip()
    if not content:return jsonify({'error':'Пустой пост'}),400
    p=Post(content=content[:280],user_id=u.id)
    db.session.add(p);db.session.commit()
    return jsonify({'id':p.id})

@app.route('/like/<int:pid>', methods=['POST'])
def like(pid):
    p=Post.query.get_or_404(pid);p.likes+=1;db.session.commit()
    return jsonify({'likes':p.likes})

@app.route('/user/<username>', methods=['GET'])
def profile(username):
    u=User.query.filter_by(username=username).first()
    if not u: return jsonify({'error':'Пользователь не найден'}),404
    ps=Post.query.filter_by(user_id=u.id).order_by(Post.timestamp.desc()).limit(30).all()
    fr=[]
    for f in Friendship.query.filter((Friendship.user1_id==u.id)|(Friendship.user2_id==u.id)).all():
        fid=f.user2_id if f.user1_id==u.id else f.user1_id
        friend=User.query.get(fid)
        if friend: fr.append(u_dict(friend))
    return jsonify({'user':u_dict(u),'posts':[{'id':p.id,'content':p.content,'likes':p.likes,'timestamp':p.timestamp.isoformat() if p.timestamp else ''} for p in ps],'friends':fr})

@app.route('/verify', methods=['POST'])
def verify():
    d=request.get_json()
    u=User.query.filter_by(username=d.get('username','')).first()
    if not u:return jsonify({'error':'Не найден'}),404
    u.verified=True;u.badge_type=d.get('badge_type','blue');db.session.commit()
    return jsonify({'message':f'{u.username} получил галочку!'})

@app.route('/update-profile', methods=['POST'])
def upd_profile():
    d=request.get_json();u=User.query.get(d['user_id'])
    if not u: return jsonify({'error':'Не найден'}),404
    if d.get('username'):
        existing=User.query.filter_by(username=d['username']).first()
        if existing and existing.id!=u.id:return jsonify({'error':'Имя занято'}),400
        u.username=d['username']
    if 'bio' in d:u.bio=d['bio'][:200]
    db.session.commit();return jsonify({'message':'OK'})

@app.route('/change-password', methods=['POST'])
def ch_pass():
    d=request.get_json();u=User.query.get(d['user_id'])
    if not u or not bcrypt.check_password_hash(u.password,d.get('old_password','')):return jsonify({'error':'Неверный пароль'}),400
    if d.get('email')!=u.email:return jsonify({'error':'Email не совпадает'}),400
    u.password=bcrypt.generate_password_hash(d['new_password']).decode('utf-8');db.session.commit()
    return jsonify({'message':'OK'})

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    if 'avatar' not in request.files: return jsonify({'error':'Нет файла'}),400
    f=request.files['avatar']
    uid=request.form.get('user_id')
    if not uid: return jsonify({'error':'user_id не передан'}),400
    u=User.query.get(int(uid))
    if not u: return jsonify({'error':'Пользователь не найден'}),404
    ext=f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else 'jpg'
    if ext not in('jpg','jpeg','png','gif','webp'):ext='jpg'
    fn=f"{uuid.uuid4()}.{ext}"
    f.save(os.path.join(app.config['UPLOAD_FOLDER'],fn))
    u.avatar_url=f"/static/avatars/{fn}";db.session.commit()
    return jsonify({'avatar_url':u.avatar_url})

@app.route('/static/avatars/<fn>')
def ava(fn):return send_from_directory(app.config['UPLOAD_FOLDER'],fn)

@app.route('/friends/<int:uid>', methods=['GET'])
def friends(uid):
    if not User.query.get(uid): return jsonify([])
    fr=[]
    for f in Friendship.query.filter((Friendship.user1_id==uid)|(Friendship.user2_id==uid)).all():
        fid=f.user2_id if f.user1_id==uid else f.user1_id
        friend=User.query.get(fid)
        if friend: fr.append(u_dict(friend))
    return jsonify(fr)

@app.route('/friend-request', methods=['POST'])
def send_fr():
    d=request.get_json()
    from_id=d.get('from_id')
    to_username=d.get('to_username','').strip()
    if not from_id or not to_username: return jsonify({'error':'Данные неполные'}),400
    to=User.query.filter_by(username=to_username).first()
    if not to:return jsonify({'error':'Пользователь не найден'}),404
    if int(from_id)==to.id:return jsonify({'error':'Нельзя добавить себя'}),400
    existing=FriendRequest.query.filter_by(from_id=int(from_id),to_id=to.id,status='pending').first()
    if existing:return jsonify({'error':'Заявка уже отправлена'}),400
    are_friends=Friendship.query.filter(
        ((Friendship.user1_id==int(from_id))&(Friendship.user2_id==to.id))|
        ((Friendship.user1_id==to.id)&(Friendship.user2_id==int(from_id)))
    ).first()
    if are_friends:return jsonify({'error':'Вы уже друзья'}),400
    db.session.add(FriendRequest(from_id=int(from_id),to_id=to.id));db.session.commit()
    return jsonify({'message':'Заявка отправлена'})

@app.route('/friend-requests/<int:uid>', methods=['GET'])
def fr_list(uid):
    inc=FriendRequest.query.filter_by(to_id=uid,status='pending').all()
    out=FriendRequest.query.filter_by(from_id=uid,status='pending').all()
    return jsonify({
        'incoming':[{'id':r.id,'from':u_dict(User.query.get(r.from_id))} for r in inc if User.query.get(r.from_id)],
        'outgoing':[{'id':r.id,'to':u_dict(User.query.get(r.to_id))} for r in out if User.query.get(r.to_id)]
    })

@app.route('/friend-request/<int:rid>/accept', methods=['POST'])
def accept_fr(rid):
    r=FriendRequest.query.get_or_404(rid);r.status='accepted'
    db.session.add(Friendship(user1_id=r.from_id,user2_id=r.to_id));db.session.commit()
    return jsonify({'message':'OK'})

@app.route('/friend-request/<int:rid>/reject', methods=['POST'])
def reject_fr(rid):
    FriendRequest.query.get_or_404(rid).status='rejected';db.session.commit()
    return jsonify({'message':'OK'})

@app.route('/mutual-friends/<int:uid1>/<username>', methods=['GET'])
def mutual(uid1,username):
    u1=User.query.get_or_404(uid1);u2=User.query.filter_by(username=username).first_or_404()
    f1=set();f2=set()
    for f in Friendship.query.filter((Friendship.user1_id==uid1)|(Friendship.user2_id==uid1)).all():f1.add(f.user2_id if f.user1_id==uid1 else f.user1_id)
    for f in Friendship.query.filter((Friendship.user1_id==u2.id)|(Friendship.user2_id==u2.id)).all():f2.add(f.user2_id if f.user1_id==u2.id else f.user1_id)
    mutual_list=[]
    for i in(f1&f2):
        u=User.query.get(i)
        if u: mutual_list.append(u_dict(u))
    return jsonify(mutual_list)

@app.route('/chats/<int:uid>', methods=['GET'])
def chats(uid):
    if not User.query.get(uid): return jsonify([])
    cids=[m.chat_id for m in ChatMember.query.filter_by(user_id=uid).all()]
    cs=Chat.query.filter(Chat.id.in_(cids)).all() if cids else []
    result=[]
    for c in cs:
        members_list=[]
        for m in ChatMember.query.filter_by(chat_id=c.id).all():
            u=User.query.get(m.user_id)
            if u: members_list.append(u_dict(u))
        result.append({'id':c.id,'name':c.name or '','is_group':c.is_group,'members':members_list})
    return jsonify(result)

@app.route('/chat', methods=['POST'])
def create_chat():
    d=request.get_json()
    creator_id=d.get('creator_id')
    if not creator_id: return jsonify({'error':'creator_id не передан'}),400
    if not User.query.get(int(creator_id)): return jsonify({'error':'Пользователь не найден'}),404
    c=Chat(name=d.get('name',''),is_group=d.get('is_group',False),created_by=int(creator_id))
    db.session.add(c);db.session.flush()
    db.session.add(ChatMember(chat_id=c.id,user_id=int(creator_id)))
    other_id=d.get('other_user_id')
    if not d.get('is_group') and other_id and User.query.get(int(other_id)):
        db.session.add(ChatMember(chat_id=c.id,user_id=int(other_id)))
    db.session.commit()
    return jsonify({'id':c.id})

@app.route('/chat/<int:cid>/messages', methods=['GET'])
def msgs(cid):
    ms=Message.query.filter_by(chat_id=cid).order_by(Message.timestamp.asc()).limit(100).all()
    result=[]
    for m in ms:
        sender=User.query.get(m.sender_id)
        if sender: result.append({'id':m.id,'sender_id':m.sender_id,'content':m.content,'timestamp':m.timestamp.isoformat() if m.timestamp else '','delivered':m.delivered,'read':m.read,'sender':u_dict(sender)})
    return jsonify(result)

@app.route('/chat/<int:cid>/message', methods=['POST'])
def send_msg(cid):
    d=request.get_json()
    sender_id=d.get('sender_id')
    if not sender_id: return jsonify({'error':'sender_id не передан'}),400
    m=Message(chat_id=cid,sender_id=int(sender_id),content=d.get('content',''))
    db.session.add(m);db.session.commit()
    return jsonify({'id':m.id,'sender':u_dict(User.query.get(int(sender_id))),'content':m.content,'timestamp':m.timestamp.isoformat() if m.timestamp else ''})

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

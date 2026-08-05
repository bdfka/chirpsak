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

# МОДЕЛИ
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
    return {'id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type,'bio':u.bio,'avatar_url':u.avatar_url,'online':u.online,'last_seen':u.last_seen.isoformat()}

# API
@app.route('/register', methods=['POST'])
def register():
    d=request.get_json()
    if User.query.filter_by(username=d['username']).first():return jsonify({'error':'Имя занято'}),400
    if User.query.filter_by(email=d['email']).first():return jsonify({'error':'Email занят'}),400
    u=User(username=d['username'],email=d['email'],password=bcrypt.generate_password_hash(d['password']).decode('utf-8'))
    db.session.add(u);db.session.commit()
    return jsonify({'user_id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type})

@app.route('/login', methods=['POST'])
def login():
    d=request.get_json()
    u=User.query.filter_by(email=d['email']).first()
    if u and bcrypt.check_password_hash(u.password,d['password']):
        u.online=True;db.session.commit()
        return jsonify({'user_id':u.id,'username':u.username,'verified':u.verified,'badge_type':u.badge_type})
    return jsonify({'error':'Неверные данные'}),401

@app.route('/logout', methods=['POST'])
def logout():
    u=User.query.get(request.get_json().get('user_id'))
    if u:u.online=False;db.session.commit()
    return jsonify({'ok':True})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    u=User.query.get(request.get_json().get('user_id'))
    if u:u.online=True;u.last_seen=datetime.utcnow();db.session.commit()
    return jsonify({'ok':True})

@app.route('/posts', methods=['GET'])
def posts():
    ps=Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    return jsonify([{'id':p.id,'content':p.content,'likes':p.likes,'timestamp':p.timestamp.isoformat(),'author':u_dict(p.author)} for p in ps])

@app.route('/post', methods=['POST'])
def create_post():
    d=request.get_json()
    u=User.query.get(d['user_id'])
    p=Post(content=d['content'][:280],user_id=u.id)
    db.session.add(p);db.session.commit()
    return jsonify({'id':p.id})

@app.route('/like/<int:pid>', methods=['POST'])
def like(pid):
    p=Post.query.get_or_404(pid);p.likes+=1;db.session.commit()
    return jsonify({'likes':p.likes})

@app.route('/user/<username>', methods=['GET'])
def profile(username):
    u=User.query.filter_by(username=username).first_or_404()
    ps=Post.query.filter_by(user_id=u.id).order_by(Post.timestamp.desc()).limit(30).all()
    fr=[]
    for f in Friendship.query.filter((Friendship.user1_id==u.id)|(Friendship.user2_id==u.id)).all():
        fid=f.user2_id if f.user1_id==u.id else f.user1_id
        fr.append(u_dict(User.query.get(fid)))
    return jsonify({'user':u_dict(u),'posts':[{'id':p.id,'content':p.content,'likes':p.likes,'timestamp':p.timestamp.isoformat()} for p in ps],'friends':fr})

@app.route('/verify', methods=['POST'])
def verify():
    d=request.get_json()
    u=User.query.filter_by(username=d['username']).first()
    if not u:return jsonify({'error':'Не найден'}),404
    u.verified=True;u.badge_type=d.get('badge_type','blue');db.session.commit()
    return jsonify({'message':f'{u.username} получил галочку!'})

@app.route('/update-profile', methods=['POST'])
def upd_profile():
    d=request.get_json();u=User.query.get(d['user_id'])
    if 'username' in d and d['username']:
        if User.query.filter_by(username=d['username']).first() and u.username!=d['username']:return jsonify({'error':'Имя занято'}),400
        u.username=d['username']
    if 'bio' in d:u.bio=d['bio'][:200]
    db.session.commit();return jsonify({'message':'OK'})

@app.route('/change-password', methods=['POST'])
def ch_pass():
    d=request.get_json();u=User.query.get(d['user_id'])
    if not u or not bcrypt.check_password_hash(u.password,d['old_password']):return jsonify({'error':'Неверный пароль'}),400
    if d['email']!=u.email:return jsonify({'error':'Email не совпадает'}),400
    u.password=bcrypt.generate_password_hash(d['new_password']).decode('utf-8');db.session.commit()
    return jsonify({'message':'OK'})

@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    f=request.files['avatar'];u=User.query.get(request.form['user_id'])
    ext=f.filename.rsplit('.',1)[-1].lower()
    if ext not in('jpg','jpeg','png','gif','webp'):return jsonify({'error':'Формат'}),400
    fn=f"{uuid.uuid4()}.{ext}"
    f.save(os.path.join(app.config['UPLOAD_FOLDER'],fn))
    u.avatar_url=f"/static/avatars/{fn}";db.session.commit()
    return jsonify({'avatar_url':u.avatar_url})

@app.route('/static/avatars/<fn>')
def ava(fn):return send_from_directory(app.config['UPLOAD_FOLDER'],fn)

@app.route('/friends/<int:uid>', methods=['GET'])
def friends(uid):
    fr=[]
    for f in Friendship.query.filter((Friendship.user1_id==uid)|(Friendship.user2_id==uid)).all():
        fid=f.user2_id if f.user1_id==uid else f.user1_id
        fr.append(u_dict(User.query.get(fid)))
    return jsonify(fr)

@app.route('/friend-request', methods=['POST'])
def send_fr():
    d=request.get_json()
    to=User.query.filter_by(username=d['to_username']).first()
    if not to:return jsonify({'error':'Не найден'}),404
    if d['from_id']==to.id:return jsonify({'error':'Нельзя'}),400
    db.session.add(FriendRequest(from_id=d['from_id'],to_id=to.id));db.session.commit()
    return jsonify({'message':'OK'})

@app.route('/friend-requests/<int:uid>', methods=['GET'])
def fr_list(uid):
    inc=FriendRequest.query.filter_by(to_id=uid,status='pending').all()
    out=FriendRequest.query.filter_by(from_id=uid,status='pending').all()
    return jsonify({'incoming':[{'id':r.id,'from':u_dict(User.query.get(r.from_id))} for r in inc],'outgoing':[{'id':r.id,'to':u_dict(User.query.get(r.to_id))} for r in out]})

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
    u2=User.query.filter_by(username=username).first_or_404()
    f1=set();f2=set()
    for f in Friendship.query.filter((Friendship.user1_id==uid1)|(Friendship.user2_id==uid1)).all():f1.add(f.user2_id if f.user1_id==uid1 else f.user1_id)
    for f in Friendship.query.filter((Friendship.user1_id==u2.id)|(Friendship.user2_id==u2.id)).all():f2.add(f.user2_id if f.user1_id==u2.id else f.user1_id)
    return jsonify([u_dict(User.query.get(i)) for i in(f1&f2)])

@app.route('/chats/<int:uid>', methods=['GET'])
def chats(uid):
    cids=[m.chat_id for m in ChatMember.query.filter_by(user_id=uid).all()]
    cs=Chat.query.filter(Chat.id.in_(cids)).all()
    return jsonify([{'id':c.id,'name':c.name,'is_group':c.is_group,'members':[u_dict(User.query.get(m.user_id)) for m in ChatMember.query.filter_by(chat_id=c.id).all()]} for c in cs])

@app.route('/chat', methods=['POST'])
def create_chat():
    d=request.get_json()
    c=Chat(name=d.get('name',''),is_group=d.get('is_group',False),created_by=d['creator_id'])
    db.session.add(c);db.session.flush()
    db.session.add(ChatMember(chat_id=c.id,user_id=d['creator_id']))
    if not d.get('is_group') and d.get('other_user_id'):db.session.add(ChatMember(chat_id=c.id,user_id=d['other_user_id']))
    db.session.commit()
    return jsonify({'id':c.id})

@app.route('/chat/<int:cid>/messages', methods=['GET'])
def msgs(cid):
    ms=Message.query.filter_by(chat_id=cid).order_by(Message.timestamp.asc()).limit(100).all()
    return jsonify([{'id':m.id,'sender_id':m.sender_id,'content':m.content,'timestamp':m.timestamp.isoformat(),'delivered':m.delivered,'read':m.read,'sender':u_dict(User.query.get(m.sender_id))} for m in ms])

@app.route('/chat/<int:cid>/message', methods=['POST'])
def send_msg(cid):
    d=request.get_json()
    m=Message(chat_id=cid,sender_id=d['sender_id'],content=d['content'])
    db.session.add(m);db.session.commit()
    return jsonify({'id':m.id,'sender':u_dict(User.query.get(m.sender_id)),'content':m.content,'timestamp':m.timestamp.isoformat()})

# САЙТ
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

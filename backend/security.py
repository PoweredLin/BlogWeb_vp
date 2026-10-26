import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import time
import warnings
from PIL import Image, ImageDraw
from .storage import meta, dumps, stamp
from .validation import fail, text


def millis(): return int(time.time()*1000)
def sha(value): return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    # Node's scryptSync used the hexadecimal salt AS TEXT, not decoded bytes.
    return hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1,dklen=64).hex()


def credentials(password):
    text(password,200,10)
    salt=secrets.token_hex(16)
    return salt,password_hash(password,salt)


def login(db,username,password):
    username=text(username or 'admin',32)
    password=text(password,200)
    account=meta(db,'account') if username=='admin' else db.execute('SELECT * FROM users WHERE username=? AND disabled=0',(username,)).fetchone()
    candidate=password_hash(password,account['salt'] if account else 'invalid-account-salt')
    if not account or not hmac.compare_digest(candidate,account['hash']): fail(401,'账号或密码不正确。')
    return 'owner' if username=='admin' else account['id']


def identity(db,token):
    if not token or len(token)>128: return None
    session=db.execute('SELECT userId FROM sessions WHERE token=? AND expires>?',(sha(token),millis())).fetchone()
    if not session: return None
    uid=session['userId']
    row=db.execute('SELECT data FROM member_profiles WHERE userId=?',(uid,)).fetchone()
    avatar=json.loads(row['data']).get('avatar','/favicon.svg') if row else '/favicon.svg'
    if uid=='owner':
        a=meta(db,'account')
        return {'id':'owner','username':'admin','name':a['name'],'avatar':avatar,'role':'admin'} if a else None
    u=db.execute('SELECT id,username,name FROM users WHERE id=? AND disabled=0',(uid,)).fetchone()
    return {**dict(u),'avatar':avatar,'role':'member'} if u else None


def session(db,response,uid,secure):
    token=secrets.token_hex(32)
    db.execute('DELETE FROM sessions WHERE expires<?',(millis(),))
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(sha(token),millis()+7*86400000,uid))
    response.set_cookie('space_session',token,max_age=7*86400,httponly=True,secure=secure,samesite='strict',path='/')


def rate(db,ip,kind,maximum,seconds=600):
    key=kind+':'+sha(ip)
    db.execute('DELETE FROM member_rates WHERE expires<?',(millis(),))
    old=db.execute('SELECT count FROM member_rates WHERE key=?',(key,)).fetchone()
    if old and old['count']>=maximum: fail(429,'操作过于频繁，请稍后再试')
    db.execute('INSERT INTO member_rates VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,millis()+seconds*1000))


def captcha(db,ip):
    rate(db,ip,'captcha',30)
    db.execute('DELETE FROM captchas WHERE expires<?',(millis(),))
    identifier=secrets.token_hex(24)
    answer=''.join(secrets.choice('23456789') for _ in range(5))
    db.execute('INSERT INTO captchas VALUES(?,?,?,?)',(identifier,sha(identifier+':'+answer),sha(ip),millis()+180000))
    img=Image.new('RGB',(180,60),'#f2f4f7'); draw=ImageDraw.Draw(img)
    for _ in range(12):
        draw.line((secrets.randbelow(180),secrets.randbelow(60),secrets.randbelow(180),secrets.randbelow(60)),fill='#c5ceda',width=1)
    for i,ch in enumerate(answer): draw.text((12+i*32,10+secrets.randbelow(10)),ch,fill='#263954',font_size=30)
    out=io.BytesIO(); img.save(out,format='PNG')
    return {'id':identifier,'image':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode(),'expiresIn':180}


def check_captcha(db,body,ip):
    identifier=text(body.get('captchaId'),80)
    answer=text(body.get('captchaAnswer'),10,trim=True)
    c=db.execute('SELECT * FROM captchas WHERE id=?',(identifier,)).fetchone()
    db.execute('DELETE FROM captchas WHERE id=?',(identifier,))
    if not c or c['expires']<millis() or c['ip']!=sha(ip) or not hmac.compare_digest(c['answer'],sha(identifier+':'+answer)):
        fail(400,'验证码不正确或已过期，请换一张重试')


def image_bytes(data):
    data=text(data,11000000)
    match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',data)
    if not match: fail(400,'请选择 PNG、JPEG 或 WebP 图片')
    try: raw=base64.b64decode(match[2],validate=True)
    except ValueError: fail(400,'图片编码无效')
    validate_image(raw,match[1])
    return raw,match[1]


def validate_image(raw,extension):
    if len(raw)>8*1024*1024: fail(400,'图片不能超过 8MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as img:
                if img.format.lower()!=extension or img.width*img.height>24000000 or max(img.size)>12000: fail(400,'图片格式或尺寸无效')
                img.verify()
            with Image.open(io.BytesIO(raw)) as img: img.load()
    except (OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning): fail(400,'图片文件损坏或尺寸过大')


def check_images(db,body,uid):
    for name in re.findall(r'/uploads/([\w.-]+)',dumps(body),re.ASCII):
        r=db.execute('SELECT userId FROM upload_owners WHERE name=?',(name,)).fetchone()
        if (r['userId'] if r else 'owner')!=uid: fail(403,'只能引用自己上传的图片')

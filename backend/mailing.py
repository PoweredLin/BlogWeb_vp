"""Small, single-process SMTP delivery and weekly report scheduler."""
import asyncio
import logging
import os
import json
import re
import smtplib
import socket
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet, InvalidToken

from .storage import meta, set_meta, stamp, dumps

logger = logging.getLogger('lin-notebook.mail')
CONFIG_KEY = 'mailSettings'


class DeliveryUnknown(Exception):
    pass


def valid_email(value):
    return isinstance(value, str) and len(value) <= 254 and re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value) is not None


def _fernet():
    key = os.getenv('EMAIL_ENCRYPTION_KEY', '')
    if not key:
        raise RuntimeError('尚未配置 EMAIL_ENCRYPTION_KEY')
    try:
        return Fernet(key.encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError('EMAIL_ENCRYPTION_KEY 格式无效') from None


def settings(db):
    value = meta(db, CONFIG_KEY, {})
    result = {k: value.get(k, default) for k, default in {
        'host': '', 'port': 587, 'sender': '', 'recipient': '', 'username': '',
        'useTls': True, 'timezone': 'Asia/Shanghai', 'enabled': False,
        'weekday': 1, 'sendTime': '09:00', 'lastScheduledKey': '', 'reportSources':['posts']
    }.items()}
    result['passwordConfigured'] = bool(value.get('password'))
    return result


def save_settings(db, body):
    host = str(body.get('host', '')).strip()
    sender = str(body.get('sender', '')).strip()
    recipient = str(body.get('recipient', '')).strip()
    username = str(body.get('username', '')).strip()
    password = body.get('password')
    port = body.get('port', 587)
    weekday = body.get('weekday', 1)
    send_time = body.get('sendTime', '09:00')
    timezone = str(body.get('timezone', 'Asia/Shanghai')).strip()
    enabled = body.get('enabled', False)
    use_tls = body.get('useTls', True)
    sources=body.get('reportSources',['posts'])
    if not isinstance(sources,list) or not sources or any(s not in ('posts','notes','tasks','automation') for s in sources):raise ValueError('周报内容范围无效')
    if not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError('SMTP 端口无效')
    if not isinstance(weekday, int) or not 0 <= weekday <= 6: raise ValueError('发送日期无效')
    if not isinstance(enabled, bool) or not isinstance(use_tls, bool): raise ValueError('邮件开关配置无效')
    try: datetime.strptime(send_time, '%H:%M'); ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError): raise ValueError('发送时间或时区无效') from None
    if enabled and not all((host, sender, recipient, username, meta(db, CONFIG_KEY, {}).get('password') or password)):
        raise ValueError('自动发送需要完整的 SMTP 配置和授权码')
    if any('\r' in x or '\n' in x for x in (host, sender, recipient, username)):
        raise ValueError('邮件配置包含无效字符')
    if not valid_email(sender) or not valid_email(recipient): raise ValueError('发件或收件邮箱格式无效')
    if any(len(x) > 254 for x in (host, sender, recipient, username)):
        raise ValueError('邮件配置长度超限')
    value = meta(db, CONFIG_KEY, {})
    value.update({'host': host, 'port': port, 'sender': sender, 'recipient': recipient,
                  'username': username, 'useTls': use_tls, 'timezone': timezone,
                  'enabled': enabled, 'weekday': weekday, 'sendTime': send_time,'reportSources':list(dict.fromkeys(sources))})
    if password:
        if not isinstance(password, str) or len(password) > 512: raise ValueError('SMTP 授权码无效')
        value['password'] = _fernet().encrypt(password.encode()).decode()
    set_meta(db, CONFIG_KEY, value)
    return settings(db)


def _credentials(config):
    if not config.get('password'):
        raise ValueError('请先保存 SMTP 授权码')
    try: password = _fernet().decrypt(config['password'].encode()).decode()
    except InvalidToken: raise RuntimeError('邮件密钥已变化，需重新填写 SMTP 授权码') from None
    return password


def _connect(config):
    password = _credentials(config)
    client = None
    try:
        if config.get('useTls'):
            client = smtplib.SMTP(config['host'], config['port'], timeout=15)
            client.ehlo()
            client.starttls()
            client.ehlo()
        else:
            client = smtplib.SMTP_SSL(config['host'], config['port'], timeout=15)
        client.login(config['username'], password)
        return client
    except Exception:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        raise


def connection_error(error):
    """Return actionable SMTP guidance without exposing provider response text."""
    if isinstance(error, DeliveryUnknown):
        return '测试邮件已提交，但 SMTP 连接在确认结果前中断。先检查收件箱和垃圾邮件，确认没有收到后再重试，避免重复发送。'
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return 'SMTP 登录被拒绝。请确认用户名通常是完整邮箱地址，并使用邮箱服务商生成的 SMTP/应用授权码。'
    if isinstance(error, smtplib.SMTPSenderRefused):
        return 'SMTP 服务商拒绝了发件地址。请将发件邮箱设置为当前 SMTP 账号允许使用的地址。'
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return 'SMTP 服务商拒绝了测试收件地址。请换成有效邮箱，并检查服务商的收件人或外发限制。'
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return 'TLS 握手方式与端口不匹配。587 通常使用 STARTTLS；465 通常使用隐式 TLS。'
    if isinstance(error, ssl.SSLError):
        return 'TLS 握手失败。请核对端口和加密方式：587 选 STARTTLS，465 取消 STARTTLS 使用隐式 TLS。'
    if isinstance(error, socket.gaierror):
        return '无法解析 SMTP 服务器地址。请检查 SMTP 主机名拼写和服务器 DNS。'
    if isinstance(error, (TimeoutError, socket.timeout)):
        return '连接 SMTP 服务器超时。请检查主机/端口，并确认服务器或云厂商允许出站访问 465/587 端口。'
    if isinstance(error, smtplib.SMTPConnectError):
        return 'SMTP 服务器拒绝连接。请检查主机、端口、TLS 方式和服务器出站网络策略。'
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return 'SMTP 服务器在会话中断开连接。请检查 TLS/端口组合及服务商连接限制。'
    if isinstance(error, smtplib.SMTPResponseException):
        return f'SMTP 服务商拒绝了请求（状态码 {error.smtp_code}）。请检查账号权限、发件地址和服务商发送限制。'
    if isinstance(error, OSError):
        return '服务器无法连接 SMTP 服务。请检查 DNS、防火墙和云厂商的出站邮件端口限制。'
    return '邮件测试失败。请核对 SMTP 地址、端口、TLS 方式和应用授权码；服务器日志只记录错误类型，不记录授权码。'


def test_connection(config):
    client = _connect(config)
    try: client.noop()
    finally: client.quit()


def report(db, now=None):
    end = now or datetime.now().astimezone()
    start = end - timedelta(days=7)
    rows = db.execute("SELECT data FROM records WHERE kind='posts' AND deleted IS NULL ORDER BY created DESC LIMIT 500").fetchall()
    posts = []
    for row in rows:
        post = json.loads(row['data'])
        try: published = datetime.fromisoformat(post.get('publishAt', '').replace('Z', '+00:00')).astimezone(end.tzinfo)
        except (ValueError, TypeError): continue
        if post.get('status') == 'published' and start <= published <= end:
            posts.append({'title': post.get('title', ''), 'slug': post.get('slug', ''), 'publishAt': published.isoformat(), 'excerpt': post.get('excerpt', '')})
    sources=meta(db,CONFIG_KEY,{}).get('reportSources',['posts']);sections=[]
    if 'posts' not in sources:posts=[]
    if 'notes' in sources:
        notes=[]
        for row in db.execute("SELECT data FROM records WHERE kind='notes' AND deleted IS NULL ORDER BY created DESC LIMIT 30"):
            n=json.loads(row['data']);d=n.get('date','')
            if start.date().isoformat()<=d<=end.date().isoformat():notes.append({k:v for k,v in n.items() if k in ('date','title','content','note','reflection','highlight')})
        sections.append({'title':'私人日志（最近 7 天）','text':'\n'.join(dumps(n) for n in notes)[:15000] or '本周没有日志。'})
    if 'tasks' in sources:
        tasks=[json.loads(r['data']) for r in db.execute("SELECT data FROM records WHERE kind='tasks' AND deleted IS NULL ORDER BY updated DESC LIMIT 500")]
        sections.append({'title':'任务概览','text':f'任务 {len(tasks)} 项，其中完成 {sum(t.get("status")=="done" for t in tasks)} 项。'})
    if 'automation' in sources:
        runs=db.execute('SELECT snapshot,state,created FROM automation_runs WHERE created>=? ORDER BY created DESC LIMIT 30',(start.isoformat(),)).fetchall()
        sections.append({'title':'自动化运行','text':'\n'.join(json.loads(r['snapshot'])['name']+'：'+r['state'] for r in runs) or '本周没有自动化运行。'})
    return {'period': {'from': start.date().isoformat(), 'to': end.date().isoformat()}, 'posts': posts,'sections':sections}


def send_email(config, subject, body, recipient=None):
    target = recipient or config['recipient']
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = formataddr(('个人空间', config['sender']))
    message['To'] = target
    message.set_content(body)
    client = _connect(config)
    try:
        try:
            refused = client.send_message(message)
            if refused: raise smtplib.SMTPRecipientsRefused(refused)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            raise
        except Exception as error:
            raise DeliveryUnknown(type(error).__name__) from None
    finally:
        try: client.quit()
        except Exception: pass


def report_text(data, site_url):
    lines = [f"个人空间周报（{data['period']['from']} 至 {data['period']['to']}）", '', f"本周发布 {len(data['posts'])} 篇文章。", '']
    lines.extend(f"- {p['title']}  {site_url}/blog/{p['slug']}" for p in data['posts'])
    if not data['posts']: lines.append('本周没有发布文章。')
    for section in data.get('sections',[]):lines.extend(['',section['title'],section['text']])
    return '\n'.join(lines)


def recover_interrupted(store):
    with store.transaction() as db:
        db.execute("UPDATE email_runs SET status='unknown',finished=?,error='服务重启前未确认投递结果，请检查收件箱' WHERE status='sending'", (stamp(),))


async def scheduler(app):
    while True:
        try:
            await asyncio.sleep(30)
            with app.state.store.connect() as db:
                config = meta(db, CONFIG_KEY, {})
                if not config.get('enabled'): continue
                now = datetime.now(ZoneInfo(config['timezone']))
                if now.weekday() != config['weekday'] or now.strftime('%H:%M') != config['sendTime']: continue
                schedule_key = now.strftime('%G-W%V')
                if config.get('lastScheduledKey') == schedule_key: continue
                data = report(db, now)
            from .api import deliver_report
            await asyncio.to_thread(deliver_report, app, 'scheduled', schedule_key, data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Weekly email scheduler failed')

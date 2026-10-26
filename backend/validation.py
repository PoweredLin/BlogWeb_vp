"""Validate the preserved V8 wire contract, including cross-field invariants."""
import copy
import json
import re
from datetime import date, datetime
from pathlib import Path
from jsonschema import Draft202012Validator, validators

CONTRACT = json.loads((Path(__file__).parent / 'contracts/v8.json').read_text(encoding='utf-8'))
DEFAULT_PROFILE = CONTRACT['defaultProfile']
DEFAULT_STORY = CONTRACT['defaultStory']
AWARDS = CONTRACT['awards']


class Problem(Exception):
    def __init__(self, status, message, **extra):
        self.status, self.message, self.extra = status, message, extra


def fail(status, message, **extra):
    raise Problem(status,message,**extra)


def _properties(validator, properties, instance, schema):
    if isinstance(instance, dict):
        for key, prop in properties.items():
            if key not in instance and 'default' in prop:
                instance[key] = copy.deepcopy(prop['default'])
    yield from Draft202012Validator.VALIDATORS['properties'](validator,properties,instance,schema)


Validator = validators.extend(Draft202012Validator, {'properties': _properties})


def text(value, maximum=200, minimum=0, trim=False):
    if not isinstance(value,str): fail(400,'请输入文字')
    value = value.strip() if trim else value
    if not minimum <= len(value) <= maximum: fail(400,f'文字长度应为 {minimum}–{maximum}')
    return value


def choice(value, options):
    if value not in options: fail(400,'选项无效')
    return value


def number(value, low, high, integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not low <= value <= high or (integer and int(value)!=value): fail(400,'数值超出范围')
    return value


def image_path(value, empty=False):
    if empty and value=='': return value
    if not isinstance(value,str) or not re.fullmatch(r'/(assets|uploads)/[\w-]+\.(png|jpeg|webp)',value, re.ASCII): fail(400,'图片必须使用本站图片路径')
    return value


def validate_schema(schema, body):
    if not isinstance(body,dict): fail(400,'请求内容必须是对象')
    result = copy.deepcopy({k:v for k,v in body.items() if k in schema.get('properties',{})})
    errors = list(Validator(schema).iter_errors(result))
    if errors: fail(400,'请检查填写内容：'+'.'.join(map(str,errors[0].path)))
    return result


def timestamp(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None: fail(400,'时间必须包含时区')
        return dt.timestamp()
    except (ValueError,TypeError,AttributeError): fail(400,'时间格式无效')


def validate_record(kind,body):
    if kind not in CONTRACT['schemas']: fail(404,'记录类型不存在')
    b=validate_schema(CONTRACT['schemas'][kind],body)
    for key in ('date','due'):
        if key in b:
            try: date.fromisoformat(b[key])
            except ValueError: fail(400,'日期无效')
    if 'title' in b: b['title']=text(b['title'],200,1,True)
    if kind=='habits':
        for key in b['checks']:
            try: date.fromisoformat(key)
            except ValueError: fail(400,'打卡日期无效')
    if kind=='sleep':
        duration=timestamp(b['end'])-timestamp(b['start'])
        if not 0<duration<=48*3600: fail(400,'起床时间必须晚于入睡时间，且在 48 小时内')
        if abs(sum(b[k] for k in ('deep','light','rem','awake'))*60-duration)>=60.001: fail(400,'睡眠阶段合计应与起止时长一致')
    if kind=='library' and b['progress']>b['total']: fail(400,'进度不能超过总进度')
    if kind=='posts':
        timestamp(b['publishAt'])
        if b.get('origin_url') and not re.match(r'^https?://',b['origin_url'],re.I): fail(400,'原文链接必须为 HTTP(S)')
        b['category']=taxonomy_name(b['category'])
        tags=[taxonomy_name(t) for t in b['tags'].replace('，',',').split(',') if t.strip()]
        if len(tags)>20: fail(400,'最多 20 个标签')
        b['tags']=','.join(dict.fromkeys(tags))
    return b


def taxonomy_name(value):
    value=text(value,60,1,True)
    if any(c in value for c in ',，\r\n'): fail(400,'分类标签不能包含逗号或换行')
    return value


PROFILE_DEFAULTS={'avatar':'/favicon.svg','bio':'','gitProvider':'github','gitUsername':'','theme':'minimal','customWallpaper':'','wallpaperOpacity':24,'motion':True}
SITE_DEFAULTS={'blogTheme':'paper','listStyle':'editorial','motion':True,'showTicker':True,'showSidebar':True,'previewImages':True,'blogBackground':'','coverImage':'','title':'Lin 的随手记','subtitle':'偶尔写代码，经常想太多。这里是我的一些记录。','notice':'欢迎来坐坐。关于技术、生活，以及途中遇见的故事。','cover':'landscape-fields','commentsEnabled':True,'heroMode':'poster','heroImages':['landscape-eye','landscape-fantasy','dimension-sunset','landscape-study'],'heroInterval':8,'heroLabel':'A PLACE TO SLOW DOWN','heroTitle':'','heroTail':'','heroIntro':'','heroOverlay':30,'heroine':'atri','scrollCue':'往下翻翻','avatarBg':'/assets/landscape-room.webp'}
COVERS=['landscape-'+s for s in ['dawn','fields','room','study','fantasy','orbit','journey','eye','games']]+['dimension-'+s for s in ['sunset','blue','gold','violet','pink']]


def site_settings(body):
    result=copy.deepcopy(SITE_DEFAULTS)
    result.update({k:v for k,v in body.items() if k in result})
    for key,options in {'blogTheme':['paper','gallery'],'listStyle':['editorial','grid'],'heroMode':['poster','collage'],'cover':COVERS,'heroine':['atri','charlotte','wada','cafe','flower','may']}.items(): choice(result[key],options)
    for key in ['motion','showTicker','showSidebar','previewImages','commentsEnabled']:
        if not isinstance(result[key],bool): fail(400,'开关必须是布尔值')
    for key,limit in {'title':80,'subtitle':160,'notice':500,'heroLabel':60,'heroTitle':60,'heroTail':20,'heroIntro':120,'scrollCue':16}.items(): result[key]=text(result[key],limit,1 if key=='title' else 0)
    number(result['heroInterval'],3,60,True); number(result['heroOverlay'],0,80,True)
    for key in ['blogBackground','coverImage','avatarBg']: image_path(result[key],key!='avatarBg')
    if not isinstance(result['heroImages'],list) or not 1<=len(result['heroImages'])<=6: fail(400,'选择 1–6 张首页图片')
    for img in result['heroImages']:
        if img not in COVERS: image_path(img)
    return result


def member_profile(body):
    b={**PROFILE_DEFAULTS,**{k:v for k,v in body.items() if k in PROFILE_DEFAULTS}}
    b['name']=text(body.get('name'),80,1,True)
    b['bio']=text(b['bio'],1000)
    if b['avatar']!='/favicon.svg': image_path(b['avatar'])
    choice(b['gitProvider'],['github','gitee']); choice(b['theme'],['minimal','cozy'])
    if not isinstance(b['gitUsername'],str) or (b['gitUsername'] and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,38}',b['gitUsername'])): fail(400,'Git 用户名格式无效')
    image_path(b['customWallpaper'],True); number(b['wallpaperOpacity'],0,70,True)
    if not isinstance(b['motion'],bool): fail(400,'动效选项无效')
    number(body.get('version'),1,2**53,True)
    return b


def journal_data(kind,body):
    choice(kind,['albums','moments'])
    b={'title':text(body.get('title',''),100,trim=True),'content':text(body.get('content',''),6000),'mood':choice(body.get('mood','晴'),['晴','雨','游戏中','追番中','出走','灵感']),'status':choice(body.get('status'),['published','private','draft']),'images':[]}
    images=body.get('images',[])
    if not isinstance(images,list) or len(images)>60: fail(400,'图片数量无效')
    for img in images:
        if not isinstance(img,dict): fail(400,'图片格式无效')
        b['images'].append({'url':image_path(img.get('url')),'caption':text(img.get('caption',''),200)})
    if kind=='albums' and (not b['title'] or not b['images']): fail(400,'相册需要标题和图片')
    if kind=='moments' and not b['content'].strip() and not b['images']: fail(400,'说说需要内容或图片')
    return b

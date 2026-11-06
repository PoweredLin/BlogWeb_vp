"""Finite, versioned module layout configuration. Never store code or CSS."""
import copy
import re
from fastapi import APIRouter,Request
from .storage import meta,set_meta,audit
from .validation import fail,image_path
router=APIRouter(prefix='/api')
DEFAULT={
 'home':[{'id':'profile','enabled':False},{'id':'anime','enabled':True},{'id':'web','enabled':False},{'id':'articles','enabled':True},{'id':'moments','enabled':False},{'id':'albums','enabled':False}],
 'room':[{'id':'stage','enabled':True},{'id':'stats','enabled':True},{'id':'progress','enabled':True},{'id':'shelf','enabled':True},{'id':'git','enabled':True}],
 'accent':'violet','introEnabled':True,'introReplay':'session',
 'introPhotoMode':'auto','introPhotos':[],'introTitle':'','animeAutoPublic':True,
 'animeSeason':'auto','animeLimit':10,'webDocumentId':''
}

def config(db):
    value={'version':1,**copy.deepcopy(DEFAULT),**meta(db,'pageLayout',{})}
    for section in ('home','room'):
        present={row['id'] for row in value[section]}
        value[section]=value[section]+[copy.deepcopy(row) for row in DEFAULT[section] if row['id'] not in present]
    return value

def validate(body):
    result={}
    for section in ('home','room'):
        rows=body.get(section);ids=[x['id'] for x in DEFAULT[section]]
        if not isinstance(rows,list) or len(rows)!=len(ids):fail(400,'模块列表不完整')
        if any(not isinstance(row,dict) or row.get('id') not in ids or not isinstance(row.get('enabled'),bool) for row in rows):fail(400,'模块配置无效')
        if len({row['id'] for row in rows})!=len(ids):fail(400,'模块重复')
        result[section]=[{'id':r['id'],'enabled':r['enabled']} for r in rows]
    if not any(r['id']=='articles' and r['enabled'] for r in result['home']):fail(400,'文章列表不能关闭')
    if body.get('accent') not in ('violet','forest','ocean','rose'):fail(400,'主题强调色无效')
    if not isinstance(body.get('introEnabled'),bool) or body.get('introReplay') not in ('session','always','once'):fail(400,'片头配置无效')
    if body.get('introPhotoMode') not in ('auto','custom'):fail(400,'片头图片来源无效')
    photos=body.get('introPhotos')
    if not isinstance(photos,list) or len(photos)>18 or any(not isinstance(url,str) for url in photos):fail(400,'片头图片数量无效')
    photos=list(dict.fromkeys(image_path(url) for url in photos))
    title=body.get('introTitle','')
    if not isinstance(title,str) or len(title)>24:fail(400,'片头文字最多 24 字')
    anime_public=body.get('animeAutoPublic',True)
    if not isinstance(anime_public,bool):fail(400,'番剧公开设置无效')
    season=body.get('animeSeason','auto');limit=body.get('animeLimit',10);document=body.get('webDocumentId','')
    if not isinstance(season,str) or (season!='auto' and not re.fullmatch(r'[0-9]{4}-Q[1-4]',season)):fail(400,'首页番剧季度无效')
    if type(limit) is not int or not 1<=limit<=24:fail(400,'首页番剧数量须为 1–24')
    if not isinstance(document,str) or len(document)>80:fail(400,'首页文档选择无效')
    return {**result,'accent':body['accent'],'introEnabled':body['introEnabled'],'introReplay':body['introReplay'],'introPhotoMode':body['introPhotoMode'],'introPhotos':photos,'introTitle':title.strip(),'animeAutoPublic':anime_public,'animeSeason':season,'animeLimit':limit,'webDocumentId':document}

@router.get('/page-layout')
def public_layout(request:Request):
    with request.app.state.store.connect() as db:
        value=config(db)
        return {k:value[k] for k in ('home','accent','introEnabled','introReplay','introPhotoMode','introPhotos','introTitle','animeAutoPublic','animeSeason','animeLimit','webDocumentId')}

@router.get('/private/page-layout')
def read_layout(request:Request):
    with request.app.state.store.connect() as db:return config(db)

@router.put('/private/page-layout')
def save_layout(request:Request,body:dict):
    value=validate(body)
    with request.app.state.store.transaction() as db:
        old=config(db)
        if body.get('version')!=old['version']:fail(409,'页面布局已更新，请刷新后保存')
        value['version']=old['version']+1;set_meta(db,'pageLayout',value);audit(db,'page-layout:update')
        return value

@router.post('/private/page-layout/reset')
def reset_layout(request:Request,body:dict):
    with request.app.state.store.transaction() as db:
        old=config(db)
        if body.get('version')!=old['version']:fail(409,'页面布局已更新，请刷新')
        value={**copy.deepcopy(DEFAULT),'version':old['version']+1};set_meta(db,'pageLayout',value);audit(db,'page-layout:reset');return value

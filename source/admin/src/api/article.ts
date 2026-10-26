import {request,result,article,posts,cachedPosts,update} from '@/integration/service';
export type ArticleResult={code:number;message:string;result:any};
export async function getArticleList(p:any={}){let rows=(await posts()).map(article).filter(x=>(!p.article_title||x.article_title.includes(p.article_title))&&(!p.category_id||x.category_id===p.category_id)&&(!p.tag_id||x.tagIdList.includes(p.tag_id))&&(!p.is_top||x.is_top===Number(p.is_top))&&(!p.status||x.status===p.status)&&(!p.create_time||x.createdAt>=p.create_time[0]&&x.createdAt<=p.create_time[1]));return result({list:rows.slice(((p.current||1)-1)*(p.size||10),(p.current||1)*(p.size||10)),total:rows.length});}
function form(b:any){return {...b,title:b.article_title,content:b.article_content,excerpt:b.article_description,cover:b.article_cover,category:b.category?.category_name||b.category_id||'日常手记',tags:(b.tagList||[]).map(t=>t.tag_name).join(','),featured:b.is_top===1,status:b.status===1?'published':b.status===2?'private':'draft',publishAt:b.publishAt||new Date().toISOString(),slug:b.slug||'post-'+b.clientId,demo:false};}
export async function addArticle(b:any){return result(article(await request('/api/studio/posts','POST',form(b))));}
export async function editArticle(b:any){return result(article(await request('/api/studio/posts/'+b.id,'PUT',form(b))));}
export async function getArticleById(id:string){const p=(await posts()).find(p=>p.id===id);if(!p)throw Error('文章不存在或无权访问');return result(article(p));}
export async function deleteArticle(id:string){const p=cachedPosts.get(id);if(!p)throw Error('请刷新列表');return result(await request('/api/studio/posts/'+id,'DELETE',{version:p.version}));}
export const updateArticleTop=(id,is_top)=>update(id,{featured:is_top===1});
export const isArticlePublic=(id,status)=>update(id,{status:status===1?'private':'published'});
export const revertArticle=(id)=>update(id,{status:'draft'});
export async function titleExist(b:any){return result((await posts()).some(p=>p.id!==b.id&&p.title===b.article_title));}

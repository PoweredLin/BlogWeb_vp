import {articles,request,result,article,page} from '@/integration/service';
export async function homeGetArticleList(current,size){return result(page((await articles()).sort((a,b)=>a.is_top-b.is_top || (a.order||999)-(b.order||999)),current,size));}
export async function blogTimelineGetArticleList(current,size){const all=await articles(),part=page(all,current,size);return result({...part,list:[...new Set(part.list.map(p=>p.createdAt.slice(0,4)))].map(year=>({year,articleList:part.list.filter(p=>p.createdAt.startsWith(year))}))});}
export async function getArticleListByTagId(p){return result(page((await articles()).filter(a=>a.tagNameList.includes(p.id)),p.current,p.size));}
export async function getArticleListByCategoryId(p){return result(page((await articles()).filter(a=>a.category_id===p.id),p.current,p.size));}
export async function getArticleById(id){return result(article(await request('/api/public/posts/'+encodeURIComponent(id))));}
export async function getRecommendArticleById(id){const a=await articles(),i=a.findIndex(p=>p.id===id);return result({previous:a[i-1]||{},next:a[i+1]||{},recommend:a.filter(p=>p.id!==id).slice(0,3)});}
export async function getHotArticle(){return result((await articles()).slice(0,5));}
export async function getArticleByContent(q){return result((await articles()).filter(p=>[p.article_title,p.article_description,p.searchText,p.tags].join(' ').toLowerCase().includes(q.toLowerCase())));}
export async function readingDuration(){return result(null);}

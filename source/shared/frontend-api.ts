/** Stable read-model types for the next frontend. Writes keep their existing versioned APIs. */
export interface Page<T>{items:T[];total:number;page:number;pageSize:number;hasMore:boolean}
export interface AnimePoster{id:string;title:string;cover:string;season:string;broadcast:string;creator:string;tags:string;weekday:''|'一'|'二'|'三'|'四'|'五'|'六'|'日'}
export interface AnimePage extends Page<AnimePoster>{seasons:string[]}
export interface MediaItem{url:string;name:string;source:'assets'|'uploads';bytes:number;public:boolean}
export interface DocumentSummary{id:string;title:string;category:string;excerpt:string;version:number;created:string;updated:string}
export interface RunSummary{id:string;flowId:string;name:string;state:string;error:string;created:string;updated:string}
export interface PublicBookmark{id:string;title:string;url:string;description:string;tags:string;public:true;embeddable:boolean}
export type HomeModule={id:'articles'|'anime'|'profile'|'web'|'moments'|'albums';data:Record<string,unknown>};
export interface HomeResponse{accent:'violet'|'forest'|'ocean'|'rose';modules:HomeModule[]}

/** Session-only helper. Bearer tokens belong to local agents, never to a public bundle. */
export async function readApi<T>(path:string,signal?:AbortSignal):Promise<T>{
 const response=await fetch(path,{credentials:'same-origin',signal,headers:{Accept:'application/json'}});
 const data=await response.json();
 if(!response.ok)throw Object.assign(new Error(data.error||'请求失败'),{status:response.status});
 return data as T;
}
export function pageQuery(values:Record<string,string|number|undefined>):string{
 const query=new URLSearchParams();for(const [key,value] of Object.entries(values))if(value!==undefined)query.set(key,String(value));return query.toString();
}

import {publicData,result} from '@/integration/service';
export async function getAllTag(){const d=await publicData();return result([...new Set(d.posts.flatMap(p=>p.tags.split(/[,，]/)).filter(Boolean))].map(n=>({id:n,tag_name:n})));}

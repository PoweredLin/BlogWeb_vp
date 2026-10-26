import {publicData,result} from '@/integration/service';
export async function getAllCategory(){const d=await publicData();return result([...new Set(d.posts.map(p=>p.category))].map(n=>({id:n,category_name:n})));}

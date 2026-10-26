import {request,result} from '@/integration/service';
export async function getCategoryDictionary(){const data=await request('/api/studio/taxonomy');return result(data.categories.map(name=>({id:name,category_name:name})));}

import {request,result} from '@/integration/service';
export async function getTagDictionary(){const data=await request('/api/studio/taxonomy');return result(data.tags.map(name=>({id:name,tag_name:name})));}

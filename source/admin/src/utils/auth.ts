export interface DataInfo<T>{token?:string;username?:string;role?:number;}
export const sessionKey='source-admin-profile',TokenKey='unused-cookie-auth';
export const getToken=()=>null;export function setToken(){}export function removeToken(){sessionStorage.removeItem(sessionKey);sessionStorage.removeItem('blogCurrentUser');}

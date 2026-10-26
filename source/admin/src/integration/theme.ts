export {darken,lighten} from '@pureadmin/theme/dist/browser-utils';
export function toggleTheme({scopeName='layout-theme-default'}={}){const root=document.documentElement;for(const cls of [...root.classList])if(cls.startsWith('layout-theme-'))root.classList.remove(cls);root.classList.add(scopeName);}

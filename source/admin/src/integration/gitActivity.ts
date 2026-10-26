import { request } from './service';

// Session-local only: never leave private account information in localStorage.
let value: any = null;
let expires = 0;
let pending: Promise<any> | null = null;
let generation = 0;
export function clearGitActivity() { generation++; value = null; expires = 0; pending = null; }
window.addEventListener('lin-git-reset', clearGitActivity);
export function getGitActivity() {
  if (value && Date.now() < expires) return Promise.resolve(value);
  if (pending) return pending;
  const current = generation;
  pending = request('/api/studio/git').then(data => {
    if (current !== generation) return null;
    value = data;
    // First refresh is asynchronous; a later explicit click may read its result.
    expires = Date.now() + (data.refreshing ? 8000 : 60000);
    return data;
  }).finally(() => { if (current === generation) pending = null; });
  return pending;
}

let cached, expires = 0, pending;
export function getGitActivity(api) {
  if (cached && Date.now() < expires) return Promise.resolve(cached);
  if (pending) return pending;
  pending = api('/api/studio/git').then(data => {
    cached = data; expires = Date.now() + (data.refreshing ? 8000 : 60000); return data;
  }).finally(() => { pending = null; });
  return pending;
}

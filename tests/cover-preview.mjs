import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lin-cover-preview-'));
const origin = 'http://127.0.0.1:4356';
const python = process.env.PYTHON || (process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const server = spawn(python, ['-m', 'backend.run'], {
  env: { ...process.env, APP_ENV: 'development', COOKIE_SECURE: 'false', DATA_DIR: directory, PORT: '4356' },
  stdio: 'ignore'
});
let browser;
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try { ready = (await fetch(origin + '/healthz')).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(ready, 'isolated backend started');
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Users/JLZ/.agent-browser/browsers/chrome-153.0.8010.36/chrome.exe' });
  const context = await browser.newContext();
  const page = await context.newPage();
  const api = async (url, method = 'GET', data) => {
    const response = await context.request.fetch(origin + url, { method, headers: { Origin: origin }, data });
    assert(response.ok(), await response.text());
    return response.json();
  };
  await api('/api/setup', 'POST', { name: 'Cover test', password: 'cover-test-password', demo: true });
  const response = await page.goto(origin + '/admin/article/addArticle');
  assert(response.headers()['content-security-policy'].includes("img-src 'self' data: blob:"));
  await page.getByPlaceholder('请输入文章标题').fill('封面预览回归');
  await page.locator('.cm-content').fill('## Preview\n\nCover preview test.');
  await page.getByRole('button', { name: '发布文章', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '发布文章' });
  await dialog.getByPlaceholder('说点儿什么，太抽象了可不好').fill('封面图片的测试文章');
  await dialog.locator('.el-select__wrapper').nth(0).click();
  await page.getByRole('option', { name: '技术笔记', exact: true }).click();
  await dialog.locator('.el-select__wrapper').nth(1).click();
  await page.getByRole('option', { name: '开发', exact: true }).click();
  await page.keyboard.press('Escape');
  await dialog.getByText('文章标题', { exact: true }).click();
  const cover = dialog.locator('.article-cover');
  await cover.locator('.el-upload-list__item').hover();
  await cover.getByRole('button', { name: '移除封面', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.article-cover .el-upload-list__item').length === 0);
  await cover.locator('input[type=file]').setInputFiles('public/assets/landscape-fields.webp');
  const image = cover.locator('img.el-image__inner');
  await image.waitFor();
  await page.waitForFunction(() => {
    const img = document.querySelector('.article-cover img.el-image__inner');
    return img?.complete && img.naturalWidth > 0 && img.src.startsWith('blob:');
  });
  await cover.locator('.el-upload-list__item').hover();
  await cover.getByRole('button', { name: '预览封面', exact: true }).click();
  await page.locator('.el-image-viewer__img').waitFor();
  assert(await page.locator('.el-image-viewer__img').evaluate(img => img.complete && img.naturalWidth > 0));
  await page.keyboard.press('Escape');

  // A real decode failure must have actionable feedback, not an endless spinner.
  await cover.locator('.el-upload-list__item').hover();
  await cover.getByRole('button', { name: '移除封面', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.article-cover .el-upload-list__item').length === 0);
  await cover.locator('input[type=file]').setInputFiles({ name: 'broken.png', mimeType: 'image/png', buffer: Buffer.from('not an image') });
  await cover.getByRole('alert').waitFor();
  await cover.getByRole('button', { name: '重新加载' }).click();
  await cover.getByRole('alert').waitFor();
  await cover.locator('.el-upload-list__item').hover();
  await cover.getByRole('button', { name: '移除封面', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.article-cover .el-upload-list__item').length === 0);
  await cover.locator('input[type=file]').setInputFiles('public/assets/landscape-dawn.webp');
  await page.waitForFunction(() => document.querySelector('.article-cover img.el-image__inner')?.naturalWidth > 0);
  await dialog.getByRole('button', { name: '保存草稿', exact: true }).click();
  await page.waitForURL('**/admin/article/articleList');
  const post = (await api('/api/studio/posts')).find(post => post.title === '封面预览回归');
  assert(post?.cover.startsWith('/uploads/'));
  assert.equal((await context.request.get(origin + post.cover)).status(), 200);
  assert.equal((await fetch(origin + post.cover)).status, 404, 'draft cover stays private');
  fs.mkdirSync('test-results', { recursive: true });
  fs.writeFileSync('test-results/cover-preview.json', JSON.stringify({ blobPreview: true, fullscreenPreview: true, invalidImageFeedback: true, retry: true, uploadedDraftCover: true, privateBeforePublication: true }, null, 2));
  console.log('PASS Local blob preview, enlarged preview, failed-image retry and private uploaded draft cover');
} finally {
  await browser?.close();
  server.kill();
}

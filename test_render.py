import asyncio
import aiohttp
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
import os

HTML = """<!doctype html>
<html><head><meta charset='utf-8'><title>测试</title></head>
<body><h1>今日发言排行榜（测试）</h1><p>这是用于验证回退渲染的测试页面。</p></body></html>
"""

OUTPUT = "test_rank.png"

async def upload_html(html: str) -> str:
    form = aiohttp.FormData()
    form.add_field('file', html.encode('utf-8'), filename='rank.html', content_type='text/html')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post('https://0x0.st', data=form, timeout=30) as resp:
            text = await resp.text()
            if resp.status == 200:
                return text.strip()
            else:
                raise Exception(f'upload failed {resp.status}: {text}')

async def fetch_screenshot(raw_url: str, outpath: str):
    sg_url = f"https://screenshot.guru/create?url={quote_plus(raw_url)}&width=840&height=600"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/*,text/html;q=0.9,*/*;q=0.8'
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(sg_url, timeout=60) as resp:
            if resp.status == 200:
                ctype = resp.headers.get('Content-Type','')
                if ctype.startswith('image/'):
                    data = await resp.read()
                    with open(outpath, 'wb') as f:
                        f.write(data)
                    return outpath
                else:
                    text = await resp.text()
                    # try to find image url
                    for line in text.splitlines():
                        if line.strip().startswith('http') and ('.png' in line or '.jpg' in line or '.jpeg' in line):
                            img_url = line.strip()
                            async with session.get(img_url, timeout=30) as r2:
                                if r2.status == 200 and r2.headers.get('Content-Type','').startswith('image/'):
                                    data = await r2.read()
                                    with open(outpath, 'wb') as f:
                                        f.write(data)
                                    return outpath
                    raise Exception('screenshot.guru returned non-image response')
            else:
                text = await resp.text()
                raise Exception(f'screenshot.guru error {resp.status}: {text}')

async def main():
    # First try: local Playwright using system Chrome/Chromium if available
    async def try_local_playwright(html, outpath):
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Chromium\Application\chrome.exe",
        ]
        for p in possible_paths:
            if os.path.exists(p):
                try:
                    async with async_playwright() as playwright:
                        browser = await playwright.chromium.launch(executable_path=p, headless=True)
                        page = await browser.new_page(viewport={"width":840, "height":600})
                        await page.set_content(html)
                        await page.screenshot(path=outpath)
                        await browser.close()
                        return outpath
                except Exception as e:
                    print('Local Playwright launch failed with executable', p, e)
        return None

    print('Trying local Playwright with system Chrome...')
    local_out = await try_local_playwright(HTML, OUTPUT)
    if local_out:
        print('Saved screenshot locally to', local_out)
        return

    # First try: use data URI to avoid upload (short HTML should work)
    data_uri = 'data:text/html;charset=utf-8,' + quote_plus(HTML)
    print('Requesting screenshot from screenshot.guru via data URI...')
    try:
        out = await fetch_screenshot(data_uri, OUTPUT)
    except Exception as e:
        print('Data-URI render failed, falling back to upload:', e)
        print('Uploading HTML to 0x0.st...')
        raw_url = await upload_html(HTML)
        print('Uploaded:', raw_url)
        print('Requesting screenshot from screenshot.guru...')
        out = await fetch_screenshot(raw_url, OUTPUT)
    print('Saved screenshot to', out)

if __name__ == '__main__':
    asyncio.run(main())

import concurrent.futures, hashlib, json, re, subprocess, threading, time, uuid, webbrowser, sys, os
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, urljoin, parse_qs, urlencode

ROOT = Path(__file__).parent
CACHE = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'AcgReader' / 'cache' if getattr(sys, 'frozen', False) else ROOT / '.cache'
CACHE.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.RLock()
CANCEL = {}
PROCESSES = {}
HLS_RESOURCES = {}

class Cancelled(Exception): pass

def start_curl(url, job_id=None, output=None, media=False):
    limit = '300' if media == 'video' or output else '60' if media else '35'
    args = ['curl.exe', '--fail', '--silent', '--show-error', '--location', '--max-redirs', '4', '--connect-timeout', '10', '--speed-limit', '1024', '--speed-time', '20', '--max-time', limit, '--proto', '=https', '--proto-redir', '=https', '-A', 'Mozilla/5.0']
    # Retries for streamed media must start a fresh HTTP response, never append bytes.
    if not media: args += ['--retry', '2', '--retry-delay', '1']
    if output: args += ['-o', str(output)]
    with LOCK:
        if job_id and CANCEL.setdefault(job_id, threading.Event()).is_set(): raise Cancelled()
        p = subprocess.Popen(args + [url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000 if os.name == 'nt' else 0)
        if job_id: PROCESSES.setdefault(job_id, set()).add(p)
    return p

def curl(url, job_id=None, output=None):
    p = start_curl(url, job_id, output)
    try:
        out, err = p.communicate()
        if job_id and CANCEL[job_id].is_set(): raise Cancelled()
        if p.returncode: raise RuntimeError(err.decode('utf-8', 'replace')[-250:])
        return out
    finally:
        with LOCK:
            if job_id: PROCESSES.get(job_id, set()).discard(p)

def cancel_job(job):
    with LOCK:
        CANCEL.setdefault(job['id'], threading.Event()).set()
        for p in list(PROCESSES.get(job['id'], set())):
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
        job.update(status='cancelled', results={}, errors={})
        JOBS.pop(job['id'], None)
        for key in list(HLS_RESOURCES):
            if key[0] == job['id']: HLS_RESOURCES.pop(key, None)
        saved = CACHE / (hashlib.sha256(job['base'].encode()).hexdigest() + '.json')
        saved.unlink(missing_ok=True)

def normalize(url):
    p = urlsplit(url.strip())
    m = re.fullmatch(r'/([a-zA-Z0-9_]+)/([0-9]+)(?:-([0-9]+))?\.html', p.path)
    if p.scheme not in ('http', 'https') or p.hostname not in ('acgmhaa.com', 'www.acgmhaa.com') or p.port not in (None, 80, 443) or p.username or not m:
        raise ValueError('请输入 acgmhaa.com 的作品页面链接，例如 /h/902864-2.html')
    return 'https://www.acgmhaa.com/' + m[1] + '/' + m[2], int(m[3] or 1)

def page_url(base, page):
    return base + (f'-{page}' if page > 1 else '') + '.html'

def fetch(url, job_id=None):
    # Windows curl uses the system certificate store; certificate verification stays enabled.
    return curl(url, job_id).decode('utf-8', 'replace')

class Parser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.stack, self.media, self.pages, self.title = base, [], [], {1}, ''
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        active = any(x[1] for x in self.stack) or bool(set(a.get('class', '').split()) & {'manga-page', 'manga-picture', 'video-content', 'video-player', 'anime-player'})
        if tag == 'a':
            try:
                b, n = normalize(urljoin(self.base + '.html', a.get('href', '')))
                if b == self.base: self.pages.add(n)
            except ValueError: pass
        in_video = tag == 'video' or any(x[0] == 'video' for x in self.stack)
        if active and tag in ('img', 'video', 'source', 'iframe'):
            src = a.get('data-original') or a.get('data-src') or a.get('src')
            if tag == 'source' and not in_video: src = (a.get('srcset') or src or '').split(',')[0].split(' ')[0]
            if src:
                url = urljoin(self.base + '.html', src)
                if urlsplit(url).scheme == 'https':
                    kind = 'embed' if tag == 'iframe' else 'video' if in_video else 'image'
                    self.media.append({'url': url, 'kind': kind})
        if tag not in ('img', 'source', 'link', 'meta', 'br', 'hr', 'input', 'area', 'embed', 'wbr'):
            self.stack.append((tag, active))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        if any(t[0] == 'h1' for t in self.stack): self.title += data

def parse(html, base):
    p = Parser(base); p.feed(html)
    # Read only the site's named player configuration; never execute page scripts.
    config = re.search(r'window\.acgPlayerConfig\s*=\s*\{([\s\S]*?)\}\s*;', html)
    if config:
        master = re.search(r'\bmasterUrl\s*:\s*("(?:[^"\\]|\\.)*")', config[1])
        if master:
            url = json.loads(master[1])
            if urlsplit(url).scheme == 'https' and urlsplit(url).path.endswith('.m3u8'):
                p.media.append({'url':url, 'kind':'video', 'format':'hls'})
    if not p.title.strip() or not p.media:
        raise ValueError('未找到正文媒体（可能是访问验证、页面结构变化，或此播放器暂不支持）')
    return {'title': p.title.strip(), 'media': p.media, 'pages': sorted(p.pages)}

def hls_resource(job_id, index, url):
    token = hashlib.sha256(url.encode()).hexdigest()
    with LOCK: HLS_RESOURCES[(job_id, index, token)] = url
    return '/api/hls?' + urlencode({'id':job_id,'index':index,'resource':token})

def rewrite_playlist(text, source, master, job_id, index):
    def resource(value):
        url = urljoin(source, value)
        parsed = urlsplit(url)
        if parsed.scheme != 'https': raise ValueError('不支持的视频分段协议')
        if parsed.path.endswith('.m3u8') and 'm' not in parse_qs(parsed.query):
            master_parts = urlsplit(master)
            query = parsed.query + ('&' if parsed.query else '') + master_parts.query
            query += ('&' if query else '') + urlencode({'from':master_parts.path})
            url = parsed._replace(query=query).geturl()
        return hls_resource(job_id, index, url)
    lines=[]
    for line in text.splitlines():
        if line and not line.startswith('#'): line = resource(line.strip())
        elif 'URI="' in line: line = re.sub(r'URI="([^"]+)"',lambda m:'URI="'+resource(m[1])+'"',line)
        lines.append(line)
    return '\n'.join(lines)+'\n'

def start_hls_download(job_id, index, port):
    binary = ROOT/'ffmpeg.exe'
    if not binary.exists(): raise ValueError('未安装视频合并组件，请使用更新后的桌面版')
    url = f'http://127.0.0.1:{port}/api/hls?' + urlencode({'id':job_id,'index':index})
    args=[str(binary),'-hide_banner','-loglevel','error','-nostdin','-rw_timeout','30000000','-allowed_extensions','ALL','-allowed_segment_extensions','ALL','-extension_picky','0','-seg_max_retry','2','-i',url,'-map','0:v:0','-map','0:a:0?','-c','copy','-bsf:a','aac_adtstoasc','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1']
    with LOCK:
        if CANCEL.setdefault(job_id,threading.Event()).is_set(): raise Cancelled()
        p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
        PROCESSES.setdefault(job_id,set()).add(p)
    return p

def crawl(job, retry=False):
    with LOCK:
        event = CANCEL.setdefault(job['id'], threading.Event())
        if event.is_set(): return
        job['status'] = 'running'
        targets = sorted(set(job['errors']) | (set(range(1, job['total']+1)) - set(job['results']))) if retry else [1]
        job['errors'] = {}
    def one(n):
        html = fetch(page_url(job['base'], n), job['id'])
        return parse(html, job['base'])
    pending = set(targets); done = set(job['results'])
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            while pending:
                if event.is_set(): return
                batch = sorted(pending)[:12]; pending.difference_update(batch)
                futures = {pool.submit(one, n): n for n in batch}
                for f in concurrent.futures.as_completed(futures):
                    n = futures[f]
                    with LOCK:
                        if event.is_set():
                            for future in futures: future.cancel()
                            return
                        try:
                            data = f.result(); job['results'][n] = data['media']
                            if n == 1: job['title'] = data['title']
                            last = max(data['pages'])
                            if last > 20000: raise ValueError('页数超过 20000，请检查作品分页')
                            job['total'] = max(job['total'], last)
                            pending.update(set(range(1, job['total']+1)) - done - set(batch) - set(job['errors']))
                        except Exception as e: job['errors'][n] = str(e)
                        done.add(n)
                    time.sleep(.12)
        with LOCK:
            if event.is_set(): return
            job['status'] = 'partial' if job['errors'] else 'complete'
    except Exception as e:
        with LOCK: job['status'] = 'partial'; job['errors'][0] = str(e)
    with LOCK:
        if event.is_set(): return
        (CACHE / (hashlib.sha256(job['base'].encode()).hexdigest() + '.json')).write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')

def snapshot(job):
    media, seen = [], set()
    for n, items in sorted(job['results'].items()):
        for item in items:
            if item['url'] not in seen:
                seen.add(item['url']); media.append(dict(item, page=n))
    return {k:v for k,v in job.items() if k != 'results'} | {'media':media, 'completed':len(job['results'])}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, data, mime='application/json; charset=utf-8', status=200):
        if not isinstance(data, bytes): data = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(data)
        except (ConnectionError, OSError): pass

    def stream_media(self):
        p = None
        headers_sent = False
        job_id = None
        try:
            query = parse_qs(urlsplit(self.path).query)
            with LOCK:
                job = JOBS[query['id'][0]]
                job_id = job['id']
                if job['status'] != 'complete': raise ValueError('请先完成提取')
                item = snapshot(job)['media'][int(query['index'][0])]
                if item['kind'] == 'embed': raise ValueError('外部播放器只能保存原链接')
            p = start_hls_download(job_id, int(query['index'][0]), self.server.server_port) if item.get('format') == 'hls' else start_curl(item['url'], job_id, media=item['kind'])
            first = p.stdout.read1(65536)
            if not first:
                _, error = p.communicate()
                if CANCEL[job_id].is_set(): raise Cancelled()
                raise ValueError(error.decode('utf-8', 'replace')[-250:] or '源站返回空文件')
            self.protocol_version = 'HTTP/1.1'
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            headers_sent = True
            chunk = first
            while chunk:
                if CANCEL[job_id].is_set(): raise Cancelled()
                self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                self.wfile.flush()
                chunk = p.stdout.read1(65536)
            _, error = p.communicate()
            if p.returncode or (item.get('format') == 'hls' and error.strip()): raise ValueError(error.decode('utf-8','replace')[-250:])
            self.wfile.write(b'0\r\n\r\n')
        except (Cancelled, ConnectionError, OSError): pass
        except Exception as e:
            if not headers_sent: self.send({'error': str(e)}, status=400)
        finally:
            self.close_connection = True
            if p:
                if p.poll() is None: p.kill()
                p.communicate()
                with LOCK: PROCESSES.get(job_id, set()).discard(p)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/': return self.send((ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/hls.min.js': return self.send((ROOT/'hls.min.js').read_bytes(), 'application/javascript')
        if path == '/api/hls':
            try:
                query=parse_qs(urlsplit(self.path).query)
                job_id=query['id'][0]; index=int(query['index'][0])
                with LOCK:
                    job=JOBS[job_id]; item=snapshot(job)['media'][index]
                    if item.get('format') != 'hls': raise ValueError('不是 HLS 视频')
                    url=HLS_RESOURCES[(job_id,index,query['resource'][0])] if 'resource' in query else item['url']
                data=curl(url,job_id)
                if urlsplit(url).path.endswith('.m3u8'):
                    text=data.decode('utf-8-sig')
                    if not text.startswith('#EXTM3U'): raise ValueError('源站未返回有效播放列表')
                    data=rewrite_playlist(text,url,item['url'],job_id,index).encode()
                    return self.send(data,'application/vnd.apple.mpegurl')
                return self.send(data,'application/octet-stream')
            except Cancelled: return
            except Exception as e: return self.send({'error':str(e)},status=400)
        if path == '/api/media':
            return self.stream_media()
        if path.startswith('/api/jobs/'):
            with LOCK:
                job = JOBS.get(path.rsplit('/',1)[1])
                return self.send(snapshot(job) if job else {'error':'任务不存在'}, status=200 if job else 404)
        self.send({'error':'不存在'}, status=404)
    def do_POST(self):
        try:
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'): raise ValueError('无效来源')
            data = json.loads(self.rfile.read(min(int(self.headers.get('Content-Length',0)), 8192)))
            if self.path == '/api/jobs':
                base, _ = normalize(data.get('url',''))
                with LOCK:
                    existing = next((j for j in JOBS.values() if j['base']==base and j['status'] != 'cancelled'), None)
                    if existing: return self.send(snapshot(existing))
                    job = dict(id=uuid.uuid4().hex, base=base, title='正在解析作品…', total=1, results={}, errors={}, status='running')
                    saved = CACHE/(hashlib.sha256(base.encode()).hexdigest()+'.json')
                    if saved.exists():
                        old=json.loads(saved.read_text(encoding='utf-8'))
                        fresh_id = job['id']
                        job.update(old); job['id'] = fresh_id; job['results']={int(k):v for k,v in old['results'].items()}; job['errors']={int(k):v for k,v in old['errors'].items()}
                        for n, items in list(job['results'].items()):
                            if any(m.get('format') == 'hls' for m in items):
                                del job['results'][n]; job['status']='partial'
                    JOBS[job['id']]=job
                    if job['status'] != 'complete':
                        job['status'] = 'running'
                        threading.Thread(target=crawl,args=(job, bool(job['results'])),daemon=True).start()
            elif self.path == '/api/retry':
                with LOCK:
                    job=JOBS[data['id']]
                    if job['status'] != 'running':
                        job['status'] = 'running'
                        threading.Thread(target=crawl,args=(job,True),daemon=True).start()
            elif self.path == '/api/reset':
                with LOCK:
                    job = JOBS.get(data.get('id'))
                    if job: cancel_job(job)
                return self.send({'ok':True})
            else: raise ValueError('未知操作')
            with LOCK: self.send(snapshot(job))
        except Exception as e: self.send({'error':str(e)}, status=400)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--desktop',action='store_true')
    options = parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',options.port),Handler)
    if not options.desktop:
        print(f'作品阅读器：http://127.0.0.1:{server.server_port} （Ctrl+C 退出）',flush=True)
        webbrowser.open(f'http://127.0.0.1:{server.server_port}')
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()

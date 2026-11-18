import unittest
import app
import threading
import http.client
import urllib.request
import tempfile
from pathlib import Path
from unittest.mock import patch

class ReaderTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(app.normalize('https://www.acgmhaa.com/h/902864-200.html')[0], app.normalize('https://acgmhaa.com/h/902864.html')[0])
        with self.assertRaises(ValueError): app.normalize('https://evil.com/h/1.html')

    def test_scope(self):
        html = '<h1>Test</h1><div class="manga-page"><img src="https://cdn.example/a.webp"><video><source src="https://cdn.example/b.mp4"></video></div><img src="https://cdn.example/ad.webp"><a href="/h/1-1200.html">last</a><a href="/h/2-9999.html">other</a>'
        p = app.parse(html, 'https://www.acgmhaa.com/h/1')
        self.assertEqual(p['pages'], [1,1200])
        self.assertEqual([m['kind'] for m in p['media']], ['image','video'])

    def test_order(self):
        j = {'results': {2:[{'url':'b'}],1:[{'url':'a'},{'url':'b'}]}}
        self.assertEqual([m['url'] for m in app.snapshot(j)['media']], ['a','b'])

    def test_challenge(self):
        with self.assertRaises(ValueError): app.parse('<title>Verify</title>', 'https://www.acgmhaa.com/h/1')

    def test_script_config_hls_without_video_src(self):
        html = r'''<h1>Video</h1><div class="anime-player"><video poster="https://cdn.example/cover.jpg"></video></div><script>window.acgPlayerConfig = { masterUrl: "https:\/\/cdn.example\/master.m3u8?m=abc\u0026t=123", ads:null };</script><img src="https://cdn.example/ad.jpg">'''
        p=app.parse(html,'https://www.acgmhaa.com/gif/1')
        self.assertEqual(p['media'],[{'url':'https://cdn.example/master.m3u8?m=abc&t=123','kind':'video','format':'hls'}])

    def test_hls_relative_playlists_keep_site_query_rules(self):
        master='https://cdn.example/video/master.m3u8?m=abc&t=123'
        text=app.rewrite_playlist('#EXTM3U\n720p/index.m3u8\n',master,master,'playlist-test',0)
        path=text.splitlines()[1]
        query=app.parse_qs(app.urlsplit(path).query)
        url=app.HLS_RESOURCES[('playlist-test',0,query['resource'][0])]
        parsed=app.urlsplit(url)
        self.assertEqual(parsed.path,'/video/720p/index.m3u8')
        self.assertEqual(app.parse_qs(parsed.query),{'m':['abc'],'t':['123'],'from':['/video/master.m3u8']})
        segment=app.rewrite_playlist('#EXTM3U\nindex0.ts\n',url,master,'playlist-test',0).splitlines()[1]
        token=app.parse_qs(app.urlsplit(segment).query)['resource'][0]
        self.assertEqual(app.HLS_RESOURCES[('playlist-test',0,token)],'https://cdn.example/video/720p/index0.ts')

    def test_cached_failure_returns_running_while_refetching(self):
        base='https://www.acgmhaa.com/gif/333'
        old=dict(id='old-partial',base=base,total=1,results={},errors={'1':'old parser failure'},status='partial',title='Test')
        with tempfile.TemporaryDirectory() as d, patch.object(app,'CACHE',Path(d)), patch.object(app,'crawl'):
            (Path(d)/(app.hashlib.sha256(base.encode()).hexdigest()+'.json')).write_text(app.json.dumps(old),encoding='utf-8')
            server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/jobs',data=app.json.dumps({'url':base+'.html'}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as response: job=app.json.load(response)
                self.assertEqual(job['status'],'running')
                self.assertNotEqual(job['id'],old['id'])
                app.JOBS.pop(job['id'],None)
            finally:server.shutdown();server.server_close()

    def test_reset_terminates_process_and_clears_results(self):
        j = dict(id='cancel-test', base='https://www.acgmhaa.com/h/1', results={1:[]}, errors={}, status='running')
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'CACHE', Path(d)):
            app.JOBS[j['id']] = j
            with patch('app.subprocess.Popen') as popen:
                p = popen.return_value
                p.poll.return_value = None
                app.PROCESSES[j['id']] = {p}
                app.cancel_job(j)
                p.kill.assert_called_once()
                p.wait.assert_called_once()
            self.assertTrue(app.CANCEL[j['id']].is_set())
            self.assertEqual(j['results'], {})
            self.assertNotIn(j['id'], app.JOBS)
            with self.assertRaises(app.Cancelled): app.fetch(j['base']+'.html', j['id'])

    def test_reset_during_crawl_cannot_repopulate_cache(self):
        j = dict(id='race-test',base='https://www.acgmhaa.com/h/1',results={},errors={},status='running',total=1,title='Test')
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set(); release.wait(3)
            return '<h1>Test</h1><div class="manga-page"><img src="https://cdn.example/a.webp"></div>'
        with tempfile.TemporaryDirectory() as d, patch.object(app,'CACHE',Path(d)), patch.object(app,'fetch',slow):
            t=threading.Thread(target=app.crawl,args=(j,)); t.start()
            self.assertTrue(entered.wait(3))
            app.cancel_job(j); release.set(); t.join(5)
            self.assertFalse(t.is_alive())
            self.assertEqual(j['results'],{})
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_media_stream_sends_bytes_before_download_finishes(self):
        release = threading.Event()
        class Source:
            count = 0
            def read1(self, size):
                self.count += 1
                if self.count == 1: return b'first'
                if self.count == 2:
                    release.wait(3)
                    return b'last'
                return b''
        class Process:
            stdout = Source()
            returncode = 0
            def communicate(self): return b'', b''
            def poll(self): return 0
        job=dict(id='stream-test', status='complete', results={1:[{'url':'https://cdn.example/1.webp','kind':'image'}]})
        app.JOBS[job['id']]=job
        app.CANCEL[job['id']]=threading.Event()
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(app,'start_curl',return_value=Process()):
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/media?id=stream-test&index=0',timeout=3) as response:
                    self.assertEqual(response.read(5),b'first')
                    self.assertFalse(release.is_set())
                    release.set()
                    self.assertEqual(response.read(),b'last')
            # A source failure after the first bytes must fail the HTTP stream,
            # allowing the browser to discard the partial file rather than save it.
            broken = Process()
            broken.stdout = Source()
            broken.returncode = 28
            with patch.object(app,'start_curl',return_value=broken):
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/media?id=stream-test&index=0',timeout=3) as response:
                    with self.assertRaises(http.client.IncompleteRead): response.read()
        finally:
            release.set();server.shutdown();server.server_close()
            app.JOBS.pop(job['id'],None)

    def test_cancelled_media_does_not_report_disconnected_client_error(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        errors=[]
        server.handle_error=lambda *args: errors.append(args)
        job=dict(id='cancel-http',status='complete',results={1:[{'url':'https://cdn.example/a.webp','kind':'image'}]})
        app.JOBS[job['id']]=job
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with patch.object(app,'start_curl',side_effect=app.Cancelled):
                try: urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/media?id=cancel-http&index=0',timeout=3)
                except Exception: pass
            self.assertEqual(errors,[])
        finally:
            server.shutdown();server.server_close();app.JOBS.pop(job['id'],None)

if __name__ == '__main__': unittest.main()

using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace AcgReader;
public class ReaderWindow : Form
{
    readonly WebView2 view = new() { Dock = DockStyle.Fill };
    readonly HttpClient http = new() { Timeout = TimeSpan.FromMinutes(7) };
    Process? backend;
    CancellationTokenSource? saving;
    string origin = "";
    readonly string dataRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AcgReader");
    public ReaderWindow()
    {
        Text = "Acg连页"; Width = 1900; Height = 1300; MinimumSize = new Size(760, 560);
        StartPosition = FormStartPosition.CenterScreen;
        Icon = Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
        BackColor = Color.FromArgb(17,20,18); Controls.Add(view);
        Shown += async (_,_) => { Size = new Size(1900, 1300); CenterToScreen(); try { await Start(); } catch(Exception e) {
            if(Environment.GetCommandLineArgs().Contains("--self-test")) File.WriteAllText(Path.Combine(dataRoot,"self-test.json"),JsonSerializer.Serialize(new {error=e.ToString()}));
            else MessageBox.Show(this, "应用启动失败："+e.Message, Text);
            Close(); } };
        FormClosed += (_,_) => { saving?.Cancel(); if(backend is {HasExited:false}) backend.Kill(true); backend?.Dispose(); http.Dispose(); };
    }
    async Task Start()
    {
        Directory.CreateDirectory(dataRoot);
        using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("AcgReader.backend")!;
        using var buffer = new MemoryStream(); await resource.CopyToAsync(buffer);
        byte[] bytes = buffer.ToArray();
        string binary = Path.Combine(dataRoot, "backend-"+Convert.ToHexString(SHA256.HashData(bytes))[..16]+".exe");
        if(!File.Exists(binary)) await File.WriteAllBytesAsync(binary,bytes);
        var listener = new TcpListener(IPAddress.Loopback,0); listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
        origin = $"http://127.0.0.1:{port}";
        backend = Process.Start(new ProcessStartInfo(binary,$"--desktop --port {port}") {UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=dataRoot});
        bool ready=false;
        for(int i=0;i<150;i++) { if(backend!.HasExited) throw new Exception("后台服务未能启动"); try { using var r=await http.GetAsync(origin); if(r.IsSuccessStatusCode) {ready=true;break;} } catch(HttpRequestException) {} await Task.Delay(200); }
        if(!ready) throw new Exception("等待后台服务超时");
        var environment = await CoreWebView2Environment.CreateAsync(null,Path.Combine(dataRoot,"WebView"));
        await view.EnsureCoreWebView2Async(environment);
        view.CoreWebView2.Settings.AreDevToolsEnabled=false;
        view.CoreWebView2.Settings.IsStatusBarEnabled=false;
        view.CoreWebView2.NewWindowRequested += (_,e) => { e.Handled=true; OpenExternal(e.Uri); };
        view.CoreWebView2.NavigationStarting += (_,e) => { if(!e.Uri.StartsWith(origin+"/")) {e.Cancel=true;OpenExternal(e.Uri);} };
        view.CoreWebView2.WebMessageReceived += async (_,e) =>
        {
            if(!e.Source.StartsWith(origin+"/")) return;
            try { using var doc=JsonDocument.Parse(e.WebMessageAsJson); var m=doc.RootElement;
                if(m.GetProperty("type").GetString()=="selfTestHls" && Environment.GetCommandLineArgs().Contains("--self-test-hls")) {
                    File.WriteAllText(Path.Combine(dataRoot,"self-test-hls.json"),m.GetRawText()); Close(); return;
                }
                if(m.GetProperty("type").GetString()=="cancelSave") { saving?.Cancel(); return; }
                if(m.GetProperty("type").GetString()=="save") await Save(m.GetProperty("id").GetString()!,m.GetProperty("token").GetString()!);
            } catch(Exception ex) { MessageBox.Show(this,ex.Message,Text); }
        };
        if(Environment.GetCommandLineArgs().Contains("--self-test") || Environment.GetCommandLineArgs().Contains("--self-test-hls")) {
            view.CoreWebView2.NavigationCompleted += async (_,e) => {
                try {
                    if(Environment.GetCommandLineArgs().Contains("--self-test-hls")) {
                        await view.CoreWebView2.ExecuteScriptAsync("""
                        (async()=>{try{
                            job=await api('/api/jobs',{url:'https://www.acgmhaa.com/gif/921679.html'});
                            for(let i=0;job.status==='running'&&i<90;i++){await new Promise(r=>setTimeout(r,1000));job=await api('/api/jobs/'+job.id)}
                            if(job.media.length!==1||job.media[0].format!=='hls')throw Error('HLS extraction failed');
                            render(true);const video=$('media').querySelector('video');video.muted=true;
                            const loaded=new Promise((resolve,reject)=>{video.addEventListener('loadeddata',resolve,{once:true});setTimeout(()=>reject(Error('playback timeout')),90000)});
                            video.play().catch(()=>{});await loaded;
                            window.chrome.webview.postMessage({type:'selfTestHls',ok:video.videoWidth>0,width:video.videoWidth,height:video.videoHeight,duration:video.duration});
                        }catch(e){window.chrome.webview.postMessage({type:'selfTestHls',ok:false,error:e.message})}})()
                        """);
                        return;
                    }
                    string result=await view.CoreWebView2.ExecuteScriptAsync("(()=>{const initial=document.title;job={status:'running',media:[{url:'data:image/svg+xml,<svg xmlns=\"http://www.w3.org/2000/svg\"/>',kind:'image',page:1}]};updateButton();const disabled=$('start').disabled;openPreview(job.media[0].url);const preview=$('preview').open;closePreview();job.status='complete';updateButton();return {title:initial,bridge:!!window.chrome.webview,disabled,preview,save:$('start').textContent==='保存',repository:document.querySelector('header a')?.href,origin:location.origin}})()");
                    File.WriteAllText(Path.Combine(dataRoot,"self-test.json"),JsonSerializer.Serialize(new {windowWidth=Width,windowHeight=Height,page=JsonSerializer.Deserialize<JsonElement>(result)}));
                } catch(Exception ex) {File.WriteAllText(Path.Combine(dataRoot,"self-test.json"),JsonSerializer.Serialize(new {error=ex.ToString()}));}
                Close();
            };
        }
        view.Source=new Uri(origin);
    }
    static void OpenExternal(string url) { if(Uri.TryCreate(url,UriKind.Absolute,out var uri) && (uri.Scheme=="https"||uri.Scheme=="http")) Process.Start(new ProcessStartInfo(url){UseShellExecute=true}); }
    void Notify(object message) { if(!IsDisposed && view.CoreWebView2!=null) view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(message)); }
    async Task Save(string id,string token)
    {
        if(saving!=null) {Notify(new {type="saveFinished",token,message="已有保存任务正在进行。"});return;}
        using var cts = new CancellationTokenSource(); saving=cts;
        try {
            using var dialog=new FolderBrowserDialog {Description="选择素材保存位置",UseDescriptionForTitle=true};
            if(dialog.ShowDialog(this)!=DialogResult.OK) {Notify(new {type="saveFinished",token,message="已取消保存。"});return;}
            var ct=cts.Token;
            using var response=await http.GetAsync(origin+"/api/jobs/"+Uri.EscapeDataString(id),ct);response.EnsureSuccessStatusCode();
            using var json=JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));var job=json.RootElement;
            if(job.GetProperty("status").GetString()!="complete") throw new Exception("请先完成提取");
            var media=job.GetProperty("media").EnumerateArray().Select(x=>x.Clone()).ToArray();
            string work=job.GetProperty("base").GetString()!.Split('/').Last();
            string folder=Path.Combine(dialog.SelectedPath,$"Acg-{work}-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}");Directory.CreateDirectory(folder);
            string manifest=Path.Combine(folder,"媒体清单.json");await File.WriteAllTextAsync(manifest,job.GetRawText(),ct);
            var errors=new System.Collections.Concurrent.ConcurrentBag<object>();int done=0,success=0;long downloaded=0;
            var watch=Stopwatch.StartNew();
            using var timer=new System.Windows.Forms.Timer {Interval=500};
            timer.Tick+=(_,_)=>Notify(new {type="saveProgress",token,message=$"正在保存：已处理 {done} / {media.Length}，已保存 {success}，失败 {errors.Count} · 已下载 {downloaded/1048576d:F1} MB · {downloaded/1048576d/Math.Max(1,watch.Elapsed.TotalSeconds):F2} MB/s"}); timer.Start();
            await Parallel.ForEachAsync(Enumerable.Range(0,media.Length),new ParallelOptions {MaxDegreeOfParallelism=3,CancellationToken=ct},async(i,cancel)=> {
                var item=media[i];string url=item.GetProperty("url").GetString()!;string prefix=(i+1).ToString("D5");string? partial=null;
                try {
                    if(item.GetProperty("kind").GetString()=="embed") {await File.WriteAllTextAsync(Path.Combine(folder,prefix+"-播放器链接.txt"),url,cancel);return;}
                    string ext=item.TryGetProperty("format",out var format) && format.GetString()=="hls" ? ".mp4" : Path.GetExtension(new Uri(url).AbsolutePath).ToLowerInvariant();if(!new[]{".webp",".avif",".png",".jpg",".jpeg",".gif",".bmp",".mp4",".webm",".mov",".m4v",".mkv"}.Contains(ext))ext=".bin";
                    string final=Path.Combine(folder,prefix+ext);partial=final+".part";
                    for(int attempt=0;;attempt++) {
                        try {
                            using var r=await http.GetAsync(origin+$"/api/media?id={Uri.EscapeDataString(id)}&index={i}",HttpCompletionOption.ResponseHeadersRead,cancel);r.EnsureSuccessStatusCode();
                            await using(var source=await r.Content.ReadAsStreamAsync(cancel))
                            await using(var file=new FileStream(partial,FileMode.Create,FileAccess.Write,FileShare.Read,65536,true)) {
                                byte[] chunk=new byte[65536];int n;
                                while((n=await source.ReadAsync(chunk,cancel))>0) {await file.WriteAsync(chunk.AsMemory(0,n),cancel);Interlocked.Add(ref downloaded,n);}
                            }
                            File.Move(partial,final);Interlocked.Increment(ref success);break;
                        } catch(Exception) when(!cancel.IsCancellationRequested && attempt==0) { if(File.Exists(partial))File.Delete(partial); }
                    }
                } catch(OperationCanceledException) {throw;}
                catch(Exception ex) {errors.Add(new {index=i+1,url,error=ex.Message});}
                finally {if(partial!=null && File.Exists(partial))File.Delete(partial);Interlocked.Increment(ref done);}
            });
            timer.Stop();
            await File.WriteAllTextAsync(manifest,JsonSerializer.Serialize(new {collection=job,saveErrors=errors},new JsonSerializerOptions {WriteIndented=true}),ct);
            Notify(new {type="saveFinished",token,message=$"已保存 {success} 个素材到 {folder}"+(errors.IsEmpty?"。":$"；{errors.Count} 项失败，详情见媒体清单。")});
        } catch(OperationCanceledException) {Notify(new {type="saveFinished",token,message="已终止保存。"});}
        catch(Exception ex) {Notify(new {type="saveFinished",token,message="保存失败："+ex.Message});}
        finally {saving=null;}
    }
}

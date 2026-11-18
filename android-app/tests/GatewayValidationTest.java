package com.acgreader.mobile;
import java.net.URL;
public class GatewayValidationTest {
 public static void main(String[] args)throws Exception{
 LocalGateway g=new LocalGateway(null);
 if(!g.allowed(new URL("https://www.acgmhaa.com/h/902864-2.html"),true))throw new AssertionError("page");
 if(!g.allowed(new URL("https://gif.acgnngca.com/a/master.m3u8"),false))throw new AssertionError("media");
 for(String s:new String[]{"https://127.0.0.1/x","https://example.com/x","https://file3.acgnngca.com.evil/x","http://gif.acgnngca.com/x"})if(g.allowed(new URL(s),false))throw new AssertionError("unsafe host");
 String html=g.text("https://www.acgmhaa.com/h/902864.html",true);
 if(!html.contains("manga-page"))throw new AssertionError("source request");
 String video=g.text("https://www.acgmhaa.com/gif/921679.html",true);
 if(!video.contains("acgPlayerConfig")||!video.contains("masterUrl"))throw new AssertionError("video source");
 g.cancelAll();System.out.println("Native gateway: host validation and direct image/video source requests passed");
 }
}

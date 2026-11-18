package com.acgreader.mobile;
import android.content.*;import android.graphics.BitmapFactory;import android.media.MediaScannerConnection;import android.net.Uri;import android.os.*;import android.provider.MediaStore;import java.io.*;import java.util.concurrent.*;
final class AlbumSaver {
 interface Callback {void complete(boolean ok,String message);}
 final Context context;final LocalGateway gateway;final ExecutorService executor=Executors.newSingleThreadExecutor();
 AlbumSaver(Context c,LocalGateway g){context=c.getApplicationContext();gateway=g;}
 void close(){executor.shutdownNow();}
 void save(String url,Callback callback){executor.execute(()->{File temporary=null,legacy=null;Uri pending=null;try{
 temporary=gateway.imageFile(url,true);
 BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeFile(temporary.getAbsolutePath(),options);
 if(options.outWidth<=0||options.outHeight<=0||options.outMimeType==null||!options.outMimeType.startsWith("image/"))throw new IOException("图片格式不受当前系统支持，未写入相册");
 ImageFormatInfo format=ImageFormatInfo.inspect(temporary);String mime=format.mime.isEmpty()?options.outMimeType:format.mime;final String savedMessage=format.frames>1?"已保存原始动图（"+format.frames+" 帧）；请在相册中打开播放":"已保存到相册 · Acg连页";String ext=mime.equals("image/jpeg")?"jpg":mime.equals("image/png")?"png":mime.equals("image/gif")?"gif":mime.equals("image/webp")?"webp":mime.equals("image/avif")?"avif":mime.equals("image/heif")?"heif":"img";
 String name="Acg-"+System.currentTimeMillis()+"."+ext;
 if(Build.VERSION.SDK_INT>=29){ContentValues v=new ContentValues();v.put(MediaStore.Images.Media.DISPLAY_NAME,name);v.put(MediaStore.Images.Media.MIME_TYPE,mime);v.put(MediaStore.Images.Media.RELATIVE_PATH,Environment.DIRECTORY_PICTURES+"/Acg连页");v.put(MediaStore.Images.Media.IS_PENDING,1);pending=context.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,v);if(pending==null)throw new IOException("无法创建相册图片");try(InputStream in=new FileInputStream(temporary);OutputStream out=context.getContentResolver().openOutputStream(pending,"w")){if(out==null)throw new IOException("无法写入相册");copy(in,out);}v.clear();v.put(MediaStore.Images.Media.IS_PENDING,0);if(context.getContentResolver().update(pending,v,null,null)<1)throw new IOException("相册更新失败");pending=null;callback.complete(true,savedMessage);
 }else{File folder=new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),"Acg连页");if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("无法创建相册目录");legacy=new File(folder,name);try(InputStream in=new FileInputStream(temporary);OutputStream out=new FileOutputStream(legacy)){copy(in,out);}String path=legacy.getAbsolutePath();MediaScannerConnection.scanFile(context,new String[]{path},new String[]{mime},(p,u)->callback.complete(u!=null,u!=null?savedMessage:"图片已写入，但相册索引失败，请在 Pictures/Acg连页 查看"));legacy=null;}
 }catch(Exception e){if(pending!=null)try{context.getContentResolver().delete(pending,null,null);}catch(Exception ignored){}if(legacy!=null)legacy.delete();callback.complete(false,e.getMessage()==null?"图片保存失败":e.getMessage());}finally{/* Original cache retains exact bytes for preview and future saves. */}});}
 static void copy(InputStream in,OutputStream out)throws IOException{byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1){if(Thread.currentThread().isInterrupted())throw new IOException("保存已中止");out.write(buffer,0,n);}out.flush();}
}

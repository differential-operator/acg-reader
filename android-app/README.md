# ACG Reader Android

安装包：`output/AcgReader-1.0.3.apk`，Android 8.0/API 26 及以上，通用架构。与旧版使用同一签名，可直接覆盖升级。

1.0.3 将应用名称、启动器名称及页面品牌统一为 ACG Reader。手机主标题中“一键提取！”固定显示在第二行，避免从中间断开。

1.0.2 新增图片预览工具栏右侧“保存”按钮：保存当前图片原文件到系统相册 Pictures/Acg连页，并显示保存结果。Android 10 及以上使用 MediaStore，无需读取相册权限；Android 8、9 首次保存会请求写入存储权限（仅声明到 API 28）。图片下载和写入在后台执行，失败时移除未完成文件或待发布相册记录，阻止重复点击。此功能已通过编译、签名与 JS 桥接测试，尚未真机验证相册交互。

1.0.1 修复旧版依赖 chatgpt.site 导致的 Cloudflare 拦截：界面和所有播放器脚本现已内置 APK，通过 WebView 的本地 HTTPS 资源映射加载；作品页面、播放列表和视频分段由 Android 原生网络层直接获取，不再请求该托管域名。不需要架设服务或运行电脑后台，提取素材仍需联网及较新的 Android System WebView。

本地网络层只接受指定作品站点和媒体域名，正常校验 TLS 证书；源站拒绝访问时显示错误，不尝试绕过验证。支持图片预览、HLS 视频、MP4 保存、原链接打开和清单导出。返回键优先关闭预览，保存期间退出会提示确认；请在前台完成保存，系统结束进程会中断任务。

保存通过系统 Storage Access Framework，只访问用户主动选择的文件夹，不申请整个存储空间权限。若系统不允许选择下载根目录，请创建或选择一个子文件夹。卸载应用不会删除已保存到所选文件夹的素材。

已完成 Java/DEX 编译、资源打包、APK v2/v3 签名验证、包名/系统版本/权限检查，以及保存桥接协议测试。当前没有 Android 手机或模拟器，尚未实测安装和系统文件夹选择器交互。

## 构建

需要 JDK 21、Python 3.14，以及 Android SDK Platform 35 和 Build Tools 35.0.0。将 SDK 文件解压到 `tools/platform/android-35` 和 `tools/build-tools/android-15`，运行 `build.ps1`。

签名密钥在本机 `.signing/release.p12`，密码通过 Windows DPAPI 加密存放在 `.signing/password.xml`，均已排除 Git。请保留这两个文件；后续覆盖升级必须使用同一密钥。迁移构建电脑前需要在原 Windows 账户下解密密码并安全迁移密钥；不要公开上传这些文件。

测试：`node tests/mobile.test.cjs`。

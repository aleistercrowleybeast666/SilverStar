package cn.silverstar.gshc;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.hardware.usb.*;
import android.net.Uri;
import android.os.*;
import android.provider.DocumentsContract;
import android.view.*;
import android.widget.*;
import androidx.core.content.FileProvider;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.hoho.android.usbserial.driver.*;
import cn.silverstar.gshc.core.*;
import cn.silverstar.gshc.core.tf.*;
import cn.silverstar.gshc.storage.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class MainActivity extends Activity {
    private static final int EXPORT=41,IMPORT=42,TF_DIRECTORY=43;
    private AppRuntime runtime;
    private LinearLayout shell,content;
    private TextView titleView,banner,stateText,telemetryText,diagnosticText,tfText;
    private boolean compactHeader,portDetails;
    private Button portDetailsButton;
    private LinearLayout connectionBar;
    private Button groundButton,debugButton;
    private final List<PlotView> charts=new ArrayList<>();
    private int page,columns=-1;
    private long recycleRequest,confirmationRequest;
    private String selectedId="",pendingAction="";
    private final Handler main=new Handler(Looper.getMainLooper());
    private final Runnable refresh=new Runnable(){@Override public void run(){renderValues();main.postDelayed(this,500);}};
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);runtime=((GshcApplication)getApplication()).runtime();
        if(runtime.tfDirectory.isEmpty())runtime.tfDirectory=SafDirectory.remembered(this);
        if(saved!=null){page=saved.getInt("page",0);selectedId=saved.getString("session","");pendingAction=saved.getString("action","");}
        shell=vertical();shell.setBackgroundColor(Color.rgb(237,243,245));setContentView(shell);
        ViewCompat.setOnApplyWindowInsetsListener(shell,(v,insets)->{androidx.core.graphics.Insets b=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout()|WindowInsetsCompat.Type.ime());v.setPadding(b.left,b.top,b.right,b.bottom);return insets;});
        titleView=label("SILVERSTAR   /   GSHC",20,true);shell.addView(titleView);banner=label("仿真 / 只读",13,false);shell.addView(banner);
        connectionBar=new LinearLayout(this);groundButton=button("地面站端口",()->connectionMenu(PortClaims.Role.GROUND));debugButton=button("飞控调试口",()->connectionMenu(PortClaims.Role.DEBUG));
        groundButton.setMaxLines(2);groundButton.setEllipsize(android.text.TextUtils.TruncateAt.END);debugButton.setMaxLines(2);debugButton.setEllipsize(android.text.TextUtils.TruncateAt.END);connectionBar.addView(groundButton);connectionBar.addView(debugButton);shell.addView(connectionBar);
        portDetailsButton=button("Port details",()->{portDetails=!portDetails;renderValues();});shell.addView(portDetailsButton);
        content=vertical();shell.addView(content,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout tabs=new LinearLayout(this);
        String[] titles={"预飞行","飞行","后期处理","调试与维护"};for(int i=0;i<titles.length;i++){final int index=i;Button button=button(titles[i],()->{page=index;showPage();});button.setMaxLines(2);button.setEllipsize(android.text.TextUtils.TruncateAt.END);button.setContentDescription(titles[i]);tabs.addView(button,new LinearLayout.LayoutParams(0,-2,1));}shell.addView(tabs);
        shell.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->{compactHeader=heightDp()<600||getResources().getConfiguration().fontScale>=1.5f;titleView.setVisibility(compactHeader?View.GONE:View.VISIBLE);int bannerLines=compactHeader?1:2;if(banner.getMaxLines()!=bannerLines)banner.setMaxLines(bannerLines);banner.setEllipsize(android.text.TextUtils.TruncateAt.END);portDetailsButton.setVisibility(compactHeader?View.VISIBLE:View.GONE);boolean wide=widthDp()>=600;int orient=wide?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL;if(connectionBar.getOrientation()!=orient||groundButton.getLayoutParams().width==-2){connectionBar.setOrientation(orient);groundButton.setLayoutParams(new LinearLayout.LayoutParams(wide?0:-1,-2,wide?1:0));debugButton.setLayoutParams(new LinearLayout.LayoutParams(wide?0:-1,-2,wide?1:0));}int next=LayoutPolicy.columns(widthDp());if(columns!=next){columns=next;showPage();}});
        showPage();
    }
    @Override protected void onResume(){super.onResume();main.post(refresh);}
    @Override protected void onPause(){main.removeCallbacks(refresh);super.onPause();}
    @Override protected void onStop(){if(!isChangingConfigurations())runtime.background();super.onStop();}
    @Override protected void onDestroy(){recycleRequest++;confirmationRequest++;super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle out){out.putInt("page",page);out.putString("session",selectedId);out.putString("action",pendingAction);super.onSaveInstanceState(out);}
    private void showPage(){
        if(content==null)return;recycleRequest++;content.removeAllViews();charts.clear();stateText=null;telemetryText=null;diagnosticText=null;tfText=null;
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);LinearLayout body=vertical();body.setPadding(dp(12),dp(8),dp(12),dp(24));scroll.addView(body);content.addView(scroll);
        if(page==0)preflight(body);else if(page==1)flight(body);else if(page==2)sessions(body);else maintenance(body);renderValues();
    }
    private void preflight(LinearLayout body){
        LinearLayout connection=card(body,"连接状态与仿真");connection.addView(label("端口在顶部统一管理。地面站：230400 · 8N1 · GSP-MIN / AIR M0\n本构建真实USB关闭；下列操作仅仿真。",14,false));
        connection.addView(button("开始仿真并记录",()->{if(runtime.mode.equals("usb-readonly")){message("请先停止USB记录");return;}runtime.simulate();}));
        connection.addView(button("停止记录 / 断开",()->{stopService(new Intent(this,UsbReadService.class));runtime.stop("用户停止");}));
        LinearLayout row=vertical();boolean split=LayoutPolicy.splitPreflight(widthDp(),heightDp());row.setOrientation(split?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL);body.addView(row);
        LinearLayout health=card(row,"准备与健康");if(split)health.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        stateText=label("等待飞控权威状态",15,false);health.addView(stateText);
        LinearLayout commands=card(row,"命令操作");if(split)commands.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        commands.addView(label("只读模式不自动应答Capability。未握手固件可能继续停留在Capability广播阶段。ACK不能证明READY。",14,false));
        Button unlock=button("解锁 / START · 当前不可用",()->{});unlock.setEnabled(false);commands.addView(unlock);
        commands.addView(button("查看危险操作保护条件",()->message("本版无设备命令发送接口。未来操作必须绑定当前连接/状态代次，检查协议、设备状态及新鲜度，再逐次人工确认。AIR M0保留的开伞命令不会生成按钮。")));
    }
    private void flight(LinearLayout body){
        LinearLayout summary=card(body,"飞行 · 任务状态与当前数据");telemetryText=label("等待遥测",14,false);summary.addView(telemetryText);
        body.addView(label("实时曲线 · 最近300样本 · 点击单图放大",14,true));
        int cols=LayoutPolicy.columns(widthDp());int[] order=LayoutPolicy.order(widthDp());
        for(int row=0;row<6/cols;row++){
            LinearLayout line=new LinearLayout(this);body.addView(line);
            for(int col=0;col<cols;col++){
                int channel=order[row*cols+col];PlotView chart=new PlotView(this,channel);charts.add(chart);
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(LayoutPolicy.chartHeight(getResources().getConfiguration().fontScale)),1);lp.setMargins(dp(3),dp(3),dp(3),dp(3));line.addView(chart,lp);
                chart.setOnClickListener(v->{PlotView large=new PlotView(this,channel);large.update(runtime.points());new AlertDialog.Builder(this).setView(large).setPositiveButton("关闭",null).create().show();large.getLayoutParams().height=dp(420);large.requestLayout();});
            }
        }
    }
    private void sessions(LinearLayout body){
        LinearLayout info=card(body,"后期处理 · 原始会话");
        info.addView(label("完整原始JSONL保存在应用内部。卸载/清除数据会丢失会话和回收站，请先导出。首版提供回放与文件管理；不移植桌面完整图像/GIF处理。",14,false));
        info.addView(button("导入原始 JSONL",()->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(i,IMPORT);}));
        info.addView(button("回收站 / 恢复",this::recycleList));
        runtime.files.execute(()->{try{List<String> ids=runtime.sessions.list(false);List<String[]> rows=new ArrayList<>();
            for(String id:ids){try{Properties p=runtime.sessions.metadata(id);rows.add(new String[]{id,p.getProperty("display_name",id),p.getProperty("mode","")+(runtime.sessions.isActive(id)?" · 正在记录":"")});}catch(IOException e){rows.add(new String[]{id,"无法读取会话",e.getMessage()});}}
            runOnUiThread(()->{
            if(isDestroyed()||page!=2)return;
            if(ids.isEmpty())body.addView(label("尚无会话。可从预飞行页开始仿真。",16,false));
            for(String[] row:rows)body.addView(button(row[1]+"\n"+row[2],()->sessionMenu(row[0],row[1])));
        });}catch(IOException e){uiError(e);}});
    }
    private void maintenance(LinearLayout body){
        LinearLayout row=vertical();boolean split=LayoutPolicy.splitPreflight(widthDp(),heightDp());row.setOrientation(split?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL);body.addView(row);
        LinearLayout status=card(row,"关键状态 · 只读");if(split)status.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));diagnosticText=label("等待协议数据",14,false);status.addView(diagnosticText);
        status.addView(button("查看已接收详细变量",()->{TelemetryState.Snapshot s=runtime.snapshot();StringBuilder values=new StringBuilder("只读协议字段；缺失不补默认值\n连接代次："+s.epoch()+"\n");for(String key:new TreeSet<>(s.fields().keySet()))values.append(key).append(" = ").append(s.fields().get(key)).append('\n');message(values.toString());}));
        LinearLayout tf=card(row,"设备 TF · LOGFILE v1");if(split)tf.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));tfText=label(runtime.tfStatus,14,false);tf.addView(tfText);
        tf.addView(label("跨连接续传不可用：设备/启动身份未知；中断后从0重新下载。设备删除无API。\n与第三页手机本地会话分开。真实文件服务仅使用顶部飞控调试口；旧固件无LOGFILE能力则不支持。closed不保证记录已成功完成。",14,false));
        tf.addView(button("选择 TF 保存目录",()->startActivityForResult(SafDirectory.picker(),TF_DIRECTORY)));
        tf.addView(label("目标目录："+(runtime.tfDirectory.isEmpty()?"尚未选择":runtime.tfDirectory)+"\n临时下载先保存在内部；目标复制回读校验成功后才标为完成。重名不覆盖，设备原件不删除。",13,false));
        tf.addView(button("查询能力与设备目录",()->tfList(false)));tf.addView(tfDownloadButton("下载已关闭文件并校验",false));
        tf.addView(button("模拟能力 / 目录",()->tfList(true)));tf.addView(tfDownloadButton("模拟自动下载 / 校验",true));
        Button delete=button("设备删除 · 本版禁用",()->{});delete.setEnabled(false);tf.addView(delete);
        tf.addView(button("查看设备删除确认条件",()->message("本版无设备DELETE API。未来必须选定文件、重新META、逐次明确确认，并由固件确认POSTFLIGHT、无打开writer、非当前任务。重连使选择和确认失效。下载成功不删除TF文件。")));
        tf.addView(label("AI接口仅内部数据边界；未启动HTTP/WebSocket监听，无任意内存读写。",13,false));
    }
    private void sessionMenu(String id,String name){
        selectedId=id;new AlertDialog.Builder(this).setTitle(name).setItems(new String[]{"查看元数据与原文","重命名","只读回放","导出到其他设备","系统分享ZIP（复制）","删除到回收站"},(dialog,index)->{
            if(index==0)viewSession(id);else if(index==1)rename(id,name);else if(index==2){runtime.replay(id);page=1;showPage();}
            else if(index==3)new AlertDialog.Builder(this).setTitle("导出到其他设备").setItems(new String[]{"复制导出","剪切导出（校验后确认）"},(d,n)->pickExport(id,n==1)).show();
            else if(index==4)share(id);else confirm("删除此会话？","移到应用内回收站，可恢复；卸载仍会删除。正在记录的会话不能删除。",()->runFile(()->runtime.sessions.recycle(id,true)));
        }).show();
    }
    private void viewSession(String id){runtime.files.execute(()->{try{
        Properties p=runtime.sessions.metadata(id);StringBuilder text=new StringBuilder();for(String k:new TreeSet<>(p.stringPropertyNames()))text.append(k).append(": ").append(p.getProperty(k)).append('\n');
        if("silverstar.gshc-jsonl".equals(p.getProperty("log_format","silverstar.gshc-jsonl"))){try(Reader r=Files.newBufferedReader(runtime.sessions.rawFile(id),StandardCharsets.UTF_8)){char[] b=new char[4096];int n=r.read(b);if(n>0)text.append("\n原文预览（最多4096字符）\n").append(b,0,n);}}
        else{try(InputStream in=Files.newInputStream(runtime.sessions.rawFile(id))){byte[] b=new byte[64];int n=in.read(b);text.append("\n原始字节前64B（未解码）\n");for(int i=0;i<n;i++)text.append(String.format(Locale.ROOT,"%02X ",b[i]&255));}}
        runOnUiThread(()->message(text.toString()));
    }catch(IOException e){uiError(e);}});}
    private void rename(String id,String name){EditText edit=new EditText(this);edit.setSingleLine(true);edit.setText(name);new AlertDialog.Builder(this).setTitle("重命名会话（不改原始日志）").setView(edit).setNegativeButton("取消",null).setPositiveButton("保存",(d,w)->runFile(()->runtime.sessions.rename(id,edit.getText().toString()))).show();}
    private void pickExport(String id,boolean cut){
        if(runtime.sessions.isActive(id)){message("请先停止记录，再导出一致快照");return;}selectedId=id;pendingAction=cut?"cut":"copy";
        Intent i=SafDirectory.picker();startActivityForResult(i,EXPORT);
    }
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;
        Uri uri=data.getData();if(code==TF_DIRECTORY){
            boolean persisted=SafDirectory.remember(this,uri,data.getFlags());runtime.tfDirectory=uri.toString();
            runtime.tfStatus=persisted?"Directory remembered with persisted permission":"Directory selected for this session only";showPage();return;
        }if(code==IMPORT){runtime.files.execute(()->{try(InputStream source=getContentResolver().openInputStream(uri)){
            if(source==null)throw new IOException("无法读取选择的文件");BufferedInputStream in=new BufferedInputStream(source);in.mark(65538);ByteArrayOutputStream head=new ByteArrayOutputStream();int next;
            while((next=in.read())!=-1&&next!='\n'){if(head.size()>=65536)throw new IOException("首行超过64KiB，拒绝导入");head.write(next);}in.reset();
            org.json.JSONObject first=new org.json.JSONObject(new String(head.toByteArray(),StandardCharsets.UTF_8));String version="legacy-unversioned";
            if(first.has("log_format")||first.has("log_format_version")){
                if(!"silverstar.gshc-jsonl".equals(first.optString("log_format"))||first.optInt("log_format_version",-1)!=1)throw new IOException("未支持的JSONL格式版本");version="1";
            }
            runtime.sessions.importRaw(in,"导入会话 "+System.currentTimeMillis(),version);runOnUiThread(this::showPage);
        }catch(Exception e){uiError(e);}});return;}
        if(code!=EXPORT||selectedId.isEmpty())return;String id=selectedId;boolean cut=pendingAction.equals("cut");pendingAction="";
        runtime.files.execute(()->{try{
            SafDirectory.Target destination=new SafDirectory(getApplicationContext(),uri).create("GSHC_"+id,".zip","application/zip");Uri zip=destination.uri;
            VerifiedExport.Receipt receipt=VerifiedExport.copy(runtime.sessions,id,destination,cut);runtime.receipt=receipt;
            runOnUiThread(()->{if(isDestroyed())return;if(cut)confirm("目标逐文件回读校验通过","目标："+zip+"\n确认剪切后，源会话移到本机回收站；首版保留可恢复副本，不自动清空。",()->runFile(()->VerifiedExport.confirmCut(runtime.sessions,receipt,true)));else message(receipt.verified?"复制完成；ZIP及逐文件SHA-256回读校验通过。源会话保留。":"目标回读未通过（不可读或内容不一致）。源会话保留；不能剪切，请重试或更换目标。");});
        }catch(Exception e){uiError(e);}});
    }
    private void share(String id){runtime.files.execute(()->{try{
        Path dir=getCacheDir().toPath().resolve("exports");Files.createDirectories(dir);Path file=dir.resolve("GSHC_"+UUID.randomUUID()+".zip");
        VerifiedExport.copy(runtime.sessions,id,new FileTarget(file),true);
        runOnUiThread(()->{if(isDestroyed())return;Uri uri=FileProvider.getUriForFile(this,getPackageName()+".exports",file.toFile());Intent i=new Intent(Intent.ACTION_SEND).setType("application/zip").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);i.setClipData(ClipData.newRawUri("GSHC ZIP",uri));startActivity(Intent.createChooser(i,"复制分享；不会删除源会话"));});
    }catch(Exception e){uiError(e);}});}
    private void recycleList(){
        final long request=++recycleRequest;
        runtime.files.execute(()->{try{
            List<String> ids=runtime.sessions.list(true);List<String> versions=new ArrayList<>();
            for(String id:ids)versions.add(runtime.sessions.recycledVersion(id));
            runOnUiThread(()->{
                if(isDestroyed()||isFinishing()||page!=2||request!=recycleRequest)return;
                if(ids.isEmpty()){message("回收站为空");return;}
                new AlertDialog.Builder(this).setTitle("选择会话恢复").setItems(ids.toArray(new String[0]),(d,n)->{
                    if(isDestroyed()||isFinishing()||page!=2||request!=recycleRequest)return;
                    recycleRequest++; // Consume exactly once; the store also validates the selected version.
                    runFile(()->runtime.sessions.restore(ids.get(n),versions.get(n)));
                }).show();
            });
        }catch(IOException e){uiError(e);}});
    }
    private TfLogClient.Source tfSource(boolean mock)throws IOException{
        if(mock)return new MockTfSource("SIMULATED TF TRANSFER FIXTURE; NOT A FLIGHT LOG\n".getBytes(StandardCharsets.UTF_8));
        if(!BuildConfig.ALLOW_USB||runtime.maintenance==null)throw new IOException("没有已授权的飞控调试口；本测试构建只支持模拟维护服务");return runtime.maintenance;
    }
    private void tfList(boolean mock){runtime.files.execute(()->{try{
        TfLogClient.Source source=tfSource(mock);TfLogClient.Capabilities caps=source.caps();TfLogClient.validateCapabilities(caps);
        StringBuilder out=new StringBuilder((mock?"模拟设备（非真实TF）":"设备TF")+"\nfile_service_version="+caps.fileServiceVersion()+"\nmax_chunk="+caps.maxChunk()+"\ndevice_id="+caps.deviceId()+"\nboot_id="+caps.bootId()+"\ndelete_supported="+caps.deleteSupported()+"（App删除禁用）\n跨连接续传=禁用：设备/启动身份未知；从0重新下载，旧副本保留。\n");
        Set<Long> cursors=new HashSet<>();long cursor=0;boolean end=false;
        for(int i=0;i<=1000;i++){if(!cursors.add(cursor))throw new IOException("目录游标重复");TfLogClient.ListPage result=source.list(cursor);if(result.end()){end=true;break;}out.append("文件 ").append(result.file().fileId()).append(" · ").append(result.file().size()).append(" B · closed=").append(result.file().closed()).append('\n');cursor=result.nextCursor();}
        if(!end)throw new IOException("目录超出客户端边界");runtime.tfStatus=out.toString();runOnUiThread(this::renderValues);
    }catch(Exception e){runtime.tfStatus="能力/目录不可用："+e.getMessage();runOnUiThread(this::renderValues);}});}
    private Button tfDownloadButton(String text,boolean mock){Button b=button(text,()->tfDownload(mock));b.setEnabled(!runtime.tfDirectory.isEmpty());return b;}
    private void tfDownload(boolean mock){if(runtime.tfDirectory.isEmpty()){startActivityForResult(SafDirectory.picker(),TF_DIRECTORY);return;}String targetDirectory=runtime.tfDirectory;runtime.files.execute(()->{try{
        SafDirectory target=new SafDirectory(getApplicationContext(),Uri.parse(targetDirectory));target.validate();
        TfLogClient.Source source=tfSource(mock);runtime.tfStatus=mock?"模拟下载校验中":"设备下载校验中";
        Path destination=getFilesDir().toPath().resolve(mock?"tf-mock":"tf-downloads");List<TfLogClient.Result> results=new TfLogClient().downloadAll(source,destination);
        for(TfLogClient.Result result:results){
            runtime.sessions.importFlightLog(result.localFile(),mock);
            SafDirectory.Target output=target.create(mock?"TF_mock_fixture":"TF_flight",mock?".bin":".sslog","application/octet-stream");
            VerifiedFileCopy.Result copied=VerifiedFileCopy.copy(result.localFile(),output);
            if(!copied.sha256().equals(result.localSha256()))throw new IOException("Source changed since protocol verification; internal copy retained");
            Path metadata=result.localFile().resolveSibling(result.localFile().getFileName().toString().replaceFirst("\\.sslog$",".metadata"));
            if(Files.isRegularFile(metadata))VerifiedFileCopy.copy(metadata,target.create("TF_transfer_metadata",".metadata","application/octet-stream"));
        }
        runtime.tfStatus="Target readback verified: "+targetDirectory+"\n"+(mock?"模拟样例":"设备TF")+"已保存 "+results.size()+" 文件；CRC32/长度验证、本地SHA256完成；未删卡。可到第三页管理/导出本地副本。";
        if(mock)runtime.tfStatus+=" 样例不是有效飞行日志。";runOnUiThread(this::renderValues);
    }catch(Exception e){runtime.tfStatus="下载/目标复制未完成，内部副本保留；请重新选择目标目录后重试。目标可能有未完成文件："+e.getMessage();runOnUiThread(this::renderValues);}});}
    private void connectionMenu(PortClaims.Role role){
        new AlertDialog.Builder(this).setTitle(role==PortClaims.Role.GROUND?"地面站端口 · 遥测/任务链路":"飞控调试口 · 维护文件服务").setItems(new String[]{"选择设备 / 端口并连接","断开此链路"},(d,n)->{
            if(n==0)devices(role);else ((GshcApplication)getApplication()).usb().disconnect(role);
        }).show();
    }
    private void devices(PortClaims.Role role){
        UsbManager manager=(UsbManager)getSystemService(USB_SERVICE);List<UsbSerialDriver> drivers=UsbSerialProber.getDefaultProber().findAllDrivers(manager);
        List<String> names=new ArrayList<>();List<UsbSerialDriver> choices=new ArrayList<>();List<Integer> ports=new ArrayList<>();
        for(UsbSerialDriver driver:drivers)for(int i=0;i<driver.getPorts().size();i++){UsbDevice d=driver.getDevice();names.add(String.format(Locale.ROOT,"%04X:%04X · %s · 端口%d",d.getVendorId(),d.getProductId(),driver.getClass().getSimpleName()+" "+d.getDeviceName(),i));choices.add(driver);ports.add(i);}
        if(names.isEmpty()){message("发现USB设备 "+manager.getDeviceList().size()+" 个，但没有可用串口驱动。需核对手机Host/OTG、供电、线缆和实际芯片。不会强制映射未知VID/PID。");return;}
        new AlertDialog.Builder(this).setTitle("选择设备 / 端口 · 230400").setItems(names.toArray(new String[0]),(d,n)->{
            if(runtime.ports.get(role)!=null){message("请先断开此链路，再更换设备/端口");return;}
            if(role==PortClaims.Role.GROUND)runtime.groundSelection=names.get(n);else runtime.debugSelection=names.get(n);renderValues();
            if(!BuildConfig.ALLOW_USB){message("本测试构建未启用真实USB。未申请设备权限、未打开端口、未发送命令。后续须授权设备测试并重新构建。");return;}
            if(role==PortClaims.Role.GROUND)confirm("连接地面站口，仅接收？","打开端口设置230400/8N1；不发送GSHC命令。",()->requestUsb(choices.get(n).getDevice(),ports.get(n),role,230400));
            else new AlertDialog.Builder(this).setTitle("飞控调试口波特率（需匹配实际配置）").setItems(new String[]{"230400 / 8N1","115200 / 8N1"},(dialog,b)->confirm("连接飞控调试口？","只在第四页明确操作时发送LOGFILE查询/读取；不路由到地面站口，不发送DELETE。",()->requestUsb(choices.get(n).getDevice(),ports.get(n),role,b==0?230400:115200))).show();
        }).show();
    }
    private void requestUsb(UsbDevice device,int port,PortClaims.Role role,int baud){
        if(!BuildConfig.ALLOW_USB)return;
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},77);
        try{((GshcApplication)getApplication()).usb().request(device,port,role,baud);}catch(Exception e){message("USB request failed: "+e.getMessage());}
    }
    private void renderValues(){
        if(banner==null)return;portDetailsButton.setText(portDetails?"收起端口详情":"展开端口详情");TelemetryState.Snapshot s=runtime.snapshot();banner.setText(runtime.mode+" · "+runtime.status+(runtime.error.isEmpty()?"":"\n故障："+runtime.error));
        groundButton.setText("地面站端口 · "+runtime.groundStatus+(compactHeader&&!portDetails?"":"\n"+runtime.groundSelection));
        debugButton.setText("飞控调试口 · "+runtime.debugStatus+(compactHeader&&!portDetails?"":"\n"+runtime.debugSelection));
        if(diagnosticText!=null)diagnosticText.setText("数据来源："+runtime.mode+"\n连接代次："+s.epoch()+"\nAIR profile已识别："+s.profileSupported()+"\n权威状态新鲜："+s.fresh()+"\nREADY："+s.ready()+"\n最后消息："+value(s,"last_kind")+"\n最近故障："+(runtime.error.isEmpty()?"无已记录故障":runtime.error));
        if(tfText!=null)tfText.setText(runtime.tfStatus);
        if(stateText!=null)stateText.setText("协议支持："+s.profileSupported()+"\n权威飞前状态新鲜："+s.fresh()+"\nREADY："+s.ready()+"   解锁："+s.startUnlocked()+"\n生命周期："+s.lifecycle()+"\n校准："+value(s,"calibration_state")+"  对准："+value(s,"alignment_state")+"\nGNSS："+value(s,"gnss_position_usable")+"\n阻止原因："+value(s,"start_block_reason"));
        if(telemetryText!=null)telemetryText.setText("当前消息："+value(s,"last_kind")+"\n机载时间 ms："+value(s,"time_ms")+"\n速度 ENU m/s："+value(s,"vel_mps")+"\n位置 ENU m："+value(s,"pos_m")+"\n四元数 WXYZ："+value(s,"quat")+"\n加速度 m/s²："+value(s,"accel_mps2")+"\n角速率 rad/s："+value(s,"gyro_radps")+"\nRSSI："+value(s,"rssi_dbm")+"  SNR："+value(s,"snr_db"));
        List<double[]> points=runtime.points();for(PlotView chart:charts)chart.update(points);
    }
    private String value(TelemetryState.Snapshot s,String key){Object v=s.fields().get(key);return v==null?"—":v.toString();}
    private float widthDp(){return Math.max(0,shell.getWidth()-shell.getPaddingLeft()-shell.getPaddingRight())/getResources().getDisplayMetrics().density;}
    private float heightDp(){return shell.getHeight()/getResources().getDisplayMetrics().density;}
    private int dp(float n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private LinearLayout vertical(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
    private LinearLayout card(LinearLayout parent,String title){LinearLayout c=vertical();c.setPadding(dp(12),dp(12),dp(12),dp(12));c.setBackgroundColor(Color.WHITE);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,dp(5),0,dp(8));parent.addView(c,lp);c.addView(label(title,18,true));return c;}
    private TextView label(String text,int sp,boolean bold){TextView t=new TextView(this);t.setText(text);t.setTextSize(sp);t.setTextColor(Color.rgb(30,49,61));t.setPadding(dp(6),dp(5),dp(6),dp(5));if(bold)t.setTypeface(null,android.graphics.Typeface.BOLD);return t;}
    private Button button(String text,Runnable action){Button b=new Button(this);b.setText(text);b.setTextSize(14);b.setAllCaps(false);b.setMinHeight(dp(56));b.setPadding(dp(8),dp(8),dp(8),dp(8));b.setOnClickListener(v->action.run());return b;}
    private void confirm(String title,String text,Runnable action){if(isDestroyed()||isFinishing())return;final long request=++confirmationRequest;new AlertDialog.Builder(this).setTitle(title).setMessage(text).setNegativeButton("取消",null).setPositiveButton("明确确认",(d,w)->{if(isDestroyed()||isFinishing()||request!=confirmationRequest)return;confirmationRequest++;action.run();}).show();}
    private void message(String text){if(isDestroyed()||isFinishing())return;ScrollView scroll=new ScrollView(this);scroll.addView(label(text,15,false));new AlertDialog.Builder(this).setTitle("SilverStar GSHC").setView(scroll).setPositiveButton("知道了",null).show();}
    private void runFile(Io work){runtime.files.execute(()->{try{work.run();runOnUiThread(()->{if(!isDestroyed())showPage();});}catch(Exception e){uiError(e);}});}
    private void uiError(Exception e){runOnUiThread(()->message("操作未完成，源会话保留。\n"+e.getMessage()));}
    private interface Io{void run()throws Exception;}
    private static final class FileTarget implements VerifiedExport.Target{
        final Path file;FileTarget(Path p){file=p;}
        public OutputStream openWrite()throws IOException{return Files.newOutputStream(file);}
        public InputStream openRead()throws IOException{return Files.newInputStream(file);}
        public String description(){return file.toString();}
    }
}

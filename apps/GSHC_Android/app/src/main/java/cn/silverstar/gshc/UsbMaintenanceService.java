package cn.silverstar.gshc;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.hardware.usb.*;
import android.os.*;
import com.hoho.android.usbserial.driver.*;
import cn.silverstar.gshc.core.tf.MaintenanceTfSource;
import cn.silverstar.gshc.storage.PortClaims;
import cn.silverstar.gshc.storage.CloseScope;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** Explicit debug-port binding. Build gate is OFF; never routes LOGFILE onto ground telemetry. */
public final class UsbMaintenanceService extends Service {
    private final ExecutorService setup=Executors.newSingleThreadExecutor();
    private volatile boolean closing;
    private volatile UsbSerialPort serial;
    private final CloseScope resources=new CloseScope();
    private final Object publishLock=new Object();
    private PortClaims.Lease lease;
    private AppRuntime runtime;
    private MaintenanceTfSource source;
    private String deviceName;
    private final Object exchangeLock=new Object();
    @Override public void onCreate(){super.onCreate();runtime=((GshcApplication)getApplication()).runtime();}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null||!BuildConfig.ALLOW_USB||"STOP".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
        if(lease!=null)return START_NOT_STICKY;
        try{
            PortClaims.Lease candidate=runtime.ports.get(PortClaims.Role.DEBUG);
            if(candidate==null||candidate.epoch()!=intent.getLongExtra("lease_epoch",-1))throw new IOException("Expired debug connection request");lease=candidate;
            UsbManager manager=(UsbManager)getSystemService(USB_SERVICE);deviceName=intent.getStringExtra("device_name");int index=intent.getIntExtra(UsbReadService.PORT,-1);UsbSerialDriver selected=null;
            for(UsbSerialDriver d:UsbSerialProber.getDefaultProber().findAllDrivers(manager))if(d.getDevice().getDeviceName().equals(deviceName)&&d.getDevice().getDeviceId()==intent.getIntExtra(UsbReadService.DEVICE,-1))selected=d;
            if(selected==null||!manager.hasPermission(selected.getDevice())||index<0||index>=selected.getPorts().size())throw new IOException("调试设备身份/权限/端口已变化");
            if(!lease.key().equals(UsbConnections.key(selected.getDevice(),index)))throw new IOException("Debug device identity changed");
            getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel("debug-usb","飞控调试口",NotificationManager.IMPORTANCE_LOW));
            PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,UsbMaintenanceService.class).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
            Notification notice=new Notification.Builder(this,"debug-usb").setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("GSHC 飞控调试口已连接").setContentText("仅显式LOGFILE操作；可停止断开").setOngoing(true).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build();
            if(Build.VERSION.SDK_INT>=29)startForeground(13,notice,ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);else startForeground(13,notice);
            UsbSerialDriver driver=selected;int baud=intent.getIntExtra("baud",230400);if(baud!=115200&&baud!=230400)throw new IOException("未支持的维护口波特率");
            runtime.debugStatus="正在打开";
            setup.execute(()->{try{
                ensureCurrent();UsbDeviceConnection connection=manager.openDevice(driver.getDevice());if(connection==null)throw new IOException("Unable to open debug port");
                resources.own(connection::close);ensureCurrent();UsbSerialPort opened=driver.getPorts().get(index);opened.open(connection);resources.own(opened::close);
                ensureCurrent();opened.setParameters(baud,8,UsbSerialPort.STOPBITS_1,UsbSerialPort.PARITY_NONE);
                synchronized(publishLock){ensureCurrent();serial=opened;source=new MaintenanceTfSource(this::exchange);runtime.maintenance=source;runtime.debugStatus="Connected / "+baud+" 8N1 / CAPS not requested";}

            }catch(Exception e){runtime.debugStatus="失败："+e.getMessage();stopSelf();}finally{if(closing)closePort();}});
        }catch(Exception e){runtime.debugStatus="失败："+e.getMessage();stopSelf();}
        return START_NOT_STICKY;
    }
    private String exchange(String request,long timeoutMs)throws IOException{
        synchronized(exchangeLock){
            if(!BuildConfig.ALLOW_USB||closing||!runtime.ports.current(lease)||serial==null)throw new IOException("调试口已断开，必须重新选择和协商");
            if(!request.matches("LOGFILE (CAPS|LIST [0-9]+|META [0-9]+|READ [0-9]+ 1-[0-9A-F]{8}-[0-9A-F]{8} [0-9]+|POLL [0-9]+|CANCEL)\\r\\n"))throw new IOException("此适配器只允许共享LOGFILE只读/取消请求");
            byte[] bytes=request.getBytes(StandardCharsets.US_ASCII);if(bytes.length>191)throw new IOException("请求过长");
            long deadline=SystemClock.elapsedRealtime()+Math.max(1,Math.min(timeoutMs,30000));serial.write(bytes,(int)Math.min(1000,timeoutMs));
            ByteArrayOutputStream line=new ByteArrayOutputStream();byte[] block=new byte[512];int skipped=0;
            while(!closing&&SystemClock.elapsedRealtime()<deadline){
                int n=serial.read(block,(int)Math.max(1,Math.min(250,deadline-SystemClock.elapsedRealtime())));
                for(int i=0;i<n;i++){
                    int value=block[i]&255;if(value>127)throw new IOException("维护响应非ASCII");line.write(value);if(line.size()>511)throw new IOException("维护响应超出511字节");
                    if(value=='\n'){
                        String response=new String(line.toByteArray(),StandardCharsets.US_ASCII);line.reset();
                        if(response.startsWith("OK LOGFILE ")||response.startsWith("PENDING LOGFILE ")||response.startsWith("ERR LOGFILE "))return response;
                        if(response.startsWith("ERR "))throw new IOException("固件不支持LOGFILE或拒绝请求："+response.trim());
                        if(++skipped>32)throw new IOException("维护通道噪声/其他输出过多");
                    }
                }
            }
            throw new IOException("维护请求超时/断开；需要重新CAPS和META");
        }
    }
    private void ensureCurrent()throws IOException{if(closing||!runtime.ports.current(lease))throw new IOException("Debug connection cancelled");}
    private void closePort(){try{resources.close();}catch(IOException e){if(runtime.ports.current(lease))runtime.debugStatus="Close failed: "+e.getMessage();}}
    private void closeAndRelease(){
        closePort();
        // The setup worker has exited opening; also wait for the old exchange to leave its I/O lock.
        synchronized(exchangeLock){
            if(lease!=null&&lease.equals(runtime.ports.get(PortClaims.Role.DEBUG))){runtime.debugStatus="Disconnected / selection invalidated";runtime.ports.release(lease);}
        }
    }
    @Override public void onDestroy(){
        synchronized(publishLock){closing=true;if(runtime.maintenance==source)runtime.maintenance=null;}
        runtime.ports.invalidate(lease);MaintenanceTfSource previous=source;if(previous!=null)runtime.files.execute(previous::transportReset);
        setup.execute(this::closeAndRelease);setup.shutdown();
        stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}

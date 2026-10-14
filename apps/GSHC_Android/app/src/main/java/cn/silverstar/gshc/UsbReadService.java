package cn.silverstar.gshc;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.hardware.usb.*;
import android.os.*;
import com.hoho.android.usbserial.driver.*;
import java.io.IOException;
import java.util.concurrent.*;
import cn.silverstar.gshc.storage.*;

/** Ground-link RX only. Every asynchronous completion is tied to the selected lease. */
public final class UsbReadService extends Service {
    public static final String DEVICE="device",PORT="port",ACTION_STOP="cn.silverstar.gshc.USB_STOP";
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final CloseScope resources=new CloseScope();
    private volatile boolean closing;
    private AppRuntime runtime;
    private PortClaims.Lease lease;
    @Override public void onCreate(){super.onCreate();runtime=((GshcApplication)getApplication()).runtime();}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null||ACTION_STOP.equals(intent.getAction())||!BuildConfig.ALLOW_USB){stopSelf();return START_NOT_STICKY;}
        if(lease!=null)return START_NOT_STICKY;
        try{
            UsbManager manager=(UsbManager)getSystemService(USB_SERVICE);UsbSerialDriver selected=null;
            int portIndex=intent.getIntExtra(PORT,-1);
            PortClaims.Lease candidate=runtime.ports.get(PortClaims.Role.GROUND);
            if(candidate==null||candidate.epoch()!=intent.getLongExtra("lease_epoch",-1))throw new IOException("过期的连接请求");
            lease=candidate;
            for(UsbSerialDriver driver:UsbSerialProber.getDefaultProber().findAllDrivers(manager)){
                UsbDevice d=driver.getDevice();
                if(d.getDeviceId()==intent.getIntExtra(DEVICE,-1)&&d.getDeviceName().equals(intent.getStringExtra("device_name")))selected=driver;
            }
            if(selected==null||!manager.hasPermission(selected.getDevice())||portIndex<0||portIndex>=selected.getPorts().size()||!lease.key().equals(UsbConnections.key(selected.getDevice(),portIndex)))throw new IOException("设备/端口身份或权限已变化");
            getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel("usb","USB只读记录",NotificationManager.IMPORTANCE_LOW));
            PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,UsbReadService.class).setAction(ACTION_STOP),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
            Notification notice=new Notification.Builder(this,"usb").setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("GSHC 地面站只读记录").setContentText("230400 / 8N1；停止可结束记录").setOngoing(true).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build();
            if(Build.VERSION.SDK_INT>=29)startForeground(12,notice,ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);else startForeground(12,notice);
            UsbSerialDriver driver=selected;io.execute(()->readLoop(manager,driver,portIndex));
        }catch(Exception e){runtime.error=e.toString();stopSelf();}
        return START_NOT_STICKY;
    }
    private void readLoop(UsbManager manager,UsbSerialDriver driver,int portIndex){
        try{
            ensureCurrent();UsbDeviceConnection connection=manager.openDevice(driver.getDevice());if(connection==null)throw new IOException("USB openDevice失败");
            resources.own(connection::close);ensureCurrent();
            UsbSerialPort serial=driver.getPorts().get(portIndex);serial.open(connection);
            resources.own(serial::close);ensureCurrent();serial.setParameters(230400,8,UsbSerialPort.STOPBITS_1,UsbSerialPort.PARITY_NONE);
            ensureCurrent();runtime.beginUsb(driver.getClass().getSimpleName(),lease).get();ensureCurrent();
            runtime.groundStatus="已连接 · 230400 8N1";long epoch=runtime.transportEpoch;byte[] buffer=new byte[4096];
            while(!closing&&runtime.recording&&epoch==runtime.transportEpoch&&runtime.ports.current(lease)){
                int n=serial.read(buffer,250);if(n>0)runtime.receiveUsb(java.util.Arrays.copyOf(buffer,n),epoch);
            }
        }catch(Exception e){if(!closing&&runtime.ports.current(lease))runtime.error="USB停止："+e.getMessage();}
        finally{closePort();runtime.stopUsb(lease,"USB断开/停止；重连需要重新选择");stopSelf();}
    }
    private void ensureCurrent()throws IOException{if(closing||!runtime.ports.current(lease))throw new IOException("USB连接已取消");}
    private void closePort(){try{resources.close();}catch(IOException e){runtime.error="USB关闭失败："+e.getMessage();}}
    private void closeAndRelease(){
        closePort();
        if(lease!=null&&lease.equals(runtime.ports.get(PortClaims.Role.GROUND))){runtime.groundStatus="未连接";runtime.ports.release(lease);}
    }
    @Override public void onDestroy(){
        closing=true;runtime.ports.invalidate(lease);runtime.stopUsb(lease,"USB服务停止");
        // Same-worker ordering waits for pending open/read and resource close, without blocking UI.
        // Release only after onDestroy begins; a stopping service must not accept a replacement lease.
        io.execute(this::closeAndRelease);io.shutdown();
        stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}

package cn.silverstar.gshc;

import android.app.PendingIntent;
import android.content.*;
import android.hardware.usb.*;
import android.net.Uri;
import android.os.Build;
import cn.silverstar.gshc.storage.*;
import java.io.IOException;

/** One process-lifetime receiver; pending permission identity survives Activity recreation. */
final class UsbConnections {
    private static final String ACTION="cn.silverstar.gshc.USB_PERMISSION";
    private final Context context;
    private final AppRuntime runtime;
    private final UsbPermissions permissions;
    UsbConnections(Context application,AppRuntime runtime){
        this.context=application;this.runtime=runtime;permissions=new UsbPermissions(runtime.ports);
        IntentFilter filter=new IntentFilter(ACTION);filter.addDataScheme("gshc-usb");
        IntentFilter detach=new IntentFilter(UsbManager.ACTION_USB_DEVICE_DETACHED);
        BroadcastReceiver receiver=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent intent){receive(intent);}};
        androidx.core.content.ContextCompat.registerReceiver(context,receiver,filter,androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED);
        androidx.core.content.ContextCompat.registerReceiver(context,receiver,detach,androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED);
    }
    void request(UsbDevice device,int port,PortClaims.Role role,int baud)throws IOException{
        if(!BuildConfig.ALLOW_USB)throw new IOException("真实 USB gate 关闭");
        UsbPermissions.Request request=permissions.request(role,key(device,port),device.getDeviceId(),baud);
        status(role,"等待 USB 权限");
        Intent reply=new Intent(ACTION).setPackage(context.getPackageName()).setData(Uri.parse("gshc-usb://permission/"+request.lease().epoch()));
        PendingIntent intent=PendingIntent.getBroadcast(context,(int)request.lease().epoch(),reply,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        try{manager().requestPermission(device,intent);}catch(RuntimeException e){permissions.cancel(role);status(role,"权限申请失败："+e.getMessage());throw e;}
    }
    void disconnect(PortClaims.Role role){
        permissions.cancel(role);runtime.ports.invalidate(role);context.stopService(new Intent(context,owner(role)));
        status(role,runtime.ports.get(role)==null?"未连接":"正在关闭");
    }
    private void receive(Intent intent){
        UsbDevice device=intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
        if(UsbManager.ACTION_USB_DEVICE_DETACHED.equals(intent.getAction())){
            if(device==null)return;
            for(PortClaims.Role role:PortClaims.Role.values()){
                PortClaims.Lease lease=runtime.ports.get(role);
                if(lease!=null&&lease.key().deviceName().equals(device.getDeviceName())){disconnect(role);status(role,"Detached / reselect required");}
            }
            permissions.detached(device.getDeviceName());return;
        }
        if(!ACTION.equals(intent.getAction())||!BuildConfig.ALLOW_USB||intent.getData()==null)return;
        long epoch;try{epoch=Long.parseLong(intent.getData().getLastPathSegment());}catch(NumberFormatException e){return;}
        UsbPermissions.Request pending=permissions.pending(epoch);if(pending==null)return;
        PortClaims.Role role=pending.lease().role();
        UsbPermissions.Request allowed=permissions.complete(epoch,device==null?null:key(device,pending.lease().key().port()),device==null?-1:device.getDeviceId(),device!=null&&intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED,false)&&manager().hasPermission(device));
        if(allowed==null){status(role,"权限未批准或设备身份已变化");return;}
        try{
            status(role,"正在打开");
            context.startForegroundService(new Intent(context,owner(role)).putExtra(UsbReadService.DEVICE,device.getDeviceId()).putExtra(UsbReadService.PORT,allowed.lease().key().port()).putExtra("device_name",device.getDeviceName()).putExtra("lease_epoch",epoch).putExtra("baud",allowed.baud()));
        }catch(RuntimeException e){runtime.ports.release(allowed.lease());status(role,"前台服务未启动："+e.getMessage());}
    }
    private UsbManager manager(){return (UsbManager)context.getSystemService(Context.USB_SERVICE);}
    private static Class<?> owner(PortClaims.Role role){return role==PortClaims.Role.GROUND?UsbReadService.class:UsbMaintenanceService.class;}
    static PortClaims.Key key(UsbDevice device,int port){return new PortClaims.Key(device.getDeviceName(),device.getVendorId(),device.getProductId(),port);}
    private void status(PortClaims.Role role,String value){if(role==PortClaims.Role.GROUND)runtime.groundStatus=value;else runtime.debugStatus=value;}
}

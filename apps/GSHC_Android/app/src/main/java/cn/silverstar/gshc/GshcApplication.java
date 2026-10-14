package cn.silverstar.gshc;
import android.app.Application;
import java.io.IOException;
public final class GshcApplication extends Application {
    private AppRuntime runtime;
    private UsbConnections usb;
    @Override public void onCreate(){super.onCreate();try{runtime=new AppRuntime(this);}catch(IOException ex){throw new IllegalStateException("无法打开应用会话存储",ex);}}
    public AppRuntime runtime(){return runtime;}
    public synchronized UsbConnections usb(){if(usb==null)usb=new UsbConnections(this,runtime);return usb;}
}

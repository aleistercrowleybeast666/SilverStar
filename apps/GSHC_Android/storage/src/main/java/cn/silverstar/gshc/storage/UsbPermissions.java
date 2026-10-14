package cn.silverstar.gshc.storage;

import java.io.IOException;
import java.util.*;

/** Application-owned permission correlation, independent of any Activity instance. */
public final class UsbPermissions {
    public record Request(PortClaims.Lease lease,int deviceId,int baud) {}
    private final PortClaims ports;
    private final Map<Long,Request> pending=new HashMap<>();
    public UsbPermissions(PortClaims ports){this.ports=ports;}
    public synchronized Request request(PortClaims.Role role,PortClaims.Key key,int deviceId,int baud)throws IOException{
        if(baud!=230400&&(role!=PortClaims.Role.DEBUG||baud!=115200))throw new IOException("Unsupported role/baud");
        PortClaims.Lease lease=ports.claim(role,key);Request request=new Request(lease,deviceId,baud);pending.put(lease.epoch(),request);return request;
    }
    /** A denial or identity mismatch invalidates only the exact requested lease. */
    public synchronized Request complete(long epoch,PortClaims.Key actual,int deviceId,boolean granted){
        Request request=pending.remove(epoch);if(request==null)return null;
        if(!granted||!ports.current(request.lease())||!request.lease().key().equals(actual)||request.deviceId()!=deviceId){ports.release(request.lease());return null;}
        return request;
    }
    public synchronized Request pending(long epoch){return pending.get(epoch);}
    public synchronized boolean cancel(PortClaims.Role role){
        Iterator<Request> it=pending.values().iterator();boolean changed=false;
        while(it.hasNext()){Request request=it.next();if(request.lease().role()==role){it.remove();ports.release(request.lease());changed=true;}}
        return changed;
    }
    public synchronized void detached(String deviceName){
        pending.values().removeIf(request->{if(!request.lease().key().deviceName().equals(deviceName))return false;ports.release(request.lease());return true;});
        ports.detached(deviceName); // Open service owners retain reservation until their own I/O/close exits.
    }
}

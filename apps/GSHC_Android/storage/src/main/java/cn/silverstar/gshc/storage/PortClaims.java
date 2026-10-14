package cn.silverstar.gshc.storage;

import java.io.IOException;
import java.util.*;

/** Application-owned logical USB ownership. A reconnect creates a new lease, never inherits one. */
public final class PortClaims {
    public enum Role { GROUND, DEBUG }
    public record Key(String deviceName,int vendorId,int productId,int port) {
        public Key {if(deviceName==null||deviceName.isEmpty()||port<0)throw new IllegalArgumentException("Invalid USB identity");}
    }
    public record Lease(Role role,Key key,long epoch) {}
    private final EnumMap<Role,Lease> claims=new EnumMap<>(Role.class);
    private final Set<Long> cancelled=new HashSet<>();
    private long generation;
    public synchronized Lease claim(Role role,Key key)throws IOException{
        if(claims.containsKey(role))throw new IOException("此链路已经连接；请先断开");
        for(Lease existing:claims.values())if(existing.key().equals(key))throw new IOException("同一物理设备端口不能由两路重复占用");
        Lease lease=new Lease(role,key,++generation);claims.put(role,lease);return lease;
    }
    public synchronized void release(Lease lease){if(lease!=null){cancelled.remove(lease.epoch());if(lease.equals(claims.get(lease.role())))claims.remove(lease.role());}}
    public synchronized boolean current(Lease lease){return lease!=null&&!cancelled.contains(lease.epoch())&&lease.equals(claims.get(lease.role()));}
    /** Stop using immediately, but reserve the physical port until its service finishes closing. */
    public synchronized void invalidate(Role role){invalidate(claims.get(role));}
    public synchronized void invalidate(Lease lease){if(lease!=null&&lease.equals(claims.get(lease.role())))cancelled.add(lease.epoch());}
    public synchronized Lease get(Role role){return claims.get(role);}
    public synchronized void detached(String deviceName){for(Lease lease:claims.values())if(lease.key().deviceName().equals(deviceName))cancelled.add(lease.epoch());generation++;}
}

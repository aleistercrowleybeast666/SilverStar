package cn.silverstar.gshc.core;

import java.util.*;

/** Single worker owner. Snapshots are immutable and safe for UI publication. */
public final class TelemetryState {
    public static final long DEFAULT_STALE_NS=3_000_000_000L;
    public record Snapshot(long epoch, boolean profileSupported, boolean fresh, boolean ready,
                           boolean startUnlocked, int lifecycle, long lastRxNs, Map<String,Object> fields) {
        public Snapshot { fields=Collections.unmodifiableMap(new LinkedHashMap<>(fields)); }
    }
    private long epoch, lastRxNs=-1, statusNs=-1, preflightTime=-1;
    private AirDecoder.Message capability, status;
    private final Map<String,Object> fields=new LinkedHashMap<>();
    public void reset(){epoch++;lastRxNs=-1;statusNs=-1;preflightTime=-1;capability=null;status=null;fields.clear();}
    public boolean profileSupported(){return capability!=null&&capability.integer("air_profile_id")==0;}
    public boolean hasUnknownProfile(){return capability!=null&&!profileSupported();}
    public AirDecoder.Message capability(){return profileSupported()?capability:null;}
    public void accept(AirDecoder.Message message,GspCodec.Envelope envelope,long rxNs){
        if(rxNs<0)throw new IllegalArgumentException("Negative monotonic time");
        if(lastRxNs>rxNs){reset();} // Local replay clock/session discontinuity cannot preserve permissions.
        if(message.type()==0x20&&message.integer("status_id")==1)reset();
        if(message.type()==0x11){long t=message.number("time_ms");if(preflightTime>=0&&t<preflightTime)reset();preflightTime=t;}
        if(message.type()==0x12){
            if(capability!=null&&capability.integer("air_profile_id")!=message.integer("air_profile_id")){status=null;statusNs=-1;fields.clear();}
            capability=message;
            if(!profileSupported()){status=null;statusNs=-1;fields.clear();}
        }
        if(message.type()==0x13&&profileSupported()){status=message;statusNs=rxNs;}
        if(message.type()==0x10){status=null;statusNs=-1;} // Flight telemetry never inherits preflight READY.
        lastRxNs=rxNs;fields.putAll(message.fields());fields.put("last_kind",message.kind());
        fields.put("radio_backend",envelope.backend());fields.put("radio_metrics_supported",envelope.metricsSupported());
        fields.put("rssi_dbm",envelope.rssiDbm());fields.put("snr_db",envelope.snrDb());
    }
    void enrich(Map<String,Object> derived){fields.putAll(derived);}
    public Snapshot snapshot(long nowNs){
        boolean fresh=statusNs>=0&&nowNs>=statusNs&&nowNs-statusNs<DEFAULT_STALE_NS;
        boolean ready=profileSupported()&&fresh&&status!=null&&status.integer("lifecycle_state")==3
                &&status.flag("system_ready")&&status.flag("selftest_passed")&&status.flag("capability_acked")
                &&status.flag("calibration_ready")&&status.flag("alignment_ready")
                &&status.integer("calibration_state")==4&&status.integer("alignment_state")==3
                &&(capability.integer("command_policy")==1||capability.integer("command_policy")==2);
        boolean unlocked=fresh&&profileSupported()&&status!=null&&status.flag("start_unlocked");
        int lifecycle=status==null?-1:status.integer("lifecycle_state");
        Map<String,Object> snapshotFields=new LinkedHashMap<>(fields);snapshotFields.put("authoritative_status_rx_ns",statusNs);
        return new Snapshot(epoch,profileSupported(),fresh,ready,unlocked,lifecycle,lastRxNs,snapshotFields);
    }
}

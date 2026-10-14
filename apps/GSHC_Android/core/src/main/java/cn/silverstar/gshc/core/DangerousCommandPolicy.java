package cn.silverstar.gshc.core;

/** Planning-only policy. This release never returns permission to transmit. */
public final class DangerousCommandPolicy {
    private DangerousCommandPolicy() {}
    public enum Decision { CONFIRMATION_REQUIRED, EPOCH_CHANGED, UNSUPPORTED_PROFILE, STALE_STATE, NOT_READY, LOCKED, DISABLED_IN_INITIAL_RELEASE }
    public record Confirmation(long epoch, long confirmedNs, boolean explicit) {}
    public static Decision evaluate(TelemetryState.Snapshot snapshot,Confirmation confirmation,long nowNs){
        if(confirmation==null||!confirmation.explicit())return Decision.CONFIRMATION_REQUIRED;
        if(confirmation.epoch()!=snapshot.epoch())return Decision.EPOCH_CHANGED;
        if(!snapshot.profileSupported())return Decision.UNSUPPORTED_PROFILE;
        Object statusTime=snapshot.fields().get("authoritative_status_rx_ns");
        if(!(statusTime instanceof Number)||((Number)statusTime).longValue()<0||nowNs<((Number)statusTime).longValue()||nowNs-((Number)statusTime).longValue()>=TelemetryState.DEFAULT_STALE_NS)return Decision.STALE_STATE;
        if(!snapshot.fresh()||nowNs<confirmation.confirmedNs()||nowNs-confirmation.confirmedNs()>=TelemetryState.DEFAULT_STALE_NS)return Decision.STALE_STATE;
        if(!snapshot.ready())return Decision.NOT_READY;
        if(!snapshot.startUnlocked())return Decision.LOCKED;
        return Decision.DISABLED_IN_INITIAL_RELEASE;
    }
}

package cn.silverstar.gshc.core;

import java.util.*;

/** Select exactly RX GSP_FRAME records; parsed duplicates and TX are never replayed. */
public final class RawReplay {
    private long accepted, skipped;
    public long accepted(){return accepted;} public long skipped(){return skipped;}
    public List<ReceivePipeline.Event> accept(Map<String,Object> record,ReceivePipeline pipeline){
        if(!"RX".equals(record.get("dir"))||!"GSP".equals(record.get("layer"))||!"GSP_FRAME".equals(record.get("kind"))){skipped++;return List.of();}
        Object hex=record.get("raw_hex");if(!(hex instanceof String))throw new IllegalArgumentException("Raw GSP record missing raw_hex");
        Object ns=record.get("host_rx_monotonic_ns"),ts=record.get("ts");
        if(!(ns instanceof Number)||!(ts instanceof Number))throw new IllegalArgumentException("Raw replay requires recorded host timestamps");
        long rxNs=((Number)ns).longValue();double seconds=((Number)ts).doubleValue();
        if(rxNs<0||!Double.isFinite(seconds)||seconds<0||seconds>Long.MAX_VALUE/1000.0)throw new IllegalArgumentException("Invalid replay time");
        byte[] raw=GspCodec.unhex((String)hex);GspCodec.Parser validator=new GspCodec.Parser();List<GspCodec.Frame> frames=validator.feed(raw);
        if(frames.size()!=1||!Arrays.equals(frames.get(0).raw(),raw))throw new IllegalArgumentException("Corrupt replay frame");
        accepted++;return pipeline.feed(raw,rxNs,(long)(seconds*1000));
    }
}

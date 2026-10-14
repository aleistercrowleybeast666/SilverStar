package cn.silverstar.gshc.core;

import java.nio.*;
import java.util.*;

public final class ReceivePipeline {
    public record Event(GspCodec.Frame gsp, AirDecoder.Message air, String error, List<Map<String,Object>> records) {
        public Event { records=List.copyOf(records); }
    }
    private GspCodec.Parser parser=new GspCodec.Parser(); private final TelemetryState state=new TelemetryState();
    private long parseErrors, receivedFlight, lostFlight, lastFlightTime=-1;
    public TelemetryState state(){return state;}
    public GspCodec.Diagnostics diagnostics(){return parser.diagnostics();}
    public long parseErrors(){return parseErrors;}
    public void reset(){parser=new GspCodec.Parser();state.reset();parseErrors=0;receivedFlight=0;lostFlight=0;lastFlightTime=-1;}
    public List<Event> feed(byte[] data,long rxNs,long wallMs){
        if(rxNs<0||wallMs<0)throw new IllegalArgumentException("Negative host time");
        List<Event> events=new ArrayList<>();
        for(GspCodec.Frame frame:parser.feed(data))events.add(process(frame,rxNs,wallMs));
        return events;
    }
    private Event process(GspCodec.Frame frame,long rxNs,long wallMs){
        List<Map<String,Object>> records=new ArrayList<>();Map<String,Object> raw=base(rxNs,wallMs,"GSP","GSP_FRAME");
        raw.put("msg_type",frame.type());raw.put("raw_hex",GspCodec.hex(frame.raw()));raw.put("payload_hex",GspCodec.hex(frame.payload()));records.add(freeze(raw));
        AirDecoder.Message message=null;String error="";GspCodec.Envelope envelope=null;
        try{
            byte[] p=frame.payload();
            if(frame.type()==1){if(p.length!=12)throw new IllegalArgumentException("GS_STATUS length");ByteBuffer b=ByteBuffer.wrap(p).order(ByteOrder.LITTLE_ENDIAN);Map<String,Object> r=base(rxNs,wallMs,"GSP_PARSED","GS_STATUS");r.put("gs_state",p[0]&255);r.put("radio_state",p[1]&255);r.put("tx_cnt",Integer.toUnsignedLong(b.getInt(2)));r.put("rx_cnt",Integer.toUnsignedLong(b.getInt(6)));r.put("crc_err_cnt",Short.toUnsignedInt(b.getShort(10)));records.add(freeze(r));}
            else if(frame.type()==4){if(p.length!=3)throw new IllegalArgumentException("GSP ACK length");Map<String,Object> r=base(rxNs,wallMs,"GSP_PARSED","GSP_ACK");r.put("ack_gsp_type",p[0]&255);r.put("result",p[1]&255);r.put("detail",p[2]&255);records.add(freeze(r));}
            else if(frame.type()==2||frame.type()==5){
                envelope=GspCodec.envelope(frame);byte[] a=envelope.air();Map<String,Object> r=radio(base(rxNs,wallMs,"AIR","AIR_RAW"),envelope);r.put("air_hex",GspCodec.hex(a));r.put("air_type",a.length>0?a[0]&255:null);r.put("air_len",a.length);records.add(freeze(r));
                if(state.hasUnknownProfile()&&(a.length==0||(a[0]&255)!=0x12))throw new IllegalArgumentException("AIR profile unsupported; retained raw only");
                message=AirDecoder.decode(a);state.accept(message,envelope,rxNs);
                r=radio(base(rxNs,wallMs,"AIR_PARSED",message.kind()),envelope);r.putAll(message.fields());
                if(message.type()==0x10||message.type()==0x11){convert(r,state.capability());state.enrich(r);}
                if(message.type()==0x10){trackFlight(r,message.number("time_ms"));}
                records.add(freeze(r));
            }
        }catch(IllegalArgumentException ex){error=ex.getMessage();parseErrors++;Map<String,Object> r=base(rxNs,wallMs,envelope==null?"GSP_PARSED":"AIR_PARSED",envelope==null?"GSP_PARSE_ERROR":"AIR_PARSE_ERROR");r.put("error",error);if(envelope!=null){radio(r,envelope);r.put("air_hex",GspCodec.hex(envelope.air()));}records.add(freeze(r));}
        return new Event(frame,message,error,records);
    }
    private void trackFlight(Map<String,Object> r,long time){long lost=0;boolean nonMonotonic=lastFlightTime>=0&&time<=lastFlightTime;
        if(lastFlightTime>=0&&time>lastFlightTime)lost=Math.max(0,(long)Math.rint((time-lastFlightTime)/200.0)-1);
        if(!nonMonotonic)lastFlightTime=time;receivedFlight++;lostFlight+=lost;r.put("lost_since_previous",lost);r.put("received_flight_packets",receivedFlight);r.put("estimated_lost_packets",lostFlight);r.put("expected_flight_packets",receivedFlight+lostFlight);r.put("packet_loss_rate",(double)lostFlight/(receivedFlight+lostFlight));r.put("time_non_monotonic",nonMonotonic);}
    private static Map<String,Object> base(long ns,long wall,String layer,String kind){Map<String,Object> r=new LinkedHashMap<>();r.put("ts",wall/1000.0);r.put("host_rx_monotonic_ns",ns);r.put("host_processed_monotonic_ns",ns);r.put("processing_lag_ms",0.0);r.put("timing_note","processing timestamp not sampled by pure core");r.put("dir","RX");r.put("layer",layer);r.put("kind",kind);return r;}
    private static Map<String,Object> radio(Map<String,Object> r,GspCodec.Envelope e){r.put("radio_backend",e.backend());r.put("radio_metrics_supported",e.metricsSupported());r.put("rssi_dbm",e.rssiDbm());r.put("snr_db",e.snrDb());return r;}
    private static Map<String,Object> freeze(Map<String,Object> r){return Collections.unmodifiableMap(new LinkedHashMap<>(r));}
    private static void convert(Map<String,Object> r,AirDecoder.Message capability){boolean valid=capability!=null&&capability.integer("accel_full_scale_g")>0&&capability.integer("gyro_full_scale_dps")>0;r.put("physical_conversion_valid",valid);r.put("air_profile_id",capability==null?null:0);r.put("accel_full_scale_g",capability==null?null:capability.integer("accel_full_scale_g"));r.put("gyro_full_scale_dps",capability==null?null:capability.integer("gyro_full_scale_dps"));r.put("accel_mps2",valid?scaled(r.get("accel_raw"),capability.integer("accel_full_scale_g")*9.80665/32768.0):null);r.put("gyro_radps",valid?scaled(r.get("gyro_raw"),capability.integer("gyro_full_scale_dps")*Math.PI/180/32768.0):null);}
    private static List<Double> scaled(Object value,double scale){List<?> source=(List<?>)value;List<Double> result=new ArrayList<>();for(Object n:source)result.add(((Number)n).doubleValue()*scale);return Collections.unmodifiableList(result);}
}

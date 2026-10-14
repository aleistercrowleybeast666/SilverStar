package cn.silverstar.gshc.core;

import java.nio.*;
import java.util.*;

/** Exact frozen M0/Profile 0 lengths and little-endian field layout. */
public final class AirDecoder {
    private AirDecoder() {}
    public record Message(int type, int seq, String kind, Map<String,Object> fields) {
        public Message { fields=Collections.unmodifiableMap(new LinkedHashMap<>(fields)); }
        public int integer(String key) { return ((Number)fields.get(key)).intValue(); }
        public long number(String key) { return ((Number)fields.get(key)).longValue(); }
        public boolean flag(String key) { return Boolean.TRUE.equals(fields.get(key)); }
    }
    private static int u(byte[] a,int i){return a[i]&255;}
    public static Message decode(byte[] a) {
        if(a.length<2)throw new IllegalArgumentException("AIR frame too short");
        int type=u(a,0), seq=u(a,1), required=switch(type){case 0x10->50;case 0x11->26;case 0x12,0x13,0x14,0x15,0x16,0x17,0x20,0x30,0x40->9;default->-1;};
        if(required<0||a.length!=required)throw new IllegalArgumentException("Unknown AIR type or bad length: "+type+"/"+a.length);
        ByteBuffer b=ByteBuffer.wrap(a).order(ByteOrder.LITTLE_ENDIAN); Map<String,Object> f=new LinkedHashMap<>(); f.put("seq",seq);
        String kind;
        switch(type){
            case 0x10,0x11 -> {
                kind=type==0x10?"FLIGHT_STATE":"PREFLIGHT_STATE";f.put("time_ms",Integer.toUnsignedLong(b.getInt(2)));
                f.put("accel_raw",shorts(b,6,3));f.put("gyro_raw",shorts(b,12,3));List<Integer> q=shorts(b,18,4);f.put("quat_q15",q);
                double norm=0;for(int n:q)norm+=(double)n*n;boolean valid=norm>0;norm=Math.sqrt(norm);
                List<Double> quat=valid?List.of(q.get(0)/norm,q.get(1)/norm,q.get(2)/norm,q.get(3)/norm):List.of(1.0,0.0,0.0,0.0);
                f.put("quat",quat);f.put("quat_raw_zero",!valid);f.put("quat_valid",valid);f.put("euler_rpy",euler(quat));
                if(type==0x10){f.put("vel_mps",floats(b,26));f.put("pos_m",floats(b,38));}
            }
            case 0x12 -> {kind="CAPABILITY";put(f,a,2,"air_profile_id","command_policy","calibration_mode_mask","sensor_summary_flags","accel_full_scale_g");f.put("gyro_full_scale_dps",Short.toUnsignedInt(b.getShort(7)));f.put("profile_supported",u(a,2)==0);}
            case 0x13 -> {kind="PREFLIGHT_STATUS";f.put("lifecycle_state",u(a,2));f.put("calibration_state",u(a,3)&15);int mode=u(a,3)>>>4;f.put("calibration_mode",mode==15?255:mode);f.put("completed_face_mask",u(a,4)&63);f.put("current_face",u(a,5));f.put("alignment_state",u(a,6)&15);
                String[] flags={"system_ready","start_unlocked","selftest_passed","gnss_position_usable","capability_acked","calibration_ready","alignment_ready"};for(int i=0;i<flags.length;i++)f.put(flags[i],(u(a,7)&(1<<i))!=0);f.put("start_block_reason",u(a,8));}
            case 0x14 -> {kind="SENSOR_STATUS";put(f,a,2,"snapshot_id","sensor_id","instance_id","status_flags","detail_code","index","total");if(u(a,8)==0||u(a,7)>=u(a,8))throw new IllegalArgumentException("SENSOR_STATUS index/total");f.put("raw_flags",u(a,5));f.put("sensor_name",sensorName(u(a,3)));}
            case 0x15,0x16,0x17 -> {int session=Short.toUnsignedInt(b.getShort(2));if(session==0)throw new IllegalArgumentException("Navigation session zero");f.put("session",session);f.put("generation",Short.toUnsignedInt(b.getShort(4)));
                if(type==0x15){kind="NAV_CAPABILITY";put(f,a,6,"schema","algorithm_id","group_mask");}else if(type==0x16){kind="NAV_PREPARATION";put(f,a,6,"required_mask","ready_mask","reason");}else{kind="NAV_HEALTH";f.put("selector",u(a,6));f.put("value",Short.toUnsignedInt(b.getShort(7)));}}
            case 0x20 -> {kind="STATUS";f.put("status_id",u(a,2));f.put("time_ms",Integer.toUnsignedLong(b.getInt(3)));put(f,a,7,"arg0","arg1");}
            case 0x30 -> {kind="CMD";f.put("cmd_id",u(a,2));f.put("token",Integer.toUnsignedLong(b.getInt(3)));put(f,a,7,"param0","param1");}
            case 0x40 -> {kind="ACK";put(f,a,2,"ack_seq","ack_cmd_id","result");f.put("time_ms",Integer.toUnsignedLong(b.getInt(5)));}
            default -> throw new IllegalArgumentException("Unreachable AIR type");
        }
        return new Message(type,seq,kind,f);
    }
    private static void put(Map<String,Object> f,byte[] a,int offset,String... names){for(int i=0;i<names.length;i++)f.put(names[i],u(a,offset+i));}
    private static List<Integer> shorts(ByteBuffer b,int offset,int count){List<Integer> out=new ArrayList<>();for(int i=0;i<count;i++)out.add((int)b.getShort(offset+i*2));return Collections.unmodifiableList(out);}
    private static List<Double> floats(ByteBuffer b,int offset){List<Double> out=new ArrayList<>();for(int i=0;i<3;i++){double v=b.getFloat(offset+i*4);if(!Double.isFinite(v))throw new IllegalArgumentException("Nonfinite flight field");out.add(v);}return Collections.unmodifiableList(out);}
    private static List<Double> euler(List<Double> q){double w=q.get(0),x=q.get(1),y=q.get(2),z=q.get(3);return List.of(Math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)),Math.asin(Math.max(-1,Math.min(1,2*(w*y-z*x)))),Math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)));}
    public static String sensorName(int id){String[] names={"","IMU","GNSS","BAROMETER","MAGNETOMETER","AIR_DATA","RANGEFINDER","RADAR_ALTIMETER","SUN_SENSOR","STAR_TRACKER","VISION","EXTERNAL_ATTITUDE","DUAL_GNSS_HEADING","TEMPERATURE","HUMIDITY"};return id>0&&id<names.length?names[id]:String.format(Locale.ROOT,"UNKNOWN_SENSOR_0x%02X",id);}
}

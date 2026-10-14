import cn.silverstar.gshc.core.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class CoreTests {
    private static int checks;
    private static void check(boolean result,String why){checks++;if(!result)throw new AssertionError(why);}
    private static void rejects(Runnable run,String why){boolean rejected=false;try{run.run();}catch(IllegalArgumentException ex){rejected=true;}check(rejected,why);}
    private static byte[] cap(int profile){return new byte[]{0x12,1,(byte)profile,1,7,15,16,(byte)0xd0,7};}
    private static byte[] ready(){return new byte[]{0x13,2,3,4,63,(byte)255,3,0x7f,0};}
    private static void rx(ReceivePipeline p,byte[] air,long ns){p.feed(Simulator.wrap(air,false),ns,1700000000000L);}
    public static void main(String[] args)throws Exception{
        check(GspCodec.crc16("123456789".getBytes(StandardCharsets.US_ASCII),0,9)==0x29b1,"CRC known vector");
        byte[] frame=Simulator.wrap(cap(0),false);
        for(int split=0;split<=frame.length;split++){GspCodec.Parser p=new GspCodec.Parser();List<GspCodec.Frame> found=new ArrayList<>();found.addAll(p.feed(Arrays.copyOfRange(frame,0,split)));found.addAll(p.feed(Arrays.copyOfRange(frame,split,frame.length)));check(found.size()==1&&Arrays.equals(found.get(0).raw(),frame),"every fragment boundary");}
        GspCodec.Parser bytes=new GspCodec.Parser();int count=0;for(byte b:frame)count+=bytes.feed(new byte[]{b}).size();check(count==1,"one byte fragmentation");
        GspCodec.Parser noisy=new GspCodec.Parser();noisy.feed(new byte[100000]);check(noisy.diagnostics().bufferSize()<=1,"noise memory bound");check(noisy.feed(frame).size()==1,"resync noise");
        byte[] bad=frame.clone();bad[bad.length-1]^=1;noisy.feed(bad);check(noisy.feed(frame).size()==1&&noisy.diagnostics().crcErrors()>0,"bad CRC recovery");
        noisy.feed(new byte[]{(byte)0xa5,0x5a,2,(byte)255});check(noisy.feed(frame).size()==1,"oversize length recovery");
        rejects(()->GspCodec.encode(2,new byte[65]),"encoder length bound");
        ReceivePipeline p=new ReceivePipeline();rx(p,cap(0),1);check(!p.state().snapshot(1).ready(),"capability is not READY");
        rx(p,new byte[]{0x40,1,0,1,0,0,0,0,0},2);check(!p.state().snapshot(2).ready(),"ACK is not READY");
        rx(p,ready(),3);check(p.state().snapshot(3).ready(),"authoritative READY");
        check(p.state().snapshot(3+TelemetryState.DEFAULT_STALE_NS-1).ready(),"before freshness boundary");
        check(!p.state().snapshot(3+TelemetryState.DEFAULT_STALE_NS).ready(),"at stale boundary");
        check(!p.state().snapshot(2).ready(),"clock earlier than status invalid");
        byte[] status=ready();status[7]&=~0x20;rx(p,status,4);check(!p.state().snapshot(4).ready(),"inconsistent calibration flag");
        rx(p,ready(),5);rx(p,cap(77),6);check(!p.state().snapshot(6).ready()&&!p.state().snapshot(6).profileSupported(),"unknown profile revokes READY");
        var unknown=p.feed(Simulator.wrap(ready(),false),7,1);check(unknown.get(0).air()==null&&!unknown.get(0).error().isEmpty(),"unknown profile raw only");
        rx(p,cap(0),8);check(!p.state().snapshot(8).ready(),"known profile cannot revive old status");rx(p,ready(),9);long epoch=p.state().snapshot(9).epoch();p.reset();check(!p.state().snapshot(10).ready()&&p.state().snapshot(10).epoch()>epoch,"reconnect clears authorization");
        rx(p,cap(0),11);rx(p,ready(),12);rx(p,new byte[]{0x20,1,1,0,0,0,0,0,0},13);check(!p.state().snapshot(13).profileSupported(),"BOOT clears capability");
        rx(p,cap(0),14);rx(p,ready(),15);p.feed(Simulator.wrap(cap(0),true),16,1);check(p.state().snapshot(16).fields().get("rssi_dbm")==null&&p.state().snapshot(16).fields().get("snr_db")==null,"NRF clears metrics");
        var malformed=p.feed(GspCodec.encode(5,new byte[]{2,0,1,0}),17,1);check(!malformed.get(0).error().isEmpty(),"unknown backend rejected");
        malformed=p.feed(GspCodec.encode(5,new byte[]{1,1,1,0}),18,1);check(!malformed.get(0).error().isEmpty(),"unknown radio flags rejected");
        rejects(()->AirDecoder.decode(new byte[]{0x11,1}),"AIR exact length");rejects(()->AirDecoder.decode(new byte[]{0x15,1,0,0,0,0,0,0,0}),"nav nonzero session");
        rejects(()->AirDecoder.decode(new byte[]{0x14,1,0,1,0,0,0,1,1}),"sensor index bounded");
        var sensor=AirDecoder.decode(new byte[]{0x14,1,0,(byte)200,0,0,0,0,1});check(sensor.fields().get("sensor_name").equals("UNKNOWN_SENSOR_0xC8"),"unknown sensor preserved");
        byte[] zero=new byte[26];zero[0]=0x11;check(!AirDecoder.decode(zero).flag("quat_valid"),"zero quaternion marked invalid");
        var snap=p.state().snapshot(16);check(DangerousCommandPolicy.evaluate(snap,null,16)==DangerousCommandPolicy.Decision.CONFIRMATION_REQUIRED,"confirmation needed");
        check(DangerousCommandPolicy.evaluate(snap,new DangerousCommandPolicy.Confirmation(snap.epoch()+1,16,true),16)==DangerousCommandPolicy.Decision.EPOCH_CHANGED,"epoch confirmation binding");
        check(DangerousCommandPolicy.evaluate(snap,new DangerousCommandPolicy.Confirmation(snap.epoch(),16,true),16)==DangerousCommandPolicy.Decision.DISABLED_IN_INITIAL_RELEASE,"even valid confirmation never enables TX");
        check(DangerousCommandPolicy.evaluate(p.state().snapshot(16+TelemetryState.DEFAULT_STALE_NS),new DangerousCommandPolicy.Confirmation(snap.epoch(),16,true),16+TelemetryState.DEFAULT_STALE_NS)==DangerousCommandPolicy.Decision.STALE_STATE,"expired confirmation blocked");
        check(DangerousCommandPolicy.evaluate(snap,new DangerousCommandPolicy.Confirmation(snap.epoch(),4000000016L,true),4000000016L)==DangerousCommandPolicy.Decision.STALE_STATE,"cached snapshot cannot regain readiness through fresh confirmation");
        List<Map<String,Object>> records=new ArrayList<>();ReceivePipeline live=new ReceivePipeline();Simulator sim=new Simulator();
        for(long ms=0;ms<=12000;ms+=200)for(var e:live.feed(sim.next(ms),1000000000L+ms*1000000,1700000000000L+ms))records.addAll(e.records());
        ReceivePipeline replayed=new ReceivePipeline();RawReplay replay=new RawReplay();for(var record:records)replay.accept(record,replayed);
        check(live.state().snapshot(13000000000L).fields().equals(replayed.state().snapshot(13000000000L).fields()),"raw simulation replay state matches");
        check(live.diagnostics().frames()==replayed.diagnostics().frames(),"replay processes raw exactly once");
        check(!live.state().snapshot(13000000000L).ready(),"flight cannot retain preflight ready");
        Map<String,Object> tx=new LinkedHashMap<>(records.get(0));tx.put("dir","TX");long before=replayed.diagnostics().frames();check(replay.accept(tx,replayed).isEmpty()&&before==replayed.diagnostics().frames(),"TX ignored in replay");
        Map<String,Object> corrupt=new LinkedHashMap<>(records.get(0));corrupt.put("raw_hex","a55a0200ffff");rejects(()->replay.accept(corrupt,replayed),"corrupt replay rejected");
        if(args.length>0){Path fixture=Path.of(args[0]);Files.createDirectories(fixture.getParent());try(BufferedWriter writer=Files.newBufferedWriter(fixture,StandardCharsets.UTF_8)){writer.write("{\"layer\":\"SESSION\",\"kind\":\"SESSION_START\",\"simulated\":true,\"data_kind\":\"SIMULATED\",\"simulation_label\":\"Android pure Java deterministic fixture\",\"app_version\":\"0.1.0-dev\",\"reference_tag\":\"v0.1.2\"}\n");for(var r:records){writer.write(json(r));writer.newLine();}}}
        System.out.println("PASS: "+checks+" core assertions; "+live.diagnostics().frames()+" RX frames; "+records.size()+" PC-compatible records; raw replay exact match.");
    }
    private static String json(Object o){if(o==null)return "null";if(o instanceof String s)return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n")+"\"";if(o instanceof Number||o instanceof Boolean)return o.toString();if(o instanceof Map<?,?> m){StringJoiner j=new StringJoiner(",","{","}");for(var e:m.entrySet())j.add(json(e.getKey().toString())+":"+json(e.getValue()));return j.toString();}if(o instanceof List<?> l){StringJoiner j=new StringJoiner(",","[","]");for(var e:l)j.add(json(e));return j.toString();}throw new IllegalArgumentException("Unsupported fixture JSON type");}
}

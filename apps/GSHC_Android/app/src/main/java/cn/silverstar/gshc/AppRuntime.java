package cn.silverstar.gshc;

import android.content.Context;
import android.os.SystemClock;
import cn.silverstar.gshc.core.*;
import cn.silverstar.gshc.storage.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Survives Activity recreation. One bounded worker owns protocol and log ordering. */
public final class AppRuntime {
    public final SessionStore sessions;
    public final ExecutorService files=Executors.newSingleThreadExecutor();
    public final PortClaims ports=new PortClaims();
    public volatile String groundSelection="未选择", debugSelection="未选择";
    public volatile String debugStatus="未连接", tfStatus="尚未协商维护文件服务";
    public volatile cn.silverstar.gshc.core.tf.MaintenanceTfSource maintenance;
    public volatile String tfDirectory="";
    public volatile String groundStatus="Disconnected";
    private PortClaims.Lease usbOwner;
    private final java.util.concurrent.atomic.AtomicBoolean overloaded=new java.util.concurrent.atomic.AtomicBoolean();
    private final ThreadPoolExecutor worker=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(64));
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor();
    private final ReceivePipeline pipeline=new ReceivePipeline();
    private ScheduledFuture<?> simulation;
    public volatile String mode="idle", status="未连接 · 默认仿真 / 只读", error="";
    public volatile boolean recording;
    public volatile long transportEpoch;
    public volatile VerifiedExport.Receipt receipt;
    private volatile TelemetryState.Snapshot snapshot=pipeline.state().snapshot(0);
    private final Deque<double[]> points=new ArrayDeque<>();
    public AppRuntime(Context context)throws IOException{
        sessions=new SessionStore(context.getFilesDir().toPath().resolve("sessions"));
        timer.scheduleWithFixedDelay(()->submit(()->{if(!mode.startsWith("replay"))snapshot=pipeline.state().snapshot(SystemClock.elapsedRealtimeNanos());}),500,500,TimeUnit.MILLISECONDS);
    }
    public TelemetryState.Snapshot snapshot(){return snapshot;}
    public synchronized List<double[]> points(){return new ArrayList<>(points);}
    public void simulate(){submit(()->{
        stopInternal("switch");pipeline.reset();clearPoints();error="";
        sessions.begin("模拟会话 "+new java.text.SimpleDateFormat("HH:mm:ss",Locale.ROOT).format(new Date()),"simulation",SystemClock.elapsedRealtimeNanos());
        mode="simulation";recording=true;status="仿真输入 · 无设备命令";
        Simulator simulator=new Simulator();long start=SystemClock.elapsedRealtime(),epoch=transportEpoch;
        simulation=timer.scheduleWithFixedDelay(()->submit(()->{if(epoch==transportEpoch&&mode.equals("simulation"))receive(simulator.next(SystemClock.elapsedRealtime()-start));}),0,200,TimeUnit.MILLISECONDS);
    });}
    public Future<?> beginUsb(String device,PortClaims.Lease owner){return worker.submit(()->{
        if(!ports.current(owner))throw new IllegalStateException("USB lease expired before recording");
        try{
            stopInternal("switch");pipeline.reset();clearPoints();error="";
            sessions.begin(device,"usb-readonly",SystemClock.elapsedRealtimeNanos());
            synchronized(ports){
                if(!ports.current(owner))throw new IOException("USB lease expired before recording commit");
                usbOwner=owner;mode="usb-readonly";recording=true;status="USB 只读 · 230400 8N1";
            }
        }catch(IOException e){fail(e);throw new IllegalStateException(e);}
    });}
    public void receiveUsb(byte[] data,long epoch){byte[] copy=data.clone();long rxNs=SystemClock.elapsedRealtimeNanos(),wallMs=System.currentTimeMillis();submit(()->{if(epoch==transportEpoch&&mode.equals("usb-readonly")&&recording)receive(copy,rxNs,wallMs);});}
    private void receive(byte[] bytes)throws IOException {
        receive(bytes,SystemClock.elapsedRealtimeNanos(),System.currentTimeMillis());
    }
    private void receive(byte[] bytes,long ns,long ms)throws IOException {
        if(!recording)return;
        Map<String,Object> raw=new LinkedHashMap<>();raw.put("ts",ms/1000.0);raw.put("host_monotonic_ns",ns);raw.put("dir","RX");raw.put("layer","SERIAL");raw.put("kind","SERIAL_RX");raw.put("raw_hex",hex(bytes));
        sessions.append(raw);
        for(ReceivePipeline.Event event:pipeline.feed(bytes,ns,ms)){
            for(Map<String,Object> rec:event.records()){
                Map<String,Object> recorded=new LinkedHashMap<>(rec);long processed=SystemClock.elapsedRealtimeNanos();
                recorded.put("host_processed_monotonic_ns",processed);recorded.put("host_monotonic_ns",processed);
                recorded.put("processing_lag_ms",(processed-ns)/1_000_000.0);recorded.remove("timing_note");sessions.append(recorded);
            }
            addPoint(event.air());
        }
        snapshot=pipeline.state().snapshot(ns);
    }
    public void stopUsb(PortClaims.Lease owner,String reason){submit(()->{if(owner!=null&&owner.equals(usbOwner))stopInternal(reason);});}
    public void stop(String reason){submit(()->stopInternal(reason));}
    public void background(){
        final long epoch=transportEpoch;
        submit(()->{if(epoch==transportEpoch&&mode.equals("simulation"))stopInternal("应用进入后台；模拟停止");});
    }
    private void stopInternal(String reason)throws IOException {
        if(simulation!=null){simulation.cancel(false);simulation=null;}
        recording=false;mode="idle";usbOwner=null;
        transportEpoch++;
        try{sessions.finish(reason,!reason.startsWith("FAIL:"));}finally{pipeline.reset();snapshot=pipeline.state().snapshot(SystemClock.elapsedRealtimeNanos());status=reason;}
    }
    public void replay(String id){submit(()->{
        if(!"silverstar.gshc-jsonl".equals(sessions.metadata(id).getProperty("log_format","silverstar.gshc-jsonl")))throw new IOException("此文件不是JSONL；请导出原生TF日志给PC FLP并提供精确匹配解码包");
        stopInternal("开始只读回放");pipeline.reset();clearPoints();error="";mode="replay";
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(new FileInputStream(sessions.rawFile(id).toFile()),StandardCharsets.UTF_8))){
            String line;long count=0;RawReplay replay=new RawReplay();
            while((line=boundedLine(reader))!=null){
                if(Thread.currentThread().isInterrupted())throw new InterruptedIOException();
                JSONObject json;
                try{json=new JSONObject(line);}catch(JSONException ex){throw new IOException("损坏的 JSONL 行 "+(count+1),ex);}
                Map<String,Object> record=toMap(json);
                List<ReceivePipeline.Event> events=replay.accept(record,pipeline);
                if(!events.isEmpty()){
                    Object ns=record.get("host_rx_monotonic_ns");snapshot=pipeline.state().snapshot(ns instanceof Number?((Number)ns).longValue():0);
                    for(ReceivePipeline.Event event:events)addPoint(event.air());
                }
                count++;
            }
            status="回放完成 · "+count+" 行 · 原文件未改动 · 不发送 TX";
        }finally{mode="replay-complete";}
    });}
    public static String boundedLine(Reader reader)throws IOException {
        StringBuilder b=new StringBuilder();int c;
        while((c=reader.read())!=-1&&c!='\n'){if(b.length()>=65536)throw new IOException("JSONL 行超过64KiB限制");b.append((char)c);}
        return c==-1&&b.length()==0?null:b.toString();
    }
    private void submit(Work work){
        try{worker.execute(()->{try{if(overloaded.getAndSet(false)){fail(new IOException("Receive queue overflow; recording incomplete"));return;}work.run();}catch(Exception e){fail(e);}});}
        catch(RejectedExecutionException e){overloaded.set(true);error="接收队列已满，停止接收；会话可能不完整";recording=false;if(simulation!=null)simulation.cancel(false);}
    }
    private void fail(Exception e){error=e.getMessage()==null?e.toString():e.getMessage();try{stopInternal("FAIL:"+error);}catch(IOException close){error+="；关闭失败 "+close.getMessage();}}
    private synchronized void clearPoints(){points.clear();}
    private synchronized void addPoint(AirDecoder.Message message){
        // Sample decoded frames in source order, including repeated device timestamps.
        if(message==null||message.type()!=0x10)return;
        Object v=message.fields().get("vel_mps"),p=message.fields().get("pos_m");
        if(!(v instanceof List<?>)||!(p instanceof List<?>))return;
        double[] point=new double[6];
        for(int i=0;i<3;i++){point[i]=((Number)((List<?>)v).get(i)).doubleValue();point[i+3]=((Number)((List<?>)p).get(i)).doubleValue();}
        if(points.size()==300)points.removeFirst();points.addLast(point);
    }
    private static String hex(byte[] bytes){StringBuilder b=new StringBuilder();for(byte v:bytes)b.append(String.format(Locale.ROOT,"%02x",v&255));return b.toString();}
    private static Map<String,Object> toMap(JSONObject json)throws JSONException{
        Map<String,Object> map=new LinkedHashMap<>();Iterator<String> keys=json.keys();
        while(keys.hasNext()){String key=keys.next();Object value=json.get(key);map.put(key,value==JSONObject.NULL?null:value);}return map;
    }
    private interface Work{void run()throws Exception;}
}

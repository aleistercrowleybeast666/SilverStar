package cn.silverstar.gshc.storage;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import java.util.concurrent.*;

public final class StorageTests {
    private static int checks;
    private static void check(boolean ok,String reason){checks++;if(!ok)throw new AssertionError(reason);}
    private interface Attempt {void run()throws IOException;}
    private static void rejects(Attempt work,String reason)throws IOException{boolean failed=false;try{work.run();}catch(IOException expected){failed=true;}check(failed,reason);}
    private static final class MemoryTarget implements VerifiedExport.Target {
        byte[] bytes=new byte[0];boolean closed,denyRead,denyWrite,failClose,truncate;
        int writes;
        public OutputStream openWrite()throws IOException{
            if(denyWrite)throw new IOException("write denied");writes++;closed=false;
            return new ByteArrayOutputStream(){@Override public void close()throws IOException{super.close();bytes=toByteArray();closed=true;if(failClose)throw new IOException("target close failed");}};
        }
        public InputStream openRead()throws IOException{check(closed,"target closed before readback");if(denyRead)throw new IOException("permission revoked");return new ByteArrayInputStream(truncate?Arrays.copyOf(bytes,bytes.length-12):bytes);}
        public String description(){return "generated-memory-target";}
    }
    private static String create(SessionStore store)throws IOException{
        String id=store.begin("Synthetic session","simulation",123456789);
        store.append(Map.of("dir","RX","layer","GSP","kind","GSP_FRAME","raw_hex","a55a04030300006312","ts",1.0,"host_monotonic_ns",123456790));
        store.finish("test");return id;
    }
    public static void main(String[] args)throws Exception{
        Path output=Paths.get(args[0]);Files.createDirectories(output);Path scratch=Files.createTempDirectory(output,"storage-generated-");
        SessionStore store=new SessionStore(scratch.resolve("sessions"));String id=create(store);byte[] original=Files.readAllBytes(store.rawFile(id));
        check(new String(original,StandardCharsets.UTF_8).contains("\"log_format_version\":1"),"new JSONL explicitly versioned");
        MemoryTarget target=new MemoryTarget();var receipt=VerifiedExport.copy(store,id,target,true);
        check(receipt.verified,"copy verified");check(Arrays.equals(original,Files.readAllBytes(store.rawFile(id))),"copy preserves source bytes");
        Files.write(output.resolve("new-session-export.zip"),target.bytes);
        try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(target.bytes))){ZipEntry entry;boolean found=false;while((entry=zip.getNextEntry())!=null){if(entry.getName().endsWith(".jsonl")){check(Arrays.equals(original,zip.readAllBytes()),"ZIP raw bytes identical");found=true;}}check(found,"raw JSONL present");}
        rejects(()->VerifiedExport.confirmCut(store,receipt,false),"cut requires confirmation");check(store.list(false).contains(id),"unconfirmed cut source retained");
        target.denyRead=true;rejects(()->VerifiedExport.confirmCut(store,receipt,true),"revoked permission before commit blocks cut");check(store.list(false).contains(id),"revoked target preserves source");target.denyRead=false;
        target.truncate=true;rejects(()->VerifiedExport.confirmCut(store,receipt,true),"truncated ZIP central directory blocks cut");check(store.list(false).contains(id),"truncated destination preserves source");target.truncate=false;
        store.rename(id,"Changed name");rejects(()->VerifiedExport.confirmCut(store,receipt,true),"changed source metadata invalidates receipt");check(store.list(false).contains(id),"changed source retained");
        var renewed=VerifiedExport.copy(store,id,target,true);VerifiedExport.confirmCut(store,renewed,true);
        check(!store.list(false).contains(id)&&store.list(true).contains(id),"confirmed verified cut atomically recycles source");store.restore(id);check(Arrays.equals(original,Files.readAllBytes(store.rawFile(id))),"recycle restoration preserves exact raw bytes");
        rejects(()->store.recycle(id,false),"delete requires confirmation");
        store.recycle(id,true);String oldRecycleVersion=store.recycledVersion(id);store.restore(id,oldRecycleVersion);store.recycle(id,true);
        rejects(()->store.restore(id,oldRecycleVersion),"stale dialog cannot restore a new recycle cycle");
        check(store.list(true).contains(id),"stale restore keeps recycled source unchanged");
        String latestRecycleVersion=store.recycledVersion(id);store.restore(id,latestRecycleVersion);
        rejects(()->store.restore(id,latestRecycleVersion),"restore confirmation cannot be applied twice");
        check(Arrays.equals(original,Files.readAllBytes(store.rawFile(id))),"versioned restoration retains original bytes");
        String active=store.begin("Active","simulation",500);MemoryTarget never=new MemoryTarget();
        rejects(()->VerifiedExport.copy(store,active,never,true),"active session export blocked");check(never.writes==0,"active export never opens destination");rejects(()->store.recycle(active,true),"active deletion blocked");store.finish("test complete");
        MemoryTarget unavailable=new MemoryTarget();unavailable.denyRead=true;var copy=VerifiedExport.copy(store,id,unavailable,false);check(!copy.verified,"readback unavailable reported as unverified copy");
        rejects(()->VerifiedExport.confirmCut(store,copy,true),"unverified copy cannot be cut");rejects(()->VerifiedExport.copy(store,id,unavailable,true),"cut staging readback failure rejects");check(store.list(false).contains(id),"failed readback source retained");
        MemoryTarget closing=new MemoryTarget();closing.failClose=true;rejects(()->VerifiedExport.copy(store,id,closing,true),"destination close failure rejects");check(store.list(false).contains(id),"close failure source retained");
        MemoryTarget denied=new MemoryTarget();denied.denyWrite=true;rejects(()->VerifiedExport.copy(store,id,denied,true),"write denial rejects");
        Thread.currentThread().interrupt();try{rejects(()->VerifiedExport.copy(store,id,new MemoryTarget(),true),"interruption rejects export");}finally{Thread.interrupted();}check(store.list(false).contains(id),"interrupted export source retained");
        byte[] legacy="{\"dir\":\"META\",\"layer\":\"SESSION\",\"kind\":\"SESSION_START\",\"ts\":123.25}\r\n".getBytes(StandardCharsets.UTF_8);
        String legacyId=store.importRaw(new ByteArrayInputStream(legacy),"Legacy raw");MemoryTarget legacyTarget=new MemoryTarget();VerifiedExport.copy(store,legacyId,legacyTarget,true);Files.write(output.resolve("legacy-session-export.zip"),legacyTarget.bytes);
        check(Arrays.equals(legacy,Files.readAllBytes(store.rawFile(legacyId))),"legacy import preserves CRLF bytes");check(store.metadata(legacyId).getProperty("log_format_version").equals("legacy-unversioned"),"legacy version preserved");
        String versioned=store.importRaw(new ByteArrayInputStream(original),"Versioned raw","1");check(store.metadata(versioned).getProperty("log_format_version").equals("1"),"versioned import identity retained");
        int before=store.list(false).size();InputStream failing=new InputStream(){public int read()throws IOException{throw new IOException("read interrupted");}};
        rejects(()->store.importRaw(failing,"Incomplete"),"failed import rejects");check(store.list(false).size()==before,"partial import not published as a session");
        rejects(()->store.rawFile("../outside"),"path traversal session rejected");
        // Shared protocol golden bytes exercise preservation, not validity as a real flight log.
        byte[] transferBytes="123456789".getBytes(StandardCharsets.US_ASCII);
        Path downloaded=scratch.resolve("1.sslog");Files.write(downloaded,transferBytes);
        byte[] transferMeta="token=1-CBF43926-00000009\nsize=9\n".getBytes(StandardCharsets.US_ASCII);
        Files.write(scratch.resolve("1.metadata"),transferMeta);
        String flight=store.importFlightLog(downloaded,false);
        check(Arrays.equals(transferBytes,Files.readAllBytes(store.rawFile(flight))),"TF import preserves exact binary bytes");
        check(!Boolean.parseBoolean(store.metadata(flight).getProperty("complete")),"transfer success does not assert finalized flight");
        check(store.metadata(flight).getProperty("decoder_identity").equals("unverified"),"TF import does not fabricate decoder match");
        check(store.files(flight).size()==3,"TF metadata sidecar retained");
        MemoryTarget flightTarget=new MemoryTarget();VerifiedExport.copy(store,flight,flightTarget,true);Files.write(output.resolve("tf-session-export.zip"),flightTarget.bytes);
        String mock=store.importFlightLog(downloaded,true);
        check(store.rawFile(mock).getFileName().toString().equals("mock-fixture.bin"),"mock bytes never named SSLOG");
        check(store.metadata(mock).getProperty("log_format").equals("synthetic-fixture"),"mock format explicitly synthetic");
        MemoryTarget mockTarget=new MemoryTarget();VerifiedExport.copy(store,mock,mockTarget,true);Files.write(output.resolve("mock-session-export.zip"),mockTarget.bytes);
        MemoryTarget sequential=new MemoryTarget();var copied=VerifiedFileCopy.copy(downloaded,sequential);
        check(copied.size()==9&&Arrays.equals(sequential.bytes,transferBytes),"TF sequential provider copy preserves binary without seek or rename");
        sequential.denyRead=true;rejects(()->VerifiedFileCopy.copy(downloaded,sequential),"TF revoked readback cannot claim success");
        check(Arrays.equals(Files.readAllBytes(downloaded),transferBytes),"failed TF destination leaves internal source intact");
        MemoryTarget badClose=new MemoryTarget();badClose.failClose=true;rejects(()->VerifiedFileCopy.copy(downloaded,badClose),"TF output close failure blocks success");
        VerifiedExport.Target corrupt=new VerifiedExport.Target(){public OutputStream openWrite(){return new ByteArrayOutputStream();}public InputStream openRead(){return new ByteArrayInputStream("000000000".getBytes(StandardCharsets.US_ASCII));}public String description(){return "corrupted-generated-target";}};
        rejects(()->VerifiedFileCopy.copy(downloaded,corrupt),"same-length corrupted TF destination rejected");
        VerifiedExport.Target full=new VerifiedExport.Target(){public OutputStream openWrite(){return new OutputStream(){private int remaining=4;public void write(int b)throws IOException{if(remaining--==0)throw new IOException("Generated ENOSPC");}};}public InputStream openRead(){throw new AssertionError("failed write cannot reach readback");}public String description(){return "generated-full-disk";}};
        rejects(()->VerifiedFileCopy.copy(downloaded,full),"disk-full during TF copy cannot report success");
        rejects(()->VerifiedExport.copy(store,id,full,true),"disk-full during ZIP export cannot authorize cut");
        check(Arrays.equals(transferBytes,Files.readAllBytes(downloaded))&&Arrays.equals(original,Files.readAllBytes(store.rawFile(id))),"disk-full preserves TF and session originals");
        Thread.currentThread().interrupt();try{rejects(()->VerifiedFileCopy.copy(downloaded,new MemoryTarget()),"TF copy cancellation blocks success");}finally{Thread.interrupted();}
        check(Arrays.equals(transferBytes,Files.readAllBytes(downloaded)),"TF copy cancellation preserves original");
        check(Arrays.equals(LayoutPolicy.order(360),new int[]{0,3,1,4,2,5}),"phone ENU paired 2x3");
        check(Arrays.equals(LayoutPolicy.order(839),new int[]{0,3,1,4,2,5}),"narrow tablet window remains 2x3");
        check(Arrays.equals(LayoutPolicy.order(840),new int[]{0,1,2,3,4,5}),"expanded window becomes 3x2");
        check(!LayoutPolicy.splitPreflight(900,400),"short landscape avoids two-pane preflight");
        check(LayoutPolicy.chartHeight(2)>=260,"large text increases chart height");
        PortClaims ports=new PortClaims();PortClaims.Key key=new PortClaims.Key("/usb/1",0x1234,1,0);
        var ground=ports.claim(PortClaims.Role.GROUND,key);
        rejects(()->ports.claim(PortClaims.Role.DEBUG,key),"same physical port cannot be claimed twice");
        var debug=ports.claim(PortClaims.Role.DEBUG,new PortClaims.Key("/usb/1",0x1234,1,1));
        check(ports.current(ground)&&ports.current(debug),"distinct interfaces may have independent owners");
        ports.detached("/usb/1");check(!ports.current(ground)&&!ports.current(debug),"detach invalidates all ports on selected device");
        rejects(()->ports.claim(PortClaims.Role.GROUND,key),"detach retains open-owner reservation until cleanup");
        ports.release(ground);ports.release(debug);
        var replacement=ports.claim(PortClaims.Role.GROUND,key);check(replacement.epoch()!=ground.epoch(),"reconnect gets new identity epoch");
        ports.release(ground);check(ports.current(replacement),"late old callback cannot release replacement");
        ports.invalidate(ground);check(ports.current(replacement),"old cleanup cannot invalidate replacement lease");
        var independent=ports.claim(PortClaims.Role.DEBUG,new PortClaims.Key("/usb/2",0x1234,1,0));
        ports.detached("/usb/1");check(ports.current(independent),"detach keeps independent device connected");
        rejects(()->ports.claim(PortClaims.Role.DEBUG,new PortClaims.Key("/usb/3",1,1,0)),"role cannot silently switch device");
        PortClaims requestsPorts=new PortClaims();UsbPermissions permissions=new UsbPermissions(requestsPorts);
        var groundPermission=permissions.request(PortClaims.Role.GROUND,key,8,230400);
        rejects(()->permissions.request(PortClaims.Role.DEBUG,key,8,230400),"permission waiting already reserves physical port");
        rejects(()->permissions.request(PortClaims.Role.GROUND,new PortClaims.Key("/usb/other",1,1,0),9,230400),"cannot overwrite pending same-role permission");
        var debugKey=new PortClaims.Key("/usb/debug",1,1,0);
        var debugPermission=permissions.request(PortClaims.Role.DEBUG,debugKey,9,115200);
        check(permissions.pending(groundPermission.lease().epoch()).equals(groundPermission),"permission survives Activity-independent coordinator lifetime");
        check(permissions.complete(debugPermission.lease().epoch(),debugKey,9,true).equals(debugPermission),"out-of-order debug grant stays with debug role and baud");
        check(permissions.complete(debugPermission.lease().epoch(),debugKey,9,true)==null,"duplicate grant consumed once");
        check(permissions.complete(groundPermission.lease().epoch(),key,999,true)==null,"device ID reuse/mismatch rejects grant");
        check(requestsPorts.current(debugPermission.lease()),"ground grant failure leaves debug alone");
        var deny=permissions.request(PortClaims.Role.GROUND,key,8,230400);
        check(permissions.complete(deny.lease().epoch(),key,8,false)==null&&requestsPorts.get(PortClaims.Role.GROUND)==null,"denied grant releases reservation");
        var unplug=permissions.request(PortClaims.Role.GROUND,key,8,230400);permissions.detached(key.deviceName());
        var replug=permissions.request(PortClaims.Role.GROUND,key,8,230400);
        check(permissions.complete(unplug.lease().epoch(),key,8,true)==null&&requestsPorts.current(replug.lease()),"late permission after unplug cannot authorize replacement");
        check(permissions.cancel(PortClaims.Role.GROUND)&&permissions.complete(replug.lease().epoch(),key,8,true)==null,"explicit disconnect cancels waiting permission");
        requestsPorts.invalidate(PortClaims.Role.DEBUG);check(!requestsPorts.current(debugPermission.lease()),"explicit disconnect immediately invalidates I/O lease");
        rejects(()->requestsPorts.claim(PortClaims.Role.GROUND,debugKey),"closing physical port remains reserved until close completes");
        requestsPorts.release(debugPermission.lease());check(requestsPorts.claim(PortClaims.Role.GROUND,debugKey)!=null,"port reusable after closing owner releases");
        CloseScope close=new CloseScope();int[] closed={0};close.own(()->closed[0]++);close.close();close.close();
        check(closed[0]==1,"close is idempotent");rejects(()->close.own(()->closed[0]++),"late-opened resource after cancellation is rejected");check(closed[0]==2,"late-opened resource is still closed");
        CloseScope broken=new CloseScope();broken.own(()->closed[0]++);broken.own(()->{throw new IOException("close failure");});
        rejects(broken::close,"resource close error reported");check(closed[0]==3,"one close failure does not leak earlier connection");
        CloseScope concurrentClose=new CloseScope();CountDownLatch enteredClose=new CountDownLatch(1),finishClose=new CountDownLatch(1),secondStarted=new CountDownLatch(1);
        concurrentClose.own(()->{enteredClose.countDown();try{if(!finishClose.await(5,TimeUnit.SECONDS))throw new IOException("test close timeout");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}});
        ExecutorService closingPool=Executors.newFixedThreadPool(2);
        try{
            Future<?> firstClose=closingPool.submit(()->{try{concurrentClose.close();}catch(IOException e){throw new UncheckedIOException(e);}});
            check(enteredClose.await(2,TimeUnit.SECONDS),"first close reached blocking resource");
            Future<?> secondClose=closingPool.submit(()->{secondStarted.countDown();try{concurrentClose.close();}catch(IOException e){throw new UncheckedIOException(e);}});
            check(secondStarted.await(2,TimeUnit.SECONDS),"concurrent close attempted");
            boolean waited=false;try{secondClose.get(100,TimeUnit.MILLISECONDS);}catch(TimeoutException expected){waited=true;}
            check(waited,"concurrent close cannot return before actual close finishes");finishClose.countDown();firstClose.get(2,TimeUnit.SECONDS);secondClose.get(2,TimeUnit.SECONDS);
        }finally{finishClose.countDown();closingPool.shutdownNow();}
        String incomplete=store.begin("Interrupted recorder","simulation",9999);store.finish("FAIL:overflow",false);
        check(store.metadata(incomplete).getProperty("complete").equals("false"),"interrupted recording closes without claiming completeness");
        CountDownLatch writing=new CountDownLatch(1),release=new CountDownLatch(1);
        ExecutorService pool=Executors.newFixedThreadPool(2);MemoryTarget stalled=new MemoryTarget();
        VerifiedExport.Target slow=new VerifiedExport.Target(){
            public OutputStream openWrite()throws IOException{writing.countDown();try{if(!release.await(5,TimeUnit.SECONDS))throw new IOException("test wait expired");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}return stalled.openWrite();}
            public InputStream openRead()throws IOException{return stalled.openRead();}public String description(){return "slow-generated-target";}
        };
        try{
            Future<?> export=pool.submit(()->{try{VerifiedExport.copy(store,id,slow,true);}catch(IOException e){throw new UncheckedIOException(e);}});
            check(writing.await(2,TimeUnit.SECONDS),"slow export started");
            Future<?> record=pool.submit(()->{try{String other=store.begin("Parallel recorder","simulation",999);store.append(Map.of("sample",1));store.finish("done");if(!store.list(false).contains(other))throw new AssertionError();}catch(IOException e){throw new UncheckedIOException(e);}});
            record.get(2,TimeUnit.SECONDS);check(true,"slow export does not block another recorder");
            rejects(()->store.rename(id,"during export"),"reserved export blocks same-session mutation");release.countDown();export.get(2,TimeUnit.SECONDS);
        }finally{release.countDown();pool.shutdownNow();}
        System.out.println("PASS: "+checks+" storage/export/layout assertions; all inputs generated; no user-file deletion.");
    }
}

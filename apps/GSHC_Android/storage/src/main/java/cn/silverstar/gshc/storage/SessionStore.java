package cn.silverstar.gshc.storage;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;

/** One synchronized owner. Raw JSONL is append-only; display names live separately. */
public final class SessionStore {
    public static final String CONTRACT_COMMIT = "c31c13cc0686a56a3184d4f207fd3816c5d39696";
    private final Path root;
    private String activeId;
    private FileOutputStream active;
    private final Set<String> reserved=new HashSet<>();
    private final Map<String,String> recycleVersions=new HashMap<>();
    public SessionStore(Path root) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        Files.createDirectories(this.root);
        Files.createDirectories(this.root.resolve("recycle"));
    }
    public synchronized String begin(String name, String mode, long monotonicNs) throws IOException {
        if (active != null) throw new IOException("已有正在记录的会话");
        String id = UUID.randomUUID().toString();
        Path dir = path(id); Files.createDirectory(dir);
        Properties props = new Properties();
        props.setProperty("session_id", id); props.setProperty("display_name", validName(name));
        props.setProperty("mode", mode); props.setProperty("started_utc", Instant.now().toString());
        props.setProperty("ended_utc", ""); props.setProperty("complete", "false");
        props.setProperty("log_format", "silverstar.gshc-jsonl"); props.setProperty("log_format_version", "1");
        writeMeta(dir, props);
        active = new FileOutputStream(dir.resolve("fc_session_" + id + ".jsonl").toFile()); activeId = id;
        Map<String,Object> rec = new LinkedHashMap<>();
        rec.put("ts", System.currentTimeMillis()/1000.0); rec.put("host_monotonic_ns", monotonicNs);
        rec.put("dir", "META"); rec.put("layer", "SESSION"); rec.put("kind", "SESSION_START");
        rec.put("log_format", "silverstar.gshc-jsonl"); rec.put("log_format_version", 1);
        rec.put("reason", mode); rec.put("session_id", id); rec.put("simulated", "simulation".equals(mode));
        rec.put("simulation_label", "simulation".equals(mode) ? "Android synthetic transport" : "");
        rec.put("app_version", "0.1.3-dev.1"); rec.put("silverstar_version", "0.1.3");
        rec.put("source_contract_tag", "v0.1.2"); rec.put("source_contract_commit", CONTRACT_COMMIT);
        rec.put("gsp_protocol", "GSP-MIN"); rec.put("air_protocol", "M0");
        rec.put("air_profile_id", null); rec.put("time_basis", "ts=Unix seconds; host_monotonic_ns=Android elapsedRealtimeNanos; device time remains in AIR");
        try { append(rec); } catch(IOException ex) { try { active.close(); } finally { active=null; activeId=null; } throw ex; }
        return id;
    }
    public synchronized void append(Map<String,Object> record) throws IOException {
        if (active == null) throw new IOException("无活动会话");
        active.write((Json.encode(record)+"\n").getBytes(StandardCharsets.UTF_8));
        active.flush();
    }
    public synchronized void finish(String reason) throws IOException {finish(reason,true);}
    public synchronized void finish(String reason,boolean complete) throws IOException {
        if (active == null) return;
        String id = activeId; IOException error = null;
        try { active.flush(); active.getFD().sync(); } catch(IOException ex) { error=ex; }
        try { active.close(); } catch(IOException ex) { if(error==null) error=ex; }
        active=null; activeId=null;
        if(error != null) throw error;
        Properties p = metadata(id); p.setProperty("complete", Boolean.toString(complete));
        p.setProperty("ended_utc", Instant.now().toString()); p.setProperty("end_reason", reason);
        writeMeta(path(id), p);
    }
    public synchronized boolean isActive(String id) { return id.equals(activeId); }
    public synchronized String importRaw(InputStream source,String name) throws IOException {
        return importRaw(source,name,"legacy-unversioned");
    }
    public synchronized String importRaw(InputStream source,String name,String formatVersion) throws IOException {
        if(!formatVersion.equals("1")&&!formatVersion.equals("legacy-unversioned"))throw new IOException("未支持的JSONL格式版本");
        String displayName=validName(name);
        String id=UUID.randomUUID().toString();Path dir=root.resolve(".incoming-"+id);Files.createDirectory(dir);
        Path part=dir.resolve("import.part"),raw=dir.resolve("fc_session_"+id+".jsonl");
        try(OutputStream out=Files.newOutputStream(part)){
            byte[] b=new byte[8192];int n;long size=0;
            while((n=source.read(b))!=-1){size+=n;if(size>1024L*1024*1024)throw new IOException("首版导入限制1GiB");out.write(b,0,n);}
        }
        Files.move(part,raw,StandardCopyOption.ATOMIC_MOVE);
        Properties p=new Properties();p.setProperty("session_id",id);p.setProperty("display_name",displayName);p.setProperty("mode","imported");
        p.setProperty("log_format","silverstar.gshc-jsonl");p.setProperty("log_format_version",formatVersion);
        p.setProperty("started_utc","");p.setProperty("ended_utc","");p.setProperty("complete","false");writeMeta(dir,p);
        Files.move(dir,path(id),StandardCopyOption.ATOMIC_MOVE);return id;
    }
    public synchronized String activeId() { return activeId; }
    public synchronized List<String> list(boolean recycled) throws IOException {
        Path parent = recycled ? root.resolve("recycle") : root;
        List<String> result = new ArrayList<>();
        try(DirectoryStream<Path> ds=Files.newDirectoryStream(parent)) {
            for(Path p:ds) if(Files.isDirectory(p, LinkOption.NOFOLLOW_LINKS) && p.getFileName().toString().matches("[0-9a-f-]{36}")) result.add(p.getFileName().toString());
        }
        Collections.sort(result); return result;
    }
    public synchronized Properties metadata(String id) throws IOException { return readMeta(path(id)); }
    public synchronized void rename(String id, String name) throws IOException {
        if (isActive(id)) throw new IOException("停止记录后可重命名");
        ensureUnreserved(id);
        Properties p=metadata(id); p.setProperty("display_name",validName(name)); writeMeta(path(id),p);
    }
    public synchronized Path rawFile(String id) throws IOException {
        String name=metadata(id).getProperty("raw_file","fc_session_"+id+".jsonl");
        if(!name.matches("[A-Za-z0-9_.-]+"))throw new IOException("非法原始文件路径");
        Path p=path(id).resolve(name);
        if(!Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS)) throw new IOException("会话原始文件不可用");
        return p;
    }
    public synchronized List<Path> files(String id) throws IOException {
        if(isActive(id)) throw new IOException("请先停止记录再导出，保证一致快照");
        List<Path> result=new ArrayList<>(Arrays.asList(rawFile(id),path(id).resolve("session.properties")));
        Path transfer=path(id).resolve("transfer.metadata");if(Files.exists(transfer,LinkOption.NOFOLLOW_LINKS))result.add(transfer);return result;
    }
    /** Register an already verified transfer without converting any source bytes or claiming decoder match. */
    public String importFlightLog(Path original,boolean simulated)throws IOException{
        if(!Files.isRegularFile(original,LinkOption.NOFOLLOW_LINKS))throw new IOException("下载文件不可用");
        String id=UUID.randomUUID().toString(),name=simulated?"mock-fixture.bin":"flight.sslog";Path staging=root.resolve(".incoming-"+id);Files.createDirectory(staging);
        Files.copy(original,staging.resolve(name));
        Path sidecar=original.resolveSibling(original.getFileName().toString().replaceFirst("\\.sslog$",".metadata"));
        if(!sidecar.equals(original)&&Files.isRegularFile(sidecar,LinkOption.NOFOLLOW_LINKS))Files.copy(sidecar,staging.resolve("transfer.metadata"));
        Properties p=new Properties();p.setProperty("session_id",id);p.setProperty("display_name",simulated?"TF模拟传输样例（非飞行日志）":"TF下载 "+original.getFileName());
        p.setProperty("mode",simulated?"mock-tf-download":"tf-download");p.setProperty("raw_file",name);p.setProperty("log_format",simulated?"synthetic-fixture":"SSLOG");p.setProperty("log_format_version",simulated?"1":"0.0");
        p.setProperty("started_utc","");p.setProperty("ended_utc","");p.setProperty("downloaded_utc",Instant.now().toString());p.setProperty("complete","false");p.setProperty("transfer_verified","true");p.setProperty("decoder_identity","unverified");
        writeMeta(staging,p);Files.move(staging,path(id),StandardCopyOption.ATOMIC_MOVE);return id;
    }
    /** Atomic logical deletion preserves recoverability if the app/process is interrupted. */
    public synchronized void recycle(String id, boolean explicitConfirmation) throws IOException {
        if(!explicitConfirmation) throw new IOException("需要明确确认");
        if(isActive(id)) throw new IOException("禁止删除正在记录的会话");
        ensureUnreserved(id);
        Files.move(path(id),root.resolve("recycle").resolve(id),StandardCopyOption.ATOMIC_MOVE);
        recycleVersions.put(id,UUID.randomUUID().toString());
    }
    /** Process-local version for an immutable recycled entry; changes on every recycle cycle. */
    public synchronized String recycledVersion(String id)throws IOException{
        path(id);Path entry=root.resolve("recycle").resolve(id);
        if(!Files.isDirectory(entry,LinkOption.NOFOLLOW_LINKS))throw new IOException("回收站目标已变化，请重新选择");
        return recycleVersions.computeIfAbsent(id,key->UUID.randomUUID().toString());
    }
    public synchronized void restore(String id) throws IOException {
        restore(id,recycledVersion(id));
    }
    public synchronized void restore(String id,String expectedVersion)throws IOException{
        ensureUnreserved(id);
        if(!Objects.equals(expectedVersion,recycledVersion(id)))throw new IOException("回收站目标版本已变化，请重新选择");
        path(id); Files.move(root.resolve("recycle").resolve(id),path(id),StandardCopyOption.ATOMIC_MOVE);
        recycleVersions.remove(id);
    }
    /** Reserve just one closed session; slow export must not block another session's recorder. */
    synchronized SessionLease reserve(String id)throws IOException {
        files(id);ensureUnreserved(id);reserved.add(id);return new SessionLease(id);
    }
    private void ensureUnreserved(String id)throws IOException{if(reserved.contains(id))throw new IOException("此会话正在导出，请稍后重试");}
    final class SessionLease implements AutoCloseable {
        private final String id;private boolean closed;
        SessionLease(String id){this.id=id;}
        List<Path> files()throws IOException{synchronized(SessionStore.this){if(closed)throw new IOException("导出事务已关闭");return SessionStore.this.files(id);}}
        void recycleConfirmed()throws IOException{
            synchronized(SessionStore.this){
                if(closed||!reserved.contains(id)||isActive(id))throw new IOException("导出事务已失效");
                Files.move(path(id),root.resolve("recycle").resolve(id),StandardCopyOption.ATOMIC_MOVE);
                recycleVersions.put(id,UUID.randomUUID().toString());
            }
        }
        @Override public void close(){synchronized(SessionStore.this){if(!closed){reserved.remove(id);closed=true;}}}
    }
    private Path path(String id) throws IOException {
        if(id==null || !id.matches("[0-9a-f-]{36}")) throw new IOException("非法会话标识");
        Path p=root.resolve(id);
        if(Files.isSymbolicLink(p)) throw new IOException("不支持链接会话目录");
        return p;
    }
    private static String validName(String name) throws IOException {
        if(name==null || name.trim().isEmpty() || name.length()>100 || name.chars().anyMatch(c->c<32)) throw new IOException("名称应为 1–100 个可见字符");
        return name.trim();
    }
    private static Properties readMeta(Path dir) throws IOException {
        Properties p=new Properties(); try(Reader r=Files.newBufferedReader(dir.resolve("session.properties"),StandardCharsets.UTF_8)){p.load(r);} return p;
    }
    private static void writeMeta(Path dir, Properties p) throws IOException {
        Path tmp=dir.resolve("session.properties.tmp");
        try(Writer w=Files.newBufferedWriter(tmp,StandardCharsets.UTF_8)){p.store(w,"SilverStar session metadata; raw JSONL unchanged");}
        Files.move(tmp,dir.resolve("session.properties"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
    }
}

package cn.silverstar.gshc.storage;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.time.Instant;
import java.util.*;
import java.util.zip.*;

/** A target may be a SAF document. Closing output is mandatory before opening input. */
public final class VerifiedExport {
    public interface Target {
        OutputStream openWrite() throws IOException;
        InputStream openRead() throws IOException;
        String description();
    }
    public static final class Receipt {
        public final String sessionId, destination;
        public final boolean verified;
        private final Map<String,Stamp> entries;
        private final Target target;
        private final byte[] manifest;
        private final Stamp archive;
        private Receipt(String id, Target t, Map<String,Stamp> entries, byte[] manifest, Stamp archive, boolean verified) {
            this.sessionId=id; this.target=t; this.destination=t.description();
            this.entries=entries; this.manifest=manifest; this.archive=archive; this.verified=verified;
        }
    }
    private static final class Stamp {
        final long size; final String hash;
        Stamp(long size,String hash){this.size=size;this.hash=hash;}
        boolean same(Stamp s){return size==s.size && hash.equals(s.hash);}
    }
    private static final class MeasuredOutput extends FilterOutputStream {
        final MessageDigest hash=newDigest();long size;
        MeasuredOutput(OutputStream out){super(out);}
        @Override public void write(int b)throws IOException{out.write(b);hash.update((byte)b);size++;}
        @Override public void write(byte[] b,int off,int len)throws IOException{out.write(b,off,len);hash.update(b,off,len);size+=len;}
        Stamp stamp(){return new Stamp(size,hex(hash.digest()));}
    }
    private VerifiedExport() {}
    public static Receipt copy(SessionStore store,String id,Target target,boolean requireVerification) throws IOException {
        try(SessionStore.SessionLease lease=store.reserve(id)) {
            List<Path> files=lease.files();
            Map<String,Stamp> expected=inventory(id,files);
            byte[] manifest=manifest(store,id,expected);
            MeasuredOutput measured=new MeasuredOutput(target.openWrite());
            try(ZipOutputStream zip=new ZipOutputStream(measured)) {
                zip.putNextEntry(new ZipEntry("manifest.json"));zip.write(manifest);zip.closeEntry();
                for(Path file:files){
                    zip.putNextEntry(new ZipEntry(entry(id,file)));
                    try(InputStream in=Files.newInputStream(file)){copyBytes(in,zip);}
                    zip.closeEntry();
                }
            }
            Stamp archive=measured.stamp();
            // Source fingerprints also protect copy consistency and later cut confirmation.
            compare(expected,inventory(id,files));
            boolean verified=false;
            try { verify(target,expected,manifest,archive);verified=true; }
            catch(IOException e){ if(requireVerification) throw new IOException("目标未通过回读校验，源会话完整保留",e); }
            return new Receipt(id,target,expected,manifest,archive,verified);
        }
    }
    public static void confirmCut(SessionStore store,Receipt receipt,boolean confirmed) throws IOException {
        if(!confirmed) throw new IOException("未确认剪切；源会话保留");
        if(!receipt.verified) throw new IOException("目标无法回读校验，只能复制");
        try(SessionStore.SessionLease lease=store.reserve(receipt.sessionId)){
            compare(receipt.entries,inventory(receipt.sessionId,store.files(receipt.sessionId)));
            // Recheck at commit, after human delay: revoked access/corruption must retain source.
            verify(receipt.target,receipt.entries,receipt.manifest,receipt.archive);
            lease.recycleConfirmed();
        }
    }
    private static Map<String,Stamp> inventory(String id,List<Path> files) throws IOException {
        Map<String,Stamp> result=new LinkedHashMap<>();
        for(Path f:files){
            if(!Files.isRegularFile(f,LinkOption.NOFOLLOW_LINKS)) throw new IOException("源文件不可用");
            try(InputStream in=Files.newInputStream(f)){result.put(entry(id,f),digest(in,Long.MAX_VALUE));}
        }
        return result;
    }
    private static String entry(String id,Path file){return "sessions/"+id+"/"+file.getFileName();}
    private static byte[] manifest(SessionStore store,String id,Map<String,Stamp> entries) throws IOException {
        Map<String,Object> m=new LinkedHashMap<>();
        m.put("format","silverstar.session-export");m.put("schema_version",1);
        m.put("session_id",id);m.put("created_at",Instant.now().toString());
        m.put("source_app",Map.of("name","GSHC-Android","version","0.1.3-dev.1"));
        Properties metadata=store.metadata(id);boolean tf=metadata.getProperty("mode","").endsWith("tf-download");boolean imported=tf||"imported".equals(metadata.getProperty("mode"));
        Map<String,Object> protocols=new LinkedHashMap<>();protocols.put("gsp",imported?null:"GSP-MIN");protocols.put("air",imported?null:"M0");protocols.put("air_profile_id",null);
        protocols.put("source_contract_tag",imported?null:"v0.1.2");protocols.put("source_contract_commit",imported?null:SessionStore.CONTRACT_COMMIT);
        protocols.put("session_export",1);m.put("protocols",protocols);
        if(tf){protocols.put("log_file_service",1);protocols.put("sslog","SSLOG".equals(metadata.getProperty("log_format"))?"0.0":null);protocols.put("file_service_contract_commit","cb944b7c5a844da2f277494662801f2179a268ad");}
        String logVersion=metadata.getProperty("log_format_version","legacy-unversioned");
        List<Object> list=new ArrayList<>();
        for(Map.Entry<String,Stamp> e:entries.entrySet()){
            boolean raw=e.getKey().endsWith(".jsonl");boolean flight=e.getKey().endsWith("/flight.sslog");boolean fixture=e.getKey().endsWith("/mock-fixture.bin");
            list.add(Map.of("path",e.getKey(),"size_bytes",e.getValue().size,"sha256",e.getValue().hash,
                "role",raw?"session_log":flight?"flight_log":"attachment","format",raw?"silverstar.gshc-jsonl":flight?"SSLOG":fixture?"synthetic-fixture":"java-properties",
                "format_version",raw?logVersion:flight?"0.0":"1"));
        }
        m.put("files",list);
        return (Json.encode(m)+"\n").getBytes(StandardCharsets.UTF_8);
    }
    private static void verify(Target target,Map<String,Stamp> expected,byte[] manifest,Stamp archive) throws IOException {
        // Covers the central directory/EOCD too; ZipInputStream alone accepts a truncated archive tail.
        try(InputStream in=target.openRead()){if(!digest(in,archive.size).same(archive))throw new IOException("ZIP整体回读校验失败");}
        Set<String> seen=new HashSet<>();boolean found=false;
        try(ZipInputStream zip=new ZipInputStream(target.openRead())) {
            ZipEntry e;
            while((e=zip.getNextEntry())!=null){
                String name=e.getName();
                if(!seen.add(name.toLowerCase(Locale.ROOT)) || e.isDirectory())throw new IOException("重复或目录 ZIP 项");
                if(name.equals("manifest.json")) {
                    Stamp a=digest(zip,manifest.length);Stamp b=digest(new ByteArrayInputStream(manifest),manifest.length);
                    if(!a.same(b))throw new IOException("manifest 校验失败");found=true;
                } else {
                    Stamp want=expected.get(name);
                    if(want==null || !digest(zip,want.size).same(want))throw new IOException("文件回读校验失败: "+name);
                }
                zip.closeEntry();
            }
        }
        if(!found || seen.size()!=expected.size()+1)throw new IOException("导出包缺少文件");
    }
    private static void compare(Map<String,Stamp> a,Map<String,Stamp> b)throws IOException {
        if(!a.keySet().equals(b.keySet()))throw new IOException("源文件集合发生变化");
        for(String key:a.keySet())if(!a.get(key).same(b.get(key)))throw new IOException("源文件发生变化，保留源会话");
    }
    private static Stamp digest(InputStream in,long max)throws IOException {
        MessageDigest digest=newDigest();
        long n=0;byte[] b=new byte[8192];int got;
        while((got=in.read(b))!=-1){
            if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("导出已中断");
            if(got>max-n)throw new IOException("回读长度超出清单");
            n+=got;digest.update(b,0,got);
        }
        return new Stamp(n,hex(digest.digest()));
    }
    private static MessageDigest newDigest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static String hex(byte[] bytes){StringBuilder hex=new StringBuilder();for(byte v:bytes)hex.append(String.format(Locale.ROOT,"%02x",v&255));return hex.toString();}
    private static void copyBytes(InputStream in,OutputStream out)throws IOException {
        byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("导出中断");out.write(b,0,n);}
    }
}

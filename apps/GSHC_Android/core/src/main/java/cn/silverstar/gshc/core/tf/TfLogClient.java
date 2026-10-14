package cn.silverstar.gshc.core.tf;

import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.CRC32;

/** Shared silverstar.log-file-service v1. Original SSLOG bytes; no device-delete API. */
public final class TfLogClient {
    public static final int VERSION=1, CHUNK_BYTES=64, MAX_LIST_ITEMS=1000;
    public interface Source {
        Capabilities caps() throws IOException;
        ListPage list(long cursor) throws IOException;
        Metadata meta(int fileId) throws IOException;
        Chunk read(int fileId,String token,long offset) throws IOException;
        void cancel() throws IOException;
    }
    public record Capabilities(int fileServiceVersion,boolean supported,int maxChunk,boolean deleteSupported,
                               boolean telemetryBulk,String deviceId,String bootId) {
        /** Local client policy only; there is no resume_supported field on the wire. */
        public boolean resumeAllowed(){return false;}
        public String resumeUnavailableReason(){return "Reliable device/boot identity is unavailable; start a new download at offset zero.";}
    }
    public record ListedFile(int fileId,long size,boolean closed) {
        public ListedFile { fileIdCheck(fileId);unsigned(size,"size"); }
    }
    public record ListPage(ListedFile file,long nextCursor,boolean end) {
        public ListPage { unsigned(nextCursor,"cursor");if(end?(file!=null||nextCursor!=0):file==null)throw new IllegalArgumentException("Invalid LIST page"); }
    }
    public record Metadata(int fileId,String token,long size,long crc32,String format,String formatVersion,boolean closed) {
        public Metadata { fileIdCheck(fileId);unsigned(size,"size");unsigned(crc32,"CRC32");if(!tokenFor(crc32,size).equals(token))throw new IllegalArgumentException("Invalid v1 token/CRC/size"); }
    }
    public record Chunk(int fileId,String token,long offset,byte[] bytes,long crc32) {
        public Chunk { bytes=bytes.clone(); }
        @Override public byte[] bytes(){return bytes.clone();}
    }
    public record Result(Metadata entry,Path localFile,boolean resumed,long downloadedBytes,String localSha256) {}
    static void fileIdCheck(int id){if(id<1||id>999999)throw new IllegalArgumentException("Invalid file ID");}
    static void unsigned(long value,String label){if(value<0||value>0xffffffffL)throw new IllegalArgumentException("Invalid uint32 "+label);}
    public static String tokenFor(long crc,long size){unsigned(crc,"CRC32");unsigned(size,"size");return String.format(Locale.ROOT,"1-%08X-%08X",crc,size);}
    public static void validateCapabilities(Capabilities c)throws IOException{
        if(c==null||c.fileServiceVersion()!=VERSION||!c.supported()||c.maxChunk()!=CHUNK_BYTES||c.telemetryBulk()
                ||!"unknown".equals(c.deviceId())||!"unknown".equals(c.bootId()))throw new IOException("Unsupported LOGFILE service capabilities/version");
    }
    public List<Result> downloadAll(Source source,Path target)throws IOException{
        validateCapabilities(source.caps());List<ListedFile> files=new ArrayList<>();Set<Long> cursors=new HashSet<>();Set<Integer> ids=new HashSet<>();long cursor=0;
        for(int i=0;i<=MAX_LIST_ITEMS;i++){
            if(!cursors.add(cursor))throw new IOException("Repeated LIST cursor");ListPage page=source.list(cursor);if(page.end())break;
            ListedFile file=page.file();if(!file.closed())throw new IOException("LIST contains active file");if(!ids.add(file.fileId()))throw new IOException("Duplicate file ID");
            if(i==MAX_LIST_ITEMS)throw new IOException("TF directory exceeds client bound");files.add(file);cursor=page.nextCursor();
        }
        List<Result> results=new ArrayList<>();for(ListedFile file:files)results.add(download(source,file.fileId(),file.size(),target));return List.copyOf(results);
    }
    public Result download(Source source,int fileId,Path target)throws IOException{return download(source,fileId,null,target);}
    private Result download(Source source,int fileId,Long listedSize,Path target)throws IOException{
        // No token survives as authority across calls: negotiate and obtain fresh META each time.
        validateCapabilities(source.caps());Metadata metadata=source.meta(fileId);validateMetadata(metadata,fileId);
        if(listedSize!=null&&listedSize.longValue()!=metadata.size())throw new IOException("LIST/META size changed; enumerate again");
        Path directory=target.toAbsolutePath().normalize();Files.createDirectories(directory);
        // Integration f2ce541: unknown identity forbids reusing even matching tokens/prefixes.
        // Each attempt owns a new path. Old partial and complete downloads remain untouched.
        Path part=Files.createTempFile(directory,String.format(Locale.ROOT,"%06d-%s-",fileId,metadata.token()),".part");
        String stem=part.getFileName().toString().replaceFirst("\\.part$","");
        Path published=directory.resolve(stem+".sslog"),sidecar=directory.resolve(stem+".metadata");
        long offset=0;
        try(RandomAccessFile output=new RandomAccessFile(part.toFile(),"rw")){
            output.seek(offset);
            while(offset<metadata.size()){
                byte[] payload=verifiedRead(source,metadata,offset);
                output.write(payload);output.getFD().sync();offset+=payload.length;
            }
            output.getFD().sync();
        }
        verifyLocal(part,metadata);String hash=sha256(part);
        // Atomic rename is required; unsupported filesystems leave the partial distinguishable.
        Files.move(part,published,StandardCopyOption.ATOMIC_MOVE);saveMetadata(sidecar,metadata,hash);
        return new Result(metadata,published,false,offset,hash);
    }
    private static void validateMetadata(Metadata m,int id)throws IOException{
        if(m==null||m.fileId()!=id||!m.closed()||!"SSLOG".equals(m.format())||!"0.0".equals(m.formatVersion()))throw new IOException("Invalid/active/unsupported SSLOG metadata");
    }
    private static byte[] verifiedRead(Source source,Metadata m,long offset)throws IOException{
        Chunk c=source.read(m.fileId(),m.token(),offset);byte[] bytes=c.bytes();
        int expected=(int)Math.min(CHUNK_BYTES,m.size()-offset);
        if(c.fileId()!=m.fileId()||!m.token().equals(c.token())||c.offset()!=offset)throw new IOException("READ file/token/offset mismatch");
        if(bytes.length>expected||(expected>0&&bytes.length==0))throw new IOException("READ length mismatch");
        if(crc32(bytes)!=c.crc32())throw new IOException("READ CRC32 mismatch");return bytes;
    }
    private static void verifyLocal(Path path,Metadata m)throws IOException{
        if(Files.size(path)!=m.size())throw new IOException("Final size mismatch");CRC32 crc=new CRC32();byte[] buffer=new byte[8192];
        try(InputStream in=Files.newInputStream(path)){int n;while((n=in.read(buffer))!=-1)crc.update(buffer,0,n);}
        if(crc.getValue()!=m.crc32())throw new IOException("Final whole-file CRC32 mismatch; local data preserved");
    }
    private static void saveMetadata(Path path,Metadata m,String hash)throws IOException{
        Properties p=new Properties();p.setProperty("file_service_version","1");p.setProperty("file_id",Integer.toString(m.fileId()));p.setProperty("token",m.token());p.setProperty("size",Long.toString(m.size()));p.setProperty("crc32",String.format(Locale.ROOT,"%08X",m.crc32()));
        p.setProperty("format","SSLOG");p.setProperty("format_version","0.0");p.setProperty("closed","true");p.setProperty("device_id","unknown");p.setProperty("boot_id","unknown");p.setProperty("local_sha256",hash);p.setProperty("local_resume_policy","disabled_unknown_identity; new_attempt_offset_zero");
        p.setProperty("required_decoder_package_version","1.2");p.setProperty("decoder_identity","unverified; exact decoder and embedded Descriptor required by FLP");
        Path tmp=path.resolveSibling(path.getFileName()+".tmp");try(FileOutputStream out=new FileOutputStream(tmp.toFile())){p.store(out,"Shared LOGFILE v1; original bytes; no source deletion");out.getFD().sync();}
        Files.move(tmp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
    }
    public static long crc32(byte[] data){CRC32 crc=new CRC32();crc.update(data);return crc.getValue();}
    private static MessageDigest digest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}}
    public static String sha256(byte[] bytes){return hex(digest().digest(bytes));}
    public static String sha256(Path path)throws IOException{MessageDigest digest=digest();byte[] buffer=new byte[8192];try(InputStream in=Files.newInputStream(path)){int n;while((n=in.read(buffer))!=-1)digest.update(buffer,0,n);}return hex(digest.digest());}
    private static String hex(byte[] bytes){StringBuilder b=new StringBuilder();for(byte value:bytes)b.append(String.format(Locale.ROOT,"%02x",value&255));return b.toString();}
}

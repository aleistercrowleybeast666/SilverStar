package cn.silverstar.gshc.storage;

import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Sequential-only provider copy: no seek or atomic rename is required, and source is never removed. */
public final class VerifiedFileCopy {
    public record Result(long size,String sha256,String destination) {}
    private VerifiedFileCopy() {}
    public static Result copy(Path source,VerifiedExport.Target target)throws IOException{
        MessageDigest sourceHash=digest();long size=0;
        try(InputStream in=Files.newInputStream(source);OutputStream out=target.openWrite()){
            byte[] buffer=new byte[8192];int n;
            while((n=in.read(buffer))!=-1){interrupted();out.write(buffer,0,n);sourceHash.update(buffer,0,n);size+=n;}
        }
        byte[] expected=sourceHash.digest();MessageDigest targetHash=digest();long read=0;
        try(InputStream in=target.openRead()){
            byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){interrupted();read+=n;if(read>size)throw new IOException("Destination larger than verified source");targetHash.update(buffer,0,n);}
        }
        if(read!=size||!Arrays.equals(expected,targetHash.digest()))throw new IOException("Destination readback verification failed; internal source retained");
        StringBuilder hex=new StringBuilder();for(byte b:expected)hex.append(String.format(Locale.ROOT,"%02x",b&255));
        return new Result(size,hex.toString(),target.description());
    }
    private static MessageDigest digest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static void interrupted()throws InterruptedIOException{if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Copy interrupted; internal source retained");}
}

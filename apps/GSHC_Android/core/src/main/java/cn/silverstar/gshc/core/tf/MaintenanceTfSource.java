package cn.silverstar.gshc.core.tf;

import java.io.IOException;
import java.util.*;

/** Shared maintenance-console ASCII v1 with f2ce541 read-only policy; no USB ownership, AIR binding or DELETE API. */
public final class MaintenanceTfSource implements TfLogClient.Source {
    public static final int MAX_REQUEST_BYTES=191,MAX_RESPONSE_BYTES=511;
    public static final long TIMEOUT_MS=30000;
    @FunctionalInterface public interface LineTransport {
        /** Return one complete ASCII CRLF line, within timeoutMillis; never silently retry a write. */
        String exchange(String request,long timeoutMillis)throws IOException;
    }
    private record Reply(String status,String operation,Map<String,String> fields) {}
    private final LineTransport transport;private boolean negotiated;private TfLogClient.Metadata current;
    private volatile boolean cancelRequested;
    public MaintenanceTfSource(LineTransport transport){this.transport=Objects.requireNonNull(transport);}
    /** Transport owner must call on disconnect/reconnect/reboot before allowing further commands. */
    public synchronized void transportReset(){invalidate();cancelRequested=false;}
    @Override public synchronized TfLogClient.Capabilities caps()throws IOException{
        invalidate();cancelRequested=false;
        try{Reply r=exchange("LOGFILE CAPS",TIMEOUT_MS);expect(r,"OK","CAPS");
            TfLogClient.Capabilities c=new TfLogClient.Capabilities(integer(r,"file_service_version",0,0xffffffffL),flag(r,"supported"),integer(r,"max_chunk",0,511),flag(r,"delete_supported"),flag(r,"telemetry_bulk"),required(r,"device_id"),required(r,"boot_id"));
            TfLogClient.validateCapabilities(c);negotiated=true;return c;
        }catch(IllegalArgumentException ex){throw failure(ex);}catch(IOException ex){invalidate();throw ex;}
    }
    @Override public synchronized TfLogClient.ListPage list(long cursor)throws IOException{
        try{requireCaps();TfLogClient.unsigned(cursor,"cursor");Reply r=submit("LIST","LOGFILE LIST "+cursor);boolean end=flag(r,"end");long next=number(r,"next_cursor",0,0xffffffffL);
            if(end)return new TfLogClient.ListPage(null,next,true);
            return new TfLogClient.ListPage(new TfLogClient.ListedFile(integer(r,"file_id",1,999999),number(r,"size",0,0xffffffffL),flag(r,"closed")),next,false);
        }catch(IllegalArgumentException ex){throw failure(ex);}catch(IOException ex){invalidate();throw ex;}
    }
    @Override public synchronized TfLogClient.Metadata meta(int fileId)throws IOException{
        try{requireCaps();TfLogClient.fileIdCheck(fileId);Reply r=submit("META","LOGFILE META "+fileId);int actual=integer(r,"file_id",1,999999);if(actual!=fileId)throw new IOException("META file ID mismatch");
            TfLogClient.Metadata m=new TfLogClient.Metadata(actual,required(r,"token"),number(r,"size",0,0xffffffffL),crc(r,"crc32"),required(r,"format"),required(r,"format_version"),flag(r,"closed"));
            if(!m.closed()||!"SSLOG".equals(m.format())||!"0.0".equals(m.formatVersion()))throw new IOException("META active/unsupported format");current=m;return m;
        }catch(IllegalArgumentException ex){throw failure(ex);}catch(IOException ex){invalidate();throw ex;}
    }
    @Override public synchronized TfLogClient.Chunk read(int fileId,String token,long offset)throws IOException{
        try{requireCaps();if(current==null||fileId!=current.fileId()||!current.token().equals(token))throw new IOException("Fresh META required before READ");
            if(offset<0||offset>current.size())throw new IOException("READ offset outside META size");Reply r=submit("READ",readRequest(fileId,token,offset).trim());
            int actual=integer(r,"file_id",1,999999);String returnedToken=required(r,"token");long actualOffset=number(r,"offset",0,0xffffffffL);int length=integer(r,"length",0,64);
            if(actual!=fileId||!returnedToken.equals(token)||actualOffset!=offset)throw new IOException("READ identity/offset mismatch");
            String data=required(r,"data");byte[] bytes=decodeData(data,length);long crc=crc(r,"crc32");
            if(length>current.size()-offset||(offset<current.size()&&length==0)||TfLogClient.crc32(bytes)!=crc)throw new IOException("READ length/CRC mismatch");
            return new TfLogClient.Chunk(actual,returnedToken,actualOffset,bytes,crc);
        }catch(IllegalArgumentException ex){throw failure(ex);}catch(IOException ex){invalidate();throw ex;}
    }
    public static String readRequest(int fileId,String token,long offset){TfLogClient.fileIdCheck(fileId);TfLogClient.unsigned(offset,"offset");if(token==null||!token.matches("1-[0-9A-F]{8}-[0-9A-F]{8}"))throw new IllegalArgumentException("Invalid v1 token");return "LOGFILE READ "+fileId+" "+token+" "+offset+"\r\n";}
    /** Also wakes the polling loop between transport calls; each exchange remains timeout bounded. */
    @Override public void cancel()throws IOException{cancelRequested=true;synchronized(this){if(cancelRequested)cancelWire();}}
    private void cancelWire()throws IOException{try{Reply r=exchange("LOGFILE CANCEL",TIMEOUT_MS);expect(r,"OK","CANCEL");if(!flag(r,"cancelled"))throw new IOException("CANCEL not acknowledged");}finally{cancelRequested=false;invalidate();}}
    private Reply submit(String operation,String request)throws IOException{
        long deadline=System.nanoTime()+TIMEOUT_MS*1000000L;
        if(cancelRequested){cancelWire();throw new IOException("LOGFILE cancelled");}
        Reply initial=exchange(request,TIMEOUT_MS);expect(initial,"PENDING",operation);long id=number(initial,"request_id",1,0xffffffffL);
        for(int polls=0;polls<4096;polls++){
            if(cancelRequested){cancelWire();throw new IOException("LOGFILE cancelled");}
            long remaining=(deadline-System.nanoTime())/1000000L;if(remaining<=0)throw new IOException("LOGFILE local timeout; CAPS+META required");
            Reply response=exchange("LOGFILE POLL "+id,remaining);
            if(!operation.equals(response.operation())||number(response,"request_id",1,0xffffffffL)!=id)throw new IOException("POLL operation/request_id mismatch");
            if("OK".equals(response.status()))return response;
            if(!"PENDING".equals(response.status()))throw new IOException("LOGFILE "+operation+" failed: "+response.fields().get("code"));
            try{Thread.sleep(10);}catch(InterruptedException ex){Thread.currentThread().interrupt();throw new IOException("LOGFILE interrupted; CAPS+META required",ex);}
        }
        throw new IOException("LOGFILE polling bound exceeded");
    }
    private Reply exchange(String request,long timeout)throws IOException{
        String wire=request+"\r\n";ascii(wire,MAX_REQUEST_BYTES);String line=transport.exchange(wire,timeout);ascii(line,MAX_RESPONSE_BYTES);
        if(!line.endsWith("\r\n"))throw new IOException("Response must end CRLF");String body=line.substring(0,line.length()-2);
        if(body.indexOf('\r')>=0||body.indexOf('\n')>=0)throw new IOException("Multiple/embedded response lines");
        String[] parts=body.split(" ",-1);if(parts.length<3||!"LOGFILE".equals(parts[1])||!(parts[0].equals("OK")||parts[0].equals("PENDING")||parts[0].equals("ERR")))throw new IOException("Unsupported firmware or malformed LOGFILE response");
        Map<String,String> fields=new HashMap<>();for(int i=3;i<parts.length;i++){int equals=parts[i].indexOf('=');if(equals<=0||equals==parts[i].length()-1||fields.put(parts[i].substring(0,equals),parts[i].substring(equals+1))!=null)throw new IOException("Malformed/duplicate response field");}
        return new Reply(parts[0],parts[2],fields);
    }
    private static void ascii(String text,int maximum)throws IOException{if(text==null||text.length()>maximum)throw new IOException("ASCII line length bound");for(int i=0;i<text.length();i++)if(text.charAt(i)>127||text.charAt(i)<32&&text.charAt(i)!='\r'&&text.charAt(i)!='\n')throw new IOException("Non-ASCII/control character");}
    private static void expect(Reply r,String status,String op)throws IOException{if(!status.equals(r.status())||!op.equals(r.operation()))throw new IOException("Unexpected LOGFILE status/operation; unsupported or rejected: "+r.status()+"/"+r.operation());}
    private static String required(Reply r,String key)throws IOException{String value=r.fields().get(key);if(value==null)throw new IOException("Missing LOGFILE field "+key);return value;}
    private static long number(Reply r,String key,long min,long max)throws IOException{String value=required(r,key);if(!value.matches("[0-9]+"))throw new IOException("Invalid unsigned decimal "+key);try{long n=Long.parseLong(value);if(n<min||n>max)throw new NumberFormatException();return n;}catch(NumberFormatException ex){throw new IOException("Out of range "+key,ex);}}
    private static int integer(Reply r,String key,long min,long max)throws IOException{long value=number(r,key,min,max);if(value>Integer.MAX_VALUE)throw new IOException("Integer out of range "+key);return(int)value;}
    private static boolean flag(Reply r,String key)throws IOException{return number(r,key,0,1)==1;}
    private static long crc(Reply r,String key)throws IOException{String value=required(r,key);if(!value.matches("[0-9A-F]{8}"))throw new IOException("CRC must be eight uppercase hex digits");return Long.parseLong(value,16);}
    private static byte[] decodeData(String data,int length)throws IOException{if(length==0){if(!data.equals("-"))throw new IOException("Empty READ requires dash");return new byte[0];}if(data.length()!=length*2||!data.matches("[0-9A-F]+"))throw new IOException("READ data hex/length mismatch");byte[] bytes=new byte[length];for(int i=0;i<length;i++)bytes[i]=(byte)Integer.parseInt(data.substring(i*2,i*2+2),16);return bytes;}
    private void requireCaps()throws IOException{if(!negotiated)throw new IOException("Fresh CAPS required");}
    private void invalidate(){negotiated=false;current=null;}
    private IOException failure(IllegalArgumentException ex){invalidate();return new IOException("Invalid LOGFILE response/argument",ex);}
}

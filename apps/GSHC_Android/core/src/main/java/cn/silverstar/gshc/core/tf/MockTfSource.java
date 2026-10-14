package cn.silverstar.gshc.core.tf;

import java.io.IOException;
import java.util.*;

/** Explicit synthetic LOGFILE v1 source; not a hardware driver or valid SSLOG generator. */
public final class MockTfSource implements TfLogClient.Source {
    private byte[] data;private final TfLogClient.Metadata metadata;private boolean negotiated,metaValid;
    public int reads,capsCalls,metaCalls;public long failAtOffset=Long.MAX_VALUE;public boolean corruptCrc,advertisedDeleteSupported;public final List<Long> requestedOffsets=new ArrayList<>();
    public MockTfSource(byte[] data){this.data=data.clone();long crc=TfLogClient.crc32(data);metadata=new TfLogClient.Metadata(1,TfLogClient.tokenFor(crc,data.length),data.length,crc,"SSLOG","0.0",true);}
    /** Fault injection deliberately preserves advertised CRC/token to test whole-file CRC failure without reusing older attempts. */
    public void replaceBytesKeepingMetadata(byte[] replacement){if(replacement.length!=data.length)throw new IllegalArgumentException("Length must match");data=replacement.clone();negotiated=false;metaValid=false;}
    @Override public TfLogClient.Capabilities caps(){capsCalls++;negotiated=true;metaValid=false;return new TfLogClient.Capabilities(1,true,64,advertisedDeleteSupported,false,"unknown","unknown");}
    @Override public TfLogClient.ListPage list(long cursor)throws IOException{if(!negotiated)throw new IOException("CAPS required");return cursor==0?new TfLogClient.ListPage(new TfLogClient.ListedFile(1,data.length,true),1,false):new TfLogClient.ListPage(null,0,true);}
    @Override public TfLogClient.Metadata meta(int fileId)throws IOException{if(!negotiated||fileId!=1)throw new IOException("Fresh CAPS/file ID required");metaCalls++;metaValid=true;return metadata;}
    @Override public TfLogClient.Chunk read(int fileId,String token,long offset)throws IOException{
        if(!metaValid||fileId!=1||!metadata.token().equals(token))throw new IOException("Fresh META required");
        requestedOffsets.add(offset);
        if(offset>=failAtOffset){negotiated=false;metaValid=false;throw new IOException("Injected disconnection");}
        if(offset<0||offset>data.length)throw new IOException("Invalid mock offset");reads++;byte[] bytes=Arrays.copyOfRange(data,(int)offset,(int)Math.min(data.length,offset+64));
        return new TfLogClient.Chunk(1,token,offset,bytes,TfLogClient.crc32(bytes)^(corruptCrc?1:0));
    }
    @Override public void cancel(){negotiated=false;metaValid=false;}
}

package cn.silverstar.gshc.storage;

import java.io.*;
import java.util.*;

/** A late-opened resource is closed immediately after cancellation instead of being published. */
public final class CloseScope implements Closeable {
    private final List<Closeable> resources=new ArrayList<>();
    private boolean closed;
    public synchronized <T extends Closeable> T own(T resource)throws IOException{
        if(closed){resource.close();throw new IOException("Connection closed while opening");}
        resources.add(resource);return resource;
    }
    public synchronized boolean closed(){return closed;}
    /** Concurrent callers return only after the owning close finishes. Call on an I/O worker. */
    @Override public synchronized void close()throws IOException{
        if(closed)return;closed=true;
        List<Closeable> closing=new ArrayList<>(resources);resources.clear();
        IOException error=null;
        for(int i=closing.size()-1;i>=0;i--){try{closing.get(i).close();}catch(IOException e){if(error==null)error=e;else error.addSuppressed(e);}}
        if(error!=null)throw error;
    }
}

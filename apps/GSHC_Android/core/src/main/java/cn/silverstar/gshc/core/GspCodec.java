package cn.silverstar.gshc.core;

import java.util.*;

/** GSP-MIN from frozen SilverStar v0.1.2; no I/O or device transmit API. */
public final class GspCodec {
    private GspCodec() {}
    public static final int MAX_PAYLOAD = 64;
    public record Frame(int type, byte[] payload, byte[] raw) {
        public Frame { payload = payload.clone(); raw = raw.clone(); }
        @Override public byte[] payload() { return payload.clone(); }
        @Override public byte[] raw() { return raw.clone(); }
    }
    public record Envelope(byte[] air, String backend, boolean metricsSupported, Integer rssiDbm, Double snrDb) {
        public Envelope { air = air.clone(); }
        @Override public byte[] air() { return air.clone(); }
    }
    public record Diagnostics(long frames, long crcErrors, long resyncs, long discardedBytes, int bufferSize) {}
    public static int crc16(byte[] data, int offset, int length) {
        Objects.checkFromIndexSize(offset, length, data.length);
        int crc = 0xffff;
        for (int i=offset; i<offset+length; i++) {
            crc ^= (data[i]&255)<<8;
            for (int b=0; b<8; b++) crc = ((crc<<1)^((crc&0x8000)!=0 ? 0x1021 : 0))&0xffff;
        }
        return crc;
    }
    /** Encoding is for deterministic fixtures only; no transport is owned here. */
    public static byte[] encode(int type, byte[] payload) {
        if (payload.length>MAX_PAYLOAD || type<0 || type>255) throw new IllegalArgumentException("GSP bounds");
        byte[] raw = new byte[payload.length+6]; raw[0]=(byte)0xa5; raw[1]=0x5a;
        raw[2]=(byte)type; raw[3]=(byte)payload.length; System.arraycopy(payload,0,raw,4,payload.length);
        int crc=crc16(raw,2,payload.length+2); raw[raw.length-2]=(byte)crc; raw[raw.length-1]=(byte)(crc>>8); return raw;
    }
    public static Envelope envelope(Frame frame) {
        byte[] p=frame.payload();
        if (frame.type()!=2 && frame.type()!=5) throw new IllegalArgumentException("Not AIR receive envelope");
        if (p.length<3 || p.length!=3+(p[2]&255)) throw new IllegalArgumentException("AIR envelope length");
        if (frame.type()==5) {
            if (p[0]!=1 || p[1]!=0 || (p[2]&255)<1 || (p[2]&255)>61) throw new IllegalArgumentException("Unsupported radio backend/flags/length");
            return new Envelope(Arrays.copyOfRange(p,3,p.length),"nrf24l01p",false,null,null);
        }
        return new Envelope(Arrays.copyOfRange(p,3,p.length),"sx128x",true,(int)p[0],p[1]/4.0);
    }
    /** Input can be arbitrarily long; retained storage never exceeds one 70-byte frame. */
    public static final class Parser {
        private final byte[] buffer=new byte[70]; private int size;
        private long frames, crcErrors, resyncs, discarded;
        public List<Frame> feed(byte[] data) {
            List<Frame> out=new ArrayList<>();
            for (byte b:data) { buffer[size++]=b; drain(out); }
            return out;
        }
        private void drop(int n, boolean error) {
            if (error) { discarded+=n; resyncs++; }
            System.arraycopy(buffer,n,buffer,0,size-n); size-=n;
        }
        private void drain(List<Frame> out) {
            while (size>=2) {
                if ((buffer[0]&255)!=0xa5 || (buffer[1]&255)!=0x5a) { drop(1,true); continue; }
                if (size<4) return;
                int length=buffer[3]&255;
                if (length>64) { drop(1,true); continue; }
                int total=length+6; if (size<total) return;
                int expected=(buffer[total-2]&255)|((buffer[total-1]&255)<<8);
                if (crc16(buffer,2,length+2)!=expected) { crcErrors++; drop(1,true); continue; }
                out.add(new Frame(buffer[2]&255,Arrays.copyOfRange(buffer,4,total-2),Arrays.copyOf(buffer,total)));
                frames++; drop(total,false);
            }
        }
        public Diagnostics diagnostics() { return new Diagnostics(frames,crcErrors,resyncs,discarded,size); }
    }
    public static String hex(byte[] bytes) {
        char[] text=new char[bytes.length*2]; char[] digits="0123456789abcdef".toCharArray();
        for(int i=0;i<bytes.length;i++){text[i*2]=digits[(bytes[i]&255)>>>4];text[i*2+1]=digits[bytes[i]&15];} return new String(text);
    }
    public static byte[] unhex(String text) {
        if ((text.length()&1)!=0 || text.length()>140) throw new IllegalArgumentException("Invalid GSP hex length");
        byte[] out=new byte[text.length()/2];
        for(int i=0;i<out.length;i++){int a=Character.digit(text.charAt(i*2),16),b=Character.digit(text.charAt(i*2+1),16);if(a<0||b<0)throw new IllegalArgumentException("Invalid hex");out[i]=(byte)((a<<4)|b);}return out;
    }
}

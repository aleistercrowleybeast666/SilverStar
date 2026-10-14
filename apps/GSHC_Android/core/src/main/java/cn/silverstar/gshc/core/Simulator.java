package cn.silverstar.gshc.core;

import java.io.ByteArrayOutputStream;
import java.nio.*;

/** Synthetic receive-only flight fixture; never hardware evidence. */
public final class Simulator {
    private int seq;
    public byte[] next(long elapsedMs){
        if(elapsedMs<0)throw new IllegalArgumentException("Negative simulation time");
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        append(out,wrap(capability(),false));
        byte[] status={0x13,(byte)seq++,3,4,63,(byte)255,3,0x7f,0};
        if(elapsedMs<3000){status[2]=2;status[3]=2;status[6]=1;status[7]=0x14;status[8]=0x0b;}
        if(elapsedMs<6000)append(out,wrap(status,false));
        boolean flight=elapsedMs>=6000;ByteBuffer b=ByteBuffer.allocate(flight?50:26).order(ByteOrder.LITTLE_ENDIAN);
        b.put((byte)(flight?0x10:0x11)).put((byte)seq++).putInt((int)elapsedMs);
        b.putShort((short)0).putShort((short)0).putShort((short)2048);b.putShort((short)0).putShort((short)0).putShort((short)120);
        double yaw=elapsedMs/10000.0;b.putShort((short)(Math.cos(yaw/2)*32767)).putShort((short)0).putShort((short)0).putShort((short)(Math.sin(yaw/2)*32767));
        if(flight){double t=(elapsedMs-6000)/1000.0;b.putFloat(2).putFloat(1).putFloat((float)(12*Math.cos(t/6)));b.putFloat((float)(2*t)).putFloat((float)t).putFloat((float)Math.max(0,72*Math.sin(t/6)));}
        append(out,wrap(b.array(),(elapsedMs/1000)%2==1));return out.toByteArray();
    }
    private static void append(ByteArrayOutputStream out,byte[] bytes){out.write(bytes,0,bytes.length);}
    private byte[] capability(){return new byte[]{0x12,(byte)seq++,0,1,7,15,16,(byte)0xd0,7};}
    public static byte[] wrap(byte[] air,boolean nrf){byte[] payload=new byte[air.length+3];payload[0]=(byte)(nrf?1:-67);payload[1]=(byte)(nrf?0:24);payload[2]=(byte)air.length;System.arraycopy(air,0,payload,3,air.length);return GspCodec.encode(nrf?5:2,payload);}
}

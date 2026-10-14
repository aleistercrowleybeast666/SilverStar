package cn.silverstar.gshc;

import cn.silverstar.gshc.core.GspCodec;
import cn.silverstar.gshc.core.Simulator;
import cn.silverstar.gshc.storage.PortClaims;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import java.io.ByteArrayOutputStream;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import static org.junit.Assert.*;

/** Deterministic application-worker regressions; synthetic bytes, no USB or emulator. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=36)
public class RuntimeRegressionTest {
    private AppRuntime runtime;
    private ExecutorService worker;

    @Before public void create()throws Exception{
        runtime=((GshcApplication)RuntimeEnvironment.getApplication()).runtime();
        worker=executor("worker");
    }
    @After public void close()throws Exception{
        if(runtime==null)return;
        try{
            quietTimer();
            runtime.stop("test teardown");
            drain();
        }finally{
            worker.shutdownNow();
            worker.awaitTermination(10,TimeUnit.SECONDS);
            runtime.files.shutdownNow();
            runtime.files.awaitTermination(10,TimeUnit.SECONDS);
            runtime.sessions.finish("test teardown",false);
        }
    }

    @Test public void oldBackgroundCallbackCannotStopNewUsbSession()throws Exception{
        startSimulation();
        long oldEpoch=runtime.transportEpoch;
        String oldId=runtime.sessions.activeId();
        CountDownLatch release=new CountDownLatch(1);
        Future<?> blocker=blockWorker(release);
        PortClaims.Lease owner=claim();
        Future<?> start;
        try{
            start=runtime.beginUsb("synthetic queued USB",owner);
            runtime.background();
        }finally{release.countDown();}
        blocker.get(10,TimeUnit.SECONDS);
        start.get(10,TimeUnit.SECONDS);
        drain();
        assertEquals("usb-readonly",runtime.mode);
        assertTrue(runtime.recording);
        assertTrue(runtime.transportEpoch>oldEpoch);
        assertNotNull(runtime.sessions.activeId());
        assertNotEquals(oldId,runtime.sessions.activeId());
        assertTrue(runtime.ports.current(owner));
        assertEquals("",runtime.error);
    }

    @Test public void currentBackgroundCallbackStillStopsSimulation()throws Exception{
        startSimulation();
        runtime.background();
        drain();
        assertEquals("idle",runtime.mode);
        assertFalse(runtime.recording);
        assertNull(runtime.sessions.activeId());
        assertEquals("",runtime.error);
    }

    @Test public void explicitStopQueuedAfterStartStillStopsNewSession()throws Exception{
        quietTimer();
        CountDownLatch release=new CountDownLatch(1);
        Future<?> blocker=blockWorker(release);
        Future<?> start;
        try{
            start=runtime.beginUsb("synthetic queued USB",claim());
            runtime.stop("explicit user stop");
        }finally{release.countDown();}
        blocker.get(10,TimeUnit.SECONDS);
        start.get(10,TimeUnit.SECONDS);
        drain();
        assertEquals("idle",runtime.mode);
        assertFalse(runtime.recording);
        assertNull(runtime.sessions.activeId());
        assertEquals("explicit user stop",runtime.status);
        assertEquals("",runtime.error);
    }

    @Test public void simulatorFixtureHas31IdenticalLiveAndReplaySamples()throws Exception{
        startUsb();
        Simulator simulator=new Simulator();
        for(int elapsed=0;elapsed<=12000;elapsed+=200)receive(simulator.next(elapsed));
        List<double[]> live=runtime.points();
        assertEquals(31,live.size());
        assertEquals(0.0,live.get(0)[3],0.0);
        assertEquals(12.0,live.get(30)[3],0.0);
        assertReplayEquals(live);
    }

    @Test public void fragmentedFlightAndNonFlightFramesDoNotRepeatPoints()throws Exception{
        startUsb();
        Simulator simulator=new Simulator();
        receive(simulator.next(6000));
        assertEquals(1,runtime.points().size());
        receive(GspCodec.encode(4,new byte[]{2,0,0}));
        receive(simulator.next(0)); // Capability, preflight status, preflight telemetry.
        assertEquals(1,runtime.points().size());
        byte[] second=simulator.next(6200);
        receive(Arrays.copyOf(second,second.length-1));
        assertEquals(1,runtime.points().size());
        receive(new byte[]{second[second.length-1]});
        assertEquals(2,runtime.points().size());
        receive(new byte[]{0}); // A noise-only callback also must not sample old state.
        assertEquals(2,runtime.points().size());
        assertReplayEquals(runtime.points());
    }

    @Test public void multiFrameSamplesKeepSourceOrderAndRepeatedTimestamps()throws Exception{
        startUsb();
        Simulator simulator=new Simulator();
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        for(long time:new long[]{6400,6000,6400,6400})bytes.write(simulator.next(time));
        receive(bytes.toByteArray());
        List<double[]> live=runtime.points();
        assertEquals(4,live.size());
        assertEquals(0.8,live.get(0)[3],0.000001);
        assertEquals(0.0,live.get(1)[3],0.0);
        assertEquals(0.8,live.get(2)[3],0.000001);
        assertArrayEquals(live.get(2),live.get(3),0.0);
        assertReplayEquals(live);
    }

    private void startSimulation()throws Exception{
        runtime.simulate();
        drain();
        quietTimer();
        drain();
        assertEquals("simulation",runtime.mode);
        assertTrue(runtime.recording);
        assertEquals("",runtime.error);
    }
    private void startUsb()throws Exception{
        quietTimer();
        runtime.beginUsb("synthetic receive fixture",claim()).get(10,TimeUnit.SECONDS);
        assertTrue(runtime.recording);
    }
    private PortClaims.Lease claim()throws Exception{
        return runtime.ports.claim(PortClaims.Role.GROUND,new PortClaims.Key("test-only",1,2,0));
    }
    private void receive(byte[] bytes)throws Exception{
        runtime.receiveUsb(bytes,runtime.transportEpoch);
        drain();
        assertEquals("",runtime.error);
    }
    private void assertReplayEquals(List<double[]> live)throws Exception{
        String id=runtime.sessions.activeId();
        assertNotNull(id);
        runtime.stop("fixture complete");
        drain();
        runtime.replay(id);
        drain();
        assertEquals("",runtime.error);
        assertEquals("replay-complete",runtime.mode);
        List<double[]> replay=runtime.points();
        assertEquals(live.size(),replay.size());
        for(int i=0;i<live.size();i++)assertArrayEquals("sample "+i,live.get(i),replay.get(i),0.0);
    }
    private Future<?> blockWorker(CountDownLatch release)throws Exception{
        CountDownLatch started=new CountDownLatch(1);
        Future<?> result=worker.submit(()->{
            started.countDown();
            try{if(!release.await(10,TimeUnit.SECONDS))throw new AssertionError("worker release timed out");}
            catch(InterruptedException e){Thread.currentThread().interrupt();throw new AssertionError(e);}
        });
        assertTrue("worker entered latch",started.await(10,TimeUnit.SECONDS));
        return result;
    }
    private void quietTimer()throws Exception{
        ExecutorService timer=executor("timer");
        timer.shutdownNow();
        assertTrue("timer terminated",timer.awaitTermination(10,TimeUnit.SECONDS));
    }
    private void drain()throws Exception{worker.submit(()->{}).get(10,TimeUnit.SECONDS);}
    private ExecutorService executor(String name)throws Exception{
        Field field=AppRuntime.class.getDeclaredField(name);
        field.setAccessible(true);
        return (ExecutorService)field.get(runtime);
    }
}

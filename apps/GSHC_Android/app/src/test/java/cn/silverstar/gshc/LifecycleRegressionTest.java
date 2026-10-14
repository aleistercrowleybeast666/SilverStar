package cn.silverstar.gshc;

import android.app.Service;
import android.os.Looper;
import android.view.*;
import android.widget.Button;
import cn.silverstar.gshc.storage.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import java.io.*;
import java.lang.reflect.*;
import java.util.concurrent.*;
import static org.junit.Assert.*;

/** Lifecycle regressions use fake Closeables and latches, never USB devices. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=36)
public class LifecycleRegressionTest {
    private AppRuntime runtime;
    private ActivityController<MainActivity> activity;
    @Before public void setup()throws Exception{
        runtime=((GshcApplication)RuntimeEnvironment.getApplication()).runtime();
        ((ExecutorService)field(runtime,"timer")).shutdownNow();
    }
    @After public void teardown()throws Exception{
        if(activity!=null)activity.pause().stop().destroy();
        runtime.stop("test teardown");ExecutorService worker=(ExecutorService)field(runtime,"worker");
        worker.submit(()->{}).get(10,TimeUnit.SECONDS);worker.shutdown();worker.awaitTermination(10,TimeUnit.SECONDS);
        runtime.files.shutdownNow();runtime.files.awaitTermination(10,TimeUnit.SECONDS);runtime.sessions.finish("test teardown",false);
    }
    @Test public void groundDestroyWaitsForIoAndCloseWithoutBlockingUi()throws Exception{
        UsbReadService service=Robolectric.buildService(UsbReadService.class).create().get();
        PortClaims.Key key=new PortClaims.Key("synthetic-ground",1,2,0);PortClaims.Lease owner=runtime.ports.claim(PortClaims.Role.GROUND,key);set(service,"lease",owner);
        CloseScope scope=(CloseScope)field(service,"resources");ExecutorService io=(ExecutorService)field(service,"io");
        CountDownLatch closing=new CountDownLatch(1),release=new CountDownLatch(1);
        scope.own(()->{closing.countDown();await(release);});boolean destroyed=false;
        try{
            Future<?> prior=io.submit(()->{try{scope.close();}catch(IOException e){throw new UncheckedIOException(e);}});
            assertTrue(closing.await(5,TimeUnit.SECONDS));service.onDestroy();destroyed=true;
            assertFalse(runtime.ports.current(owner));assertEquals(owner,runtime.ports.get(PortClaims.Role.GROUND));
            assertThrows(IOException.class,()->runtime.ports.claim(PortClaims.Role.DEBUG,key));
            assertFalse(prior.isDone());release.countDown();prior.get(5,TimeUnit.SECONDS);assertTrue(io.awaitTermination(5,TimeUnit.SECONDS));
            PortClaims.Lease next=runtime.ports.claim(PortClaims.Role.GROUND,key);invoke(service,"closeAndRelease");assertTrue(runtime.ports.current(next));
        }finally{release.countDown();if(!destroyed)service.onDestroy();io.awaitTermination(5,TimeUnit.SECONDS);}
    }
    @Test public void maintenanceReleaseWaitsForExchangeExitAfterClose()throws Exception{
        UsbMaintenanceService service=Robolectric.buildService(UsbMaintenanceService.class).create().get();
        PortClaims.Key key=new PortClaims.Key("synthetic-debug",1,3,0);PortClaims.Lease owner=runtime.ports.claim(PortClaims.Role.DEBUG,key);set(service,"lease",owner);
        ExecutorService setup=(ExecutorService)field(service,"setup"),fakeIo=Executors.newSingleThreadExecutor();Object exchange=field(service,"exchangeLock");
        CountDownLatch inExchange=new CountDownLatch(1),release=new CountDownLatch(1),closed=new CountDownLatch(1);
        ((CloseScope)field(service,"resources")).own(closed::countDown);boolean destroyed=false;
        try{
            Future<?> prior=fakeIo.submit(()->{synchronized(exchange){inExchange.countDown();try{await(release);}catch(IOException e){throw new UncheckedIOException(e);}}});
            assertTrue(inExchange.await(5,TimeUnit.SECONDS));service.onDestroy();destroyed=true;assertTrue(closed.await(5,TimeUnit.SECONDS));
            assertEquals(owner,runtime.ports.get(PortClaims.Role.DEBUG));assertFalse(runtime.ports.current(owner));
            assertThrows(IOException.class,()->runtime.ports.claim(PortClaims.Role.GROUND,key));
            release.countDown();prior.get(5,TimeUnit.SECONDS);assertTrue(setup.awaitTermination(5,TimeUnit.SECONDS));assertNull(runtime.ports.get(PortClaims.Role.DEBUG));
        }finally{release.countDown();if(!destroyed)service.onDestroy();fakeIo.shutdownNow();setup.awaitTermination(5,TimeUnit.SECONDS);}
    }
    @Test public void rotationDiscardsOldRecycleDialogAndPreservesSession()throws Exception{
        String id=runtime.sessions.begin("synthetic recycled session","simulation",1);runtime.sessions.finish("complete");runtime.sessions.recycle(id,true);
        activity=Robolectric.buildActivity(MainActivity.class).setup();MainActivity old=activity.get();button(old.getWindow().getDecorView(),"后期处理").performClick();runtime.files.submit(()->{}).get(5,TimeUnit.SECONDS);
        PortClaims.Lease owner=runtime.ports.claim(PortClaims.Role.GROUND,new PortClaims.Key("synthetic",1,2,0));runtime.beginUsb("test-only recording",owner).get(5,TimeUnit.SECONDS);String activeId=runtime.sessions.activeId();
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
        Future<?> blocker=runtime.files.submit(()->{entered.countDown();try{await(release);}catch(IOException e){throw new UncheckedIOException(e);}});
        try{
            assertTrue(entered.await(5,TimeUnit.SECONDS));button(old.getWindow().getDecorView(),"回收站 / 恢复").performClick();activity.recreate();assertTrue(old.isDestroyed());
        }finally{release.countDown();}
        blocker.get(5,TimeUnit.SECONDS);runtime.files.submit(()->{}).get(5,TimeUnit.SECONDS);Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertNull(ShadowAlertDialog.getLatestAlertDialog());assertEquals(activeId,runtime.sessions.activeId());assertTrue(runtime.recording);assertTrue(runtime.sessions.list(true).contains(id));
    }
    private static void await(CountDownLatch latch)throws IOException{try{if(!latch.await(10,TimeUnit.SECONDS))throw new IOException("test latch timeout");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}}
    private static Object field(Object owner,String name)throws Exception{Field field=owner.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(owner);}
    private static void set(Object owner,String name,Object value)throws Exception{Field field=owner.getClass().getDeclaredField(name);field.setAccessible(true);field.set(owner,value);}
    private static void invoke(Object owner,String name)throws Exception{Method method=owner.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(owner);}
    private static Button button(View view,String text){if(view instanceof Button b&&b.getText().toString().equals(text))return b;if(view instanceof ViewGroup group)for(int i=0;i<group.getChildCount();i++){Button found=button(group.getChildAt(i),text);if(found!=null)return found;}return null;}
}

package cn.silverstar.gshc;

import android.content.*;
import android.content.pm.ProviderInfo;
import android.database.*;
import android.net.Uri;
import android.os.*;
import android.provider.*;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.view.*;
import android.widget.*;
import cn.silverstar.gshc.storage.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowContentResolver;
import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.Assert.*;

/** Local Android-framework/shadow tests. No emulator, USB device, or system SAF UI is exercised. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=36)
public class AndroidIntegrationTest {
    private ActivityController<MainActivity> controller;
    private GshcApplication application;
    @Before public void create(){application=(GshcApplication)RuntimeEnvironment.getApplication();}
    @After public void close()throws Exception{
        if(controller!=null)controller.pause().stop().destroy();
        AppRuntime runtime=application.runtime();Field timer=AppRuntime.class.getDeclaredField("timer");timer.setAccessible(true);((ExecutorService)timer.get(runtime)).shutdownNow();
        runtime.stop("test complete");Field worker=AppRuntime.class.getDeclaredField("worker");worker.setAccessible(true);ExecutorService executor=(ExecutorService)worker.get(runtime);executor.submit(()->{}).get(10,TimeUnit.SECONDS);executor.shutdown();executor.awaitTermination(10,TimeUnit.SECONDS);
        runtime.files.shutdownNow();runtime.files.awaitTermination(10,TimeUnit.SECONDS);runtime.sessions.finish("test teardown",false);
    }
    private MainActivity launch(){controller=Robolectric.buildActivity(MainActivity.class).setup();return controller.get();}
    private static List<Button> buttons(View root){List<Button> result=new ArrayList<>();if(root instanceof Button)result.add((Button)root);if(root instanceof ViewGroup group)for(int i=0;i<group.getChildCount();i++)result.addAll(buttons(group.getChildAt(i)));return result;}
    private static Button button(MainActivity a,String text){return buttons(a.getWindow().getDecorView()).stream().filter(b->b.getText().toString().equals(text)).findFirst().orElseThrow(()->new AssertionError("Missing button: "+text));}
    @Test public void fourPagesAndTwoDistinctTopPortsActuallyInflate(){
        MainActivity a=launch();
        for(String title:new String[]{"预飞行","飞行","后期处理","调试与维护"}){button(a,title).performClick();assertNotNull(button(a,title));}
        List<Button> all=buttons(a.getWindow().getDecorView());
        assertEquals(1,all.stream().filter(b->b.getText().toString().startsWith("地面站端口 ·")).count());
        assertEquals(1,all.stream().filter(b->b.getText().toString().startsWith("飞控调试口 ·")).count());
        assertFalse(button(a,"下载已关闭文件并校验").isEnabled());
        assertFalse(button(a,"模拟自动下载 / 校验").isEnabled());
        assertNotNull(button(a,"选择 TF 保存目录"));
    }
    @Test public void activityRecreationKeepsApplicationAndPage(){
        MainActivity a=launch();button(a,"调试与维护").performClick();AppRuntime before=application.runtime();
        controller.recreate();assertSame(before,((GshcApplication)controller.get().getApplication()).runtime());
        assertNotNull(button(controller.get(),"选择 TF 保存目录"));
    }
    @Test public void realUsbGateBlocksBeforePermissionOrClaim()throws Exception{
        assertFalse(BuildConfig.ALLOW_USB);
        assertThrows(IOException.class,()->application.usb().request(null,0,PortClaims.Role.GROUND,230400));
        assertNull(application.runtime().ports.get(PortClaims.Role.GROUND));assertNull(application.runtime().ports.get(PortClaims.Role.DEBUG));
    }
    @Test public void safPickerAndUnpersistedTargetDoNotInventDurablePermission(){
        Intent intent=SafDirectory.picker();assertEquals(Intent.ACTION_OPEN_DOCUMENT_TREE,intent.getAction());
        assertTrue((intent.getFlags()&Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)!=0);
        Uri uri=Uri.parse("content://test.documents/tree/root");
        assertFalse(SafDirectory.remember(application,uri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION));
        assertEquals("",SafDirectory.remembered(application));
    }
    @Test public void safProviderCopyReadbackUniqueCreationAndRevocation()throws Exception{
        TestDocuments provider=new TestDocuments();ProviderInfo info=new ProviderInfo();info.authority="test.documents";info.exported=true;info.grantUriPermissions=true;info.readPermission="android.permission.MANAGE_DOCUMENTS";info.writePermission=info.readPermission;
        provider.attachInfo(application,info);ShadowContentResolver.registerProviderInternal(info.authority,provider);
        SafDirectory directory=new SafDirectory(application,DocumentsContract.buildTreeDocumentUri(info.authority,"root"));
        directory.validate();SafDirectory.Target first=directory.create("flight",".sslog","application/octet-stream");SafDirectory.Target second=directory.create("flight",".sslog","application/octet-stream");
        assertNotEquals(first.description(),second.description());
        Path original=application.getCacheDir().toPath().resolve("generated-original.bin");byte[] content={0,1,2,3,(byte)255};Files.write(original,content);
        assertEquals(content.length,VerifiedFileCopy.copy(original,first).size());
        try(InputStream in=first.openRead()){assertArrayEquals(content,in.readAllBytes());}
        provider.revoked=true;assertThrows(IOException.class,directory::validate);assertArrayEquals(content,Files.readAllBytes(original));
    }
    public static class TestDocuments extends DocumentsProvider {
        private final Map<String,File> files=new HashMap<>();boolean revoked;
        @Override public boolean onCreate(){return true;}
        @Override public Cursor queryRoots(String[] projection){return new MatrixCursor(new String[]{Root.COLUMN_ROOT_ID,Root.COLUMN_DOCUMENT_ID});}
        @Override public Cursor queryDocument(String id,String[] projection){
            if(revoked)throw new SecurityException("Generated permission revocation");
            String[] columns=projection==null?new String[]{Document.COLUMN_DOCUMENT_ID,Document.COLUMN_DISPLAY_NAME,Document.COLUMN_MIME_TYPE,Document.COLUMN_FLAGS}:projection;
            MatrixCursor cursor=new MatrixCursor(columns);Object[] row=new Object[columns.length];
            for(int i=0;i<columns.length;i++){String c=columns[i];row[i]=c.equals(Document.COLUMN_DOCUMENT_ID)?id:c.equals(Document.COLUMN_FLAGS)?(id.equals("root")?Document.FLAG_DIR_SUPPORTS_CREATE:Document.FLAG_SUPPORTS_WRITE):c.equals(Document.COLUMN_MIME_TYPE)?(id.equals("root")?Document.MIME_TYPE_DIR:"application/octet-stream"):id;}
            cursor.addRow(row);return cursor;
        }
        @Override public Cursor queryChildDocuments(String parent,String[] projection,String sortOrder){return new MatrixCursor(new String[]{Document.COLUMN_DOCUMENT_ID});}
        @Override public boolean isChildDocument(String parent,String child){return parent.equals("root")&&files.containsKey(child);}
        @Override public String createDocument(String parent,String mime,String name)throws FileNotFoundException{
            if(revoked)throw new SecurityException("Generated permission revocation");String id=UUID.randomUUID().toString();File f=new File(getContext().getCacheDir(),id);files.put(id,f);return id;
        }
        @Override public ParcelFileDescriptor openDocument(String id,String mode,CancellationSignal signal)throws FileNotFoundException{
            if(revoked)throw new SecurityException("Generated permission revocation");File f=files.get(id);if(f==null)throw new FileNotFoundException(id);return ParcelFileDescriptor.open(f,ParcelFileDescriptor.parseMode(mode));
        }
    }
}

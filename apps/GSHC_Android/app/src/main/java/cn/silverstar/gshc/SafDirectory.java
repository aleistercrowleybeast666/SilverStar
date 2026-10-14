package cn.silverstar.gshc;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import cn.silverstar.gshc.storage.VerifiedExport;
import java.io.*;
import java.util.UUID;

/** Shared SAF directory selection mechanics; TF downloads and session exports keep separate semantics. */
final class SafDirectory {
    private static final String PREFS="export-destinations",TF="tf-directory";
    private final Context context;private final Uri tree;
    SafDirectory(Context context,Uri tree){this.context=context.getApplicationContext();this.tree=tree;}
    static Intent picker(){return new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);}
    static String remembered(Context context){
        String uri=context.getSharedPreferences(PREFS,0).getString(TF,"");
        if(uri.isEmpty())return uri;
        for(UriPermission grant:context.getContentResolver().getPersistedUriPermissions())if(grant.getUri().toString().equals(uri)&&grant.isReadPermission()&&grant.isWritePermission())return uri;
        context.getSharedPreferences(PREFS,0).edit().remove(TF).apply();return "";
    }
    static boolean remember(Context context,Uri uri,int flags){
        int access=flags&(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        boolean persisted=false;
        if((flags&Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)!=0&&access==(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION)){
            try{context.getContentResolver().takePersistableUriPermission(uri,access);persisted=true;}catch(SecurityException ignored){/* Session-only destination remains available. */}
        }
        android.content.SharedPreferences.Editor edit=context.getSharedPreferences(PREFS,0).edit();
        if(persisted)edit.putString(TF,uri.toString());else edit.remove(TF);edit.apply();return persisted;
    }
    private Uri document(){return DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));}
    void validate()throws IOException{
        try(Cursor cursor=context.getContentResolver().query(document(),new String[]{DocumentsContract.Document.COLUMN_FLAGS},(android.os.Bundle)null,null)){
            if(cursor==null||!cursor.moveToFirst()||(cursor.getInt(0)&DocumentsContract.Document.FLAG_DIR_SUPPORTS_CREATE)==0)throw new IOException("目标目录不能创建文件，请重新选择");
        }catch(SecurityException e){throw new IOException("目录授权已撤销，请重新选择；内部原件保留",e);}
    }
    Target create(String stem,String extension,String mime)throws IOException{
        validate();
        // createDocument creates a new document; every name has a random suffix. Existing names are never opened for write.
        String name=stem+"_"+UUID.randomUUID()+extension;
        try{Uri uri=DocumentsContract.createDocument(context.getContentResolver(),document(),mime,name);if(uri==null)throw new IOException("目标 provider 未创建文件");return new Target(context,uri);}
        catch(SecurityException e){throw new IOException("目录授权已撤销，请重新选择",e);}
    }
    static final class Target implements VerifiedExport.Target {
        private final Context context;final Uri uri;
        Target(Context context,Uri uri){this.context=context;this.uri=uri;}
        public OutputStream openWrite()throws IOException{OutputStream out=context.getContentResolver().openOutputStream(uri,"w");if(out==null)throw new IOException("目标不可写");return out;}
        public InputStream openRead()throws IOException{InputStream in=context.getContentResolver().openInputStream(uri);if(in==null)throw new IOException("目标无法回读，不能标为完成");return in;}
        public String description(){return uri.toString();}
    }
}

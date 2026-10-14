import cn.silverstar.gshc.core.tf.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

public final class TfTests {
    private static int checks;
    private static void check(boolean good,String why){checks++;if(!good)throw new AssertionError(why);}
    interface Attempt{void run()throws IOException;}
    private static void rejects(Attempt run,String why)throws IOException{boolean rejected=false;try{run.run();}catch(IOException e){rejected=true;}check(rejected,why);}
    private static boolean noPublished(Path directory)throws IOException{try(var files=Files.list(directory)){return files.noneMatch(p->p.toString().endsWith(".sslog"));}}
    private static String field(String json,String key){Matcher m=Pattern.compile("\""+Pattern.quote(key)+"\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);if(!m.find())throw new AssertionError("Missing shared JSON string "+key);return m.group(1).replace("\\r","\r").replace("\\n","\n").replace("\\\"","\"").replace("\\\\","\\");}
    private static int numeric(String json,String key){Matcher m=Pattern.compile("\""+Pattern.quote(key)+"\"\\s*:\\s*(\\d+)").matcher(json);if(!m.find())throw new AssertionError("Missing shared JSON number "+key);return Integer.parseInt(m.group(1));}
    private static byte[] hex(String hex){byte[] bytes=new byte[hex.length()/2];for(int i=0;i<bytes.length;i++)bytes[i]=(byte)Integer.parseInt(hex.substring(2*i,2*i+2),16);return bytes;}
    private static final class Script implements MaintenanceTfSource.LineTransport {
        private final Deque<String> requests=new ArrayDeque<>(),replies=new ArrayDeque<>();int calls;
        Script add(String request,String reply){requests.add(request);replies.add(reply);return this;}
        @Override public String exchange(String request,long timeout)throws IOException{
            calls++;check(timeout>0&&timeout<=30000,"transport bounded timeout");check(request.length()<=191,"request bounded");
            if(requests.isEmpty())throw new AssertionError("Unexpected request "+request);String expected=requests.remove();check(expected.equals(request),"exact serialized request: "+expected);
            String response=replies.remove();if(response.equals("INJECT_TIMEOUT"))throw new IOException("Injected timeout");return response;
        }
        void done(){check(requests.isEmpty()&&replies.isEmpty(),"script fully consumed");}
    }
    private static Script negotiated(String caps,String token,String crc,int size){return new Script().add("LOGFILE CAPS\r\n",caps+"\r\n").add("LOGFILE META 1\r\n","PENDING LOGFILE META request_id=2\r\n").add("LOGFILE POLL 2\r\n","OK LOGFILE META request_id=2 file_id=1 token="+token+" size="+size+" crc32="+crc+" format=SSLOG format_version=0.0 closed=1\r\n");}
    public static void main(String[] args)throws Exception{
        Path root=Files.createTempDirectory(Path.of(args[0]),"tf-v1-test-");
        // Wire golden remains compatible; integration policy is read directly from its own exact snapshot.
        Path legacyContract=Path.of(args[1]);
        Path integrationContract=legacyContract.getParent().getParent().getParent().resolve("integration-f2ce541/log_file_service_v1.json");
        String contract=Files.readString(integrationContract,StandardCharsets.UTF_8);
        String prior=Files.readString(legacyContract,StandardCharsets.UTF_8);
        check(field(prior.substring(prior.indexOf("\"golden\"")),"read_response").equals(field(contract.substring(contract.indexOf("\"golden\"")),"read_response")),"integration keeps shared wire golden unchanged");
        String golden=contract.substring(contract.indexOf("\"golden\""));String responses=contract.substring(contract.indexOf("\"responses\""));
        byte[] goldenBytes=hex(field(golden,"file_bytes_hex"));String token=field(golden,"token"),crc=field(golden,"crc32");int size=numeric(golden,"size");
        String goldenRequest=field(golden,"read_request"),goldenResponse=field(golden,"read_response"),caps=field(responses,"CAPS");
        check(numeric(contract,"protocol_version")==TfLogClient.VERSION,"shared service version");check(numeric(contract,"chunk_bytes")==TfLogClient.CHUNK_BYTES,"shared chunk bound");
        check(numeric(contract,"request_bytes")==MaintenanceTfSource.MAX_REQUEST_BYTES&&numeric(contract,"response_bytes")==MaintenanceTfSource.MAX_RESPONSE_BYTES,"shared line bounds");
        check(TfLogClient.crc32(goldenBytes)==Long.parseLong(crc,16)&&goldenBytes.length==size,"shared golden CRC/size");check(TfLogClient.tokenFor(TfLogClient.crc32(goldenBytes),size).equals(token),"shared golden token");
        check(MaintenanceTfSource.readRequest(1,token,0).equals(goldenRequest),"shared golden READ request exact");
        check(caps.contains("delete_supported=0")&&!caps.contains("resume_supported"),"integration read-only CAPS has no invented resume field");
        check(field(contract.substring(contract.indexOf("\"semantics\"")),"resume").contains("restart read-only download at offset zero"),"shared integration mandates restart");
        Script script=negotiated(caps,token,crc,size).add(goldenRequest,"PENDING LOGFILE READ request_id=3\r\n").add("LOGFILE POLL 3\r\n","PENDING LOGFILE READ request_id=3\r\n").add("LOGFILE POLL 3\r\n",goldenResponse);
        MaintenanceTfSource ascii=new MaintenanceTfSource(script);var wireCaps=ascii.caps();check(!wireCaps.deleteSupported()&&!wireCaps.resumeAllowed(),"wire delete and local resume unavailable");check(!wireCaps.resumeUnavailableReason().isEmpty(),"resume reason exposed as local policy");ascii.meta(1);check(Arrays.equals(ascii.read(1,token,0).bytes(),goldenBytes),"shared golden READ response bytes");script.done();
        for(String invalid:List.of(goldenResponse.replace("request_id=3","request_id=4"),goldenResponse.replace("LOGFILE READ","LOGFILE META"),goldenResponse.replace("file_id=1","file_id=2"),goldenResponse.replace("offset=0","offset=1"),goldenResponse.replace("crc32="+crc,"crc32=00000000"),goldenResponse.replace("length=9","length=65"))){
            Script fault=negotiated(caps,token,crc,size).add(goldenRequest,"PENDING LOGFILE READ request_id=3\r\n").add("LOGFILE POLL 3\r\n",invalid);MaintenanceTfSource source=new MaintenanceTfSource(fault);source.caps();source.meta(1);
            rejects(()->source.read(1,token,0),"mismatched completion rejected");int calls=fault.calls;rejects(()->source.read(1,token,0),"failure invalidates CAPS/META");check(fault.calls==calls,"old token never retransmitted after error");fault.done();
        }
        for(String unsupported:List.of("ERR UNKNOWN MODULE\r\n",caps.replace("file_service_version=1","file_service_version=0")+"\r\n",caps.replace("supported=1","supported=0")+"\r\n",caps.replace("max_chunk=64","max_chunk=32")+"\r\n","X".repeat(512)+"\r\n")){
            Script badCaps=new Script().add("LOGFILE CAPS\r\n",unsupported);rejects(()->new MaintenanceTfSource(badCaps).caps(),"legacy/unsupported/bounded CAPS rejection");badCaps.done();
        }
        Script timeout=negotiated(caps,token,crc,size).add(goldenRequest,"INJECT_TIMEOUT");MaintenanceTfSource timed=new MaintenanceTfSource(timeout);timed.caps();timed.meta(1);rejects(()->timed.read(1,token,0),"timeout invalidation");int calls=timeout.calls;rejects(()->timed.read(1,token,0),"timeout requires CAPS+META");check(timeout.calls==calls,"timeout cannot reuse token");timeout.done();
        Script cancelled=negotiated(caps,token,crc,size).add("LOGFILE CANCEL\r\n","OK LOGFILE CANCEL cancelled=1\r\n");MaintenanceTfSource stopped=new MaintenanceTfSource(cancelled);stopped.caps();stopped.meta(1);stopped.cancel();rejects(()->stopped.read(1,token,0),"cancel requires CAPS+META");cancelled.done();
        Script wire=new Script().add("LOGFILE CAPS\r\n",caps+"\r\n")
                .add("LOGFILE LIST 0\r\n","PENDING LOGFILE LIST request_id=1\r\n")
                .add("LOGFILE POLL 1\r\n","OK LOGFILE LIST request_id=1 file_id=1 size="+size+" closed=1 next_cursor=1 end=0\r\n")
                .add("LOGFILE LIST 1\r\n","PENDING LOGFILE LIST request_id=2\r\n")
                .add("LOGFILE POLL 2\r\n","OK LOGFILE LIST request_id=2 end=1 next_cursor=0\r\n")
                .add("LOGFILE CAPS\r\n",caps+"\r\n")
                .add("LOGFILE META 1\r\n","PENDING LOGFILE META request_id=3\r\n")
                .add("LOGFILE POLL 3\r\n","OK LOGFILE META request_id=3 file_id=1 token="+token+" size="+size+" crc32="+crc+" format=SSLOG format_version=0.0 closed=1\r\n")
                .add(goldenRequest,"PENDING LOGFILE READ request_id=4\r\n")
                .add("LOGFILE POLL 4\r\n",goldenResponse.replace("request_id=3","request_id=4"));
        var wireResult=new TfLogClient().downloadAll(new MaintenanceTfSource(wire),root.resolve("wire-golden")).get(0);
        check(Arrays.equals(Files.readAllBytes(wireResult.localFile()),goldenBytes),"shared golden full ASCII LIST/META/READ download");wire.done();
        Script emptyRead=negotiated(caps,token,crc,size).add(MaintenanceTfSource.readRequest(1,token,size),"PENDING LOGFILE READ request_id=3\r\n")
                .add("LOGFILE POLL 3\r\n","OK LOGFILE READ request_id=3 file_id=1 token="+token+" offset="+size+" length=0 crc32=00000000 data=-\r\n");
        MaintenanceTfSource endSource=new MaintenanceTfSource(emptyRead);endSource.caps();endSource.meta(1);check(endSource.read(1,token,size).bytes().length==0,"READ EOF dash and zero CRC");emptyRead.done();
        check(Arrays.stream(TfLogClient.Source.class.getDeclaredMethods()).noneMatch(m->m.getName().toLowerCase(Locale.ROOT).contains("delete")),"no card-delete source API");
        Script reconnect=negotiated(caps,token,crc,size);MaintenanceTfSource resetSource=new MaintenanceTfSource(reconnect);resetSource.caps();resetSource.meta(1);resetSource.transportReset();int resetCalls=reconnect.calls;
        rejects(()->resetSource.read(1,token,0),"transport reset requires fresh CAPS+META");check(reconnect.calls==resetCalls,"reconnect cannot send old token");reconnect.done();
        byte[] bytes=new byte[203];new Random(42).nextBytes(bytes);TfLogClient client=new TfLogClient();MockTfSource source=new MockTfSource(bytes);source.failAtOffset=64;
        rejects(()->client.downloadAll(source,root.resolve("resume")),"disconnect preserves partial");check(noPublished(root.resolve("resume")),"incomplete remains unpublished");
        Path oldPartial;try(var paths=Files.list(root.resolve("resume"))){oldPartial=paths.filter(path->path.toString().endsWith(".part")).findFirst().orElseThrow();}
        byte[] savedPrefix=Files.readAllBytes(oldPartial);check(savedPrefix.length==64,"failed attempt retains committed prefix");
        int previousCaps=source.capsCalls,previousMeta=source.metaCalls,previousReads=source.reads,previousRequests=source.requestedOffsets.size();source.failAtOffset=Long.MAX_VALUE;var result=client.downloadAll(source,root.resolve("resume")).get(0);
        check(source.capsCalls>previousCaps&&source.metaCalls>previousMeta,"new attempt renegotiates CAPS+META");check(source.reads-previousReads==4,"matching content restarts entire transfer");
        check(source.requestedOffsets.get(previousRequests)==0,"reconnect starts READ at offset zero");
        check(!result.resumed()&&result.downloadedBytes()==bytes.length,"unknown identity never resumes matching prefix/token");check(Arrays.equals(bytes,Files.readAllBytes(result.localFile())),"original bytes preserved");check(result.localSha256().equals(TfLogClient.sha256(bytes)),"SHA-256 calculated locally");
        check(Files.exists(oldPartial)&&Arrays.equals(savedPrefix,Files.readAllBytes(oldPartial)),"old partial remains byte-identical");
        previousRequests=source.requestedOffsets.size();var again=client.downloadAll(source,root.resolve("resume")).get(0);
        check(again.downloadedBytes()==bytes.length&&!again.resumed()&&!again.localFile().equals(result.localFile()),"same completed token/content starts new path and full download");
        check(source.requestedOffsets.get(previousRequests)==0&&Arrays.equals(bytes,Files.readAllBytes(result.localFile())),"new attempt starts zero and preserves old completed file");
        check(!source.caps().deleteSupported()&&!source.caps().resumeAllowed(),"mock defaults to read-only unknown-identity policy");source.advertisedDeleteSupported=true;
        check(source.caps().deleteSupported()&&!source.caps().resumeAllowed(),"advertised delete cannot enable resume or add deletion API");source.advertisedDeleteSupported=false;
        Properties metadata=new Properties();try(var in=Files.newInputStream(result.localFile().resolveSibling(result.localFile().getFileName().toString().replace(".sslog",".metadata")))){metadata.load(in);}
        check("unknown".equals(metadata.getProperty("device_id"))&&"unknown".equals(metadata.getProperty("boot_id")),"no invented identity");check("0.0".equals(metadata.getProperty("format_version"))&&"1.2".equals(metadata.getProperty("required_decoder_package_version")),"container and decoder versions remain distinct");
        MockTfSource corrupt=new MockTfSource(bytes);corrupt.corruptCrc=true;rejects(()->client.downloadAll(corrupt,root.resolve("crc")),"chunk CRC mismatch");
        MockTfSource prefix=new MockTfSource(bytes);prefix.failAtOffset=64;rejects(()->client.downloadAll(prefix,root.resolve("prefix")),"partial fixture");byte[] changed=bytes.clone();changed[0]^=1;prefix.replaceBytesKeepingMetadata(changed);prefix.failAtOffset=Long.MAX_VALUE;rejects(()->client.downloadAll(prefix,root.resolve("prefix")),"new attempt with same token fails final CRC for changed bytes");check(noPublished(root.resolve("prefix")),"changed bytes remain unpublished");
        try(var paths=Files.list(root.resolve("prefix"))){check(paths.filter(path->path.toString().endsWith(".part")).count()==2,"failed retry creates new partial and preserves old partial");}
        MockTfSource wrongWhole=new MockTfSource(bytes);wrongWhole.replaceBytesKeepingMetadata(changed);rejects(()->client.downloadAll(wrongWhole,root.resolve("whole")),"final CRC mismatch blocks publication");check(noPublished(root.resolve("whole")),"wrong whole CRC retains partial");
        MockTfSource empty=new MockTfSource(new byte[0]);var emptyResult=client.downloadAll(empty,root.resolve("empty")).get(0);check(Files.size(emptyResult.localFile())==0&&emptyResult.entry().crc32()==0,"empty CRC zero");
        TfLogClient.Source active=new TfLogClient.Source(){public TfLogClient.Capabilities caps(){return source.caps();}public TfLogClient.ListPage list(long c){return new TfLogClient.ListPage(new TfLogClient.ListedFile(1,bytes.length,false),1,false);}public TfLogClient.Metadata meta(int i){throw new AssertionError("must not META active");}public TfLogClient.Chunk read(int i,String t,long o){throw new AssertionError("must not READ active");}public void cancel(){}};
        rejects(()->client.downloadAll(active,root.resolve("active")),"CLOSED gate");
        System.out.println("PASS: "+checks+" shared LOGFILE v1 assertions; direct shared golden ASCII/POLL, unknown-identity restart at zero, retained attempts, CRC/size/SHA-256, no device deletion API.");
    }
}

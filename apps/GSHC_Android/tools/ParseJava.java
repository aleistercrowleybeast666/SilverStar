import javax.tools.*;
import com.sun.source.util.JavacTask;
import java.nio.file.*;
import java.util.*;

/** Parse-only Android source check; deliberately not an Android API/type/build claim. */
public class ParseJava {
    public static void main(String[] args)throws Exception{
        Path root=Paths.get(args[0]);List<java.io.File> sources=new ArrayList<>();
        try(var files=Files.walk(root)){files.filter(p->p.toString().endsWith(".java")).forEach(p->sources.add(p.toFile()));}
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();DiagnosticCollector<JavaFileObject> diagnostics=new DiagnosticCollector<>();
        try(StandardJavaFileManager manager=compiler.getStandardFileManager(diagnostics,Locale.ROOT,java.nio.charset.StandardCharsets.UTF_8)){
            JavacTask task=(JavacTask)compiler.getTask(null,manager,diagnostics,Arrays.asList("-proc:none","--release","17"),null,manager.getJavaFileObjectsFromFiles(sources));
            task.parse();
            for(Diagnostic<?> diagnostic:diagnostics.getDiagnostics())if(diagnostic.getKind()==Diagnostic.Kind.ERROR)throw new IllegalStateException(diagnostic.toString());
        }
        System.out.println("PASS: "+sources.size()+" Android Java files parsed; API/type/link/DEX/build checks NOT RUN (SDK absent).");
    }
}

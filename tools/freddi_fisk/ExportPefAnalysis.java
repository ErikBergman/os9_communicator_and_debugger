// Export static analysis and decompiler output; never executes the target.
// @category FreddiFisk
import com.google.gson.GsonBuilder;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ExportPefAnalysis extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getLanguageID().toString().equals("PowerPC:BE:32:default")) {
            throw new IllegalStateException("Expected the game's 32-bit big-endian PowerPC language");
        }
        if (getScriptArgs().length != 1) {
            throw new IllegalArgumentException("Pass exactly one output directory");
        }
        Path output = Path.of(getScriptArgs()[0]);
        Files.createDirectories(output.resolve("functions"));
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("program", currentProgram.getName());
        report.put("format", currentProgram.getExecutableFormat());
        report.put("language", currentProgram.getLanguageID().toString());
        report.put("compiler_spec", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        report.put("executable_sha256", currentProgram.getExecutableSHA256());
        report.put("ghidra_version", ghidra.framework.Application.getApplicationVersion());
        List<Map<String, Object>> imports = new ArrayList<>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getExternalSymbols();
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("name", symbol.getName(true));
            item.put("address", symbol.getAddress().toString());
            imports.add(item);
        }
        report.put("imports", imports);
        List<Map<String, Object>> strings = new ArrayList<>();
        DataIterator dataItems = currentProgram.getListing().getDefinedData(true);
        while (dataItems.hasNext()) {
            Data data = dataItems.next();
            if (!data.hasStringValue()) continue;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("address", data.getAddress().toString());
            item.put("value", StringDataInstance.getStringDataInstance(data).getStringValue());
            strings.add(item);
        }
        report.put("defined_strings", strings);
        List<Map<String, Object>> functions = new ArrayList<>();
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException(decompiler.getLastMessage());
        }
        int completed = 0;
        try {
            FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(true);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Function function = iterator.next();
                if (function.isExternal()) continue;
                Address entry = function.getEntryPoint();
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("address", entry.toString());
                item.put("name", function.getName());
                item.put("signature", function.getSignature().toString());
                item.put("body_bytes", function.getBody().getNumAddresses());
                Set<String> callers = new LinkedHashSet<>();
                for (Reference reference : getReferencesTo(entry)) {
                    Function caller = getFunctionContaining(reference.getFromAddress());
                    if (caller != null) callers.add(caller.getEntryPoint().toString());
                }
                item.put("referenced_by_functions", callers);
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                boolean success = result.decompileCompleted() && result.getDecompiledFunction() != null;
                item.put("decompiled", success);
                item.put("diagnostic", result.getErrorMessage());
                if (success) {
                    String filename = "functions/" + entry.toString().replace(':', '_') + ".c";
                    Files.writeString(output.resolve(filename), result.getDecompiledFunction().getC(), StandardCharsets.UTF_8);
                    item.put("pseudocode_file", filename);
                    completed++;
                }
                functions.add(item);
                if (functions.size() % 100 == 0) println("Exported " + functions.size() + " functions");
            }
        } finally {
            decompiler.dispose();
        }
        report.put("functions", functions);
        report.put("function_count", functions.size());
        report.put("decompiled_function_count", completed);
        report.put("cancelled", monitor.isCancelled());
        Files.writeString(output.resolve("ghidra-analysis.json"),
            new GsonBuilder().setPrettyPrinting().create().toJson(report) + "\n", StandardCharsets.UTF_8);
        println("Static export complete: " + completed + " / " + functions.size() + " functions decompiled");
    }
}

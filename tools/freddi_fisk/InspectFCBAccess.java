// Trace real Ghidra references to FCB imports without assuming import-table offsets.
// @category FreddiFisk
import com.google.gson.GsonBuilder;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class InspectFCBAccess extends GhidraScript {
    @Override
    public void run() throws Exception {
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("language", currentProgram.getLanguageID().toString());
        report.put("executable_sha256", currentProgram.getExecutableSHA256());
        report.put("cancelled", false);
        List<Map<String, Object>> imports = new ArrayList<>();
        Set<Function> functions = new LinkedHashSet<>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getExternalSymbols();
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            if (!symbol.getName().contains("FCB")) continue;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("name", symbol.getName(true));
            item.put("external_address", symbol.getAddress().toString());
            List<Map<String, Object>> edges = new ArrayList<>();
            Set<Address> seen = new HashSet<>();
            List<Address> layer = List.of(symbol.getAddress());
            for (int depth = 0; depth < 5 && !layer.isEmpty(); depth++) {
                List<Address> next = new ArrayList<>();
                for (Address target : layer) {
                    if (!seen.add(target)) continue;
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(target);
                    while (refs.hasNext()) {
                        Reference reference = refs.next();
                        Address from = reference.getFromAddress();
                        Function function = getFunctionContaining(from);
                        Map<String, Object> edge = new LinkedHashMap<>();
                        edge.put("from", from.toString());
                        edge.put("to", target.toString());
                        edge.put("reference_type", reference.getReferenceType().toString());
                        edge.put("depth", depth);
                        if (function != null) {
                            functions.add(function);
                            edge.put("function", function.getName());
                            edge.put("function_entry", function.getEntryPoint().toString());
                        } else {
                            next.add(from);
                        }
                        Instruction instruction = getInstructionAt(from);
                        if (instruction != null) {
                            List<String> assembly = new ArrayList<>();
                            for (int i = 0; i < 10 && instruction != null; i++, instruction = instruction.getNext()) {
                                assembly.add(instruction.getAddress().toString() + " " + instruction.toString());
                            }
                            edge.put("assembly", assembly);
                        }
                        edges.add(edge);
                    }
                }
                layer = next;
            }
            item.put("reference_edges", edges);
            imports.add(item);
        }
        report.put("fcb_imports", imports);
        Path output = Path.of(getScriptArgs()[0]);
        Files.createDirectories(output);
        // Export the actual callers and their immediate callers for patch review.
        for (Function function : new ArrayList<>(functions)) {
            functions.addAll(function.getCallingFunctions(monitor));
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            decompiler.openProgram(currentProgram);
            for (Function function : functions) {
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                String stem = function.getEntryPoint().toString();
                if (result.decompileCompleted()) {
                    Files.writeString(output.resolve(stem + ".c"), result.getDecompiledFunction().getC());
                }
                List<String> assembly = new ArrayList<>();
                for (Instruction instruction : currentProgram.getListing().getInstructions(function.getBody(), true)) {
                    assembly.add(instruction.getAddress() + " " + instruction);
                }
                Files.writeString(output.resolve(stem + ".asm"), String.join("\n", assembly) + "\n");
            }
        } finally {
            decompiler.dispose();
        }
        Files.writeString(output.resolve("fcb-access.json"),
            new GsonBuilder().setPrettyPrinting().create().toJson(report) + "\n");
        println("FCB import reference trace exported");
    }
}

// Targeted review after independent PEF/import mapping; no target execution.
// @category FreddiFisk
import com.google.gson.GsonBuilder;
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.SourceType;
import java.math.BigInteger;
import java.nio.file.*;
import java.util.*;

public class ReviewCloseRoutine extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getLanguageID().toString().equals("PowerPC:BE:32:default")) {
            throw new IllegalStateException("Incorrect CPU language");
        }
        String hash = currentProgram.getExecutableSHA256().toLowerCase(Locale.ROOT);
        if (!hash.equals("aa981103cd36cd9598da22d9ca1e3eca6ad59147dd5a9e7cc449e6a9d665a960") &&
            !hash.equals("ed76d3c0da7cb8063ac4f9fd529ee5b0ec014c7a1c71852c34375acd40b24409")) {
            throw new IllegalStateException("Close-routine offsets are specific to the verified Freddi edition and v1 patch");
        }
        Path output = Path.of(getScriptArgs()[0]);
        Files.createDirectories(output);
        // The native TOC comes from the PEF main transition vector, not Ghidra's
        // synthetic _toc label. Addresses below were verified from import-run
        // relocations and each stub's lwz r12,displacement(r2).
        currentProgram.getProgramContext().setValue(currentProgram.getRegister("r2"),
            toAddr(0x10000000), toAddr(0x1005415f), BigInteger.valueOf(0x20008000));
        Map<Long, String> APIs = new LinkedHashMap<>();
        APIs.put(0x10000c78L, "LMGetFCBSPtr");
        APIs.put(0x10000dc8L, "PBGetFCBInfoSync");
        APIs.put(0x10001938L, "PBHGetVInfoSync");
        APIs.put(0x10000c90L, "PBCloseSync");
        APIs.put(0x10000bd0L, "PBDeleteSync");
        APIs.put(0x10000ca8L, "PBHDeleteSync");
        APIs.put(0x10000cc0L, "PBFlushVolSync");
        APIs.put(0x10000bb8L, "PBGetFInfoSync");
        for (Map.Entry<Long, String> item : APIs.entrySet()) {
            Address address = toAddr(item.getKey());
            disassemble(address);
            Function function = getFunctionAt(address);
            if (function == null) function = createFunction(address, item.getValue());
            function.setName(item.getValue(), SourceType.USER_DEFINED);
            if (item.getValue().startsWith("PB")) {
                function.setReturnType(ShortDataType.dataType, SourceType.USER_DEFINED);
                function.replaceParameters(Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
                    true, SourceType.USER_DEFINED,
                    new ParameterImpl("pb", PointerDataType.dataType, currentProgram));
            }
        }
        Address start = toAddr(0x10005b2c), end = toAddr(0x10005c7f);
        disassemble(start);
        Function function = getFunctionAt(start);
        if (function == null) function = createFunction(start, "CloseFreddiFile");
        function.setName("CloseFreddiFile", SourceType.USER_DEFINED);
        function.setBody(new AddressSet(start, end));
        function.setReturnType(ShortDataType.dataType, SourceType.USER_DEFINED);
        function.replaceParameters(Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
            true, SourceType.USER_DEFINED,
            new ParameterImpl("file", PointerDataType.dataType, currentProgram));
        List<String> assembly = new ArrayList<>();
        for (Instruction instruction : currentProgram.getListing().getInstructions(function.getBody(), true)) {
            assembly.add(instruction.getAddress() + " " + instruction);
        }
        Files.writeString(output.resolve("ghidra-close.asm"), String.join("\n", assembly) + "\n");
        DecompInterface decompiler = new DecompInterface();
        DecompileResults result;
        try {
            if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException(decompiler.getLastMessage());
            result = decompiler.decompileFunction(function, 30, monitor);
            if (result.decompileCompleted()) Files.writeString(output.resolve("ghidra-close.c"),
                result.getDecompiledFunction().getC().replaceAll("(?m)[ \\t]+$", "").strip() + "\n");
        } finally {
            decompiler.dispose();
        }
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("language", currentProgram.getLanguageID().toString());
        report.put("executable_sha256", currentProgram.getExecutableSHA256());
        report.put("routine_address", start.toString());
        report.put("decompiled", result.decompileCompleted());
        report.put("diagnostic", result.getErrorMessage());
        report.put("toc_assumption", "20008000, independently mapped from original PEF transition vector");
        Files.writeString(output.resolve("ghidra-close.json"), new GsonBuilder().setPrettyPrinting().create().toJson(report) + "\n");
    }
}

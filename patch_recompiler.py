import os, re

DS = "DuckStation"  # SIE workflow clones to DuckStation (capital D)

def rd(p):
    if not os.path.exists(p): return ""
    with open(p, "r", encoding="utf-8", errors="replace") as f: return f.read()

def wr(p, c):
    d = os.path.dirname(p)
    if d: os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(c)

# === 1. Add ScaleZRegister to sie.h ===
sie_h = DS + "/src/core/sise/sie.h"
c = rd(sie_h)
if c and "ScaleZRegister" not in c:
    # Add declaration before the closing namespace brace
    # Find the last } in the file (namespace closing)
    if "} // namespace SIE" in c:
        c = c.replace("} // namespace SIE",
            "u32 ScaleZRegister(u32 idx, u32 value);\n} // namespace SIE")
    elif "}\n" in c and "namespace SIE" in c:
        # Generic: add before last }
        idx = c.rfind("}")
        c = c[:idx] + "u32 ScaleZRegister(u32 idx, u32 value);\n" + c[idx:]
    
    # Add extern C wrapper at end of file
    c += '\n\nextern "C" {\n    u32 SIE_ScaleZ_Helper(u32 idx, u32 value);\n}\n'
    wr(sie_h, c)
    print("OK: sie.h patched with ScaleZRegister + extern C")
else:
    print("SKIP: sie.h already has ScaleZRegister or file not found")

# === 2. Add ScaleZRegister implementation to sie.cpp ===
sie_cpp = DS + "/src/core/sise/sie.cpp"
c = rd(sie_cpp)
if c and "ScaleZRegister" not in c:
    # Find the namespace closing and add before it
    if "} // namespace SIE" in c:
        impl = """
u32 ScaleZRegister(u32 idx, u32 value) {
    if (!g_enabled || g_z_scale <= 1)
        return value;
    if (idx == 7 || (idx >= 16 && idx <= 19)) {
        u16 z = static_cast<u16>(value & 0xFFFF);
        if (z > 100) {
            z = static_cast<u16>(z / g_z_scale);
            if (z < 1) z = 1;
        }
        return (value & 0xFFFF0000) | z;
    }
    return value;
}

"""
        c = c.replace("} // namespace SIE", impl + "} // namespace SIE")
    wr(sie_cpp, c)
    print("OK: sie.cpp patched with ScaleZRegister implementation")
else:
    print("SKIP: sie.cpp already has ScaleZRegister or file not found")

# Add extern C wrapper at end of sie.cpp
c = rd(sie_cpp)
if c and "SIE_ScaleZ_Helper" not in c:
    c += '\nextern "C" u32 SIE_ScaleZ_Helper(u32 idx, u32 value) {\n    return SIE::ScaleZRegister(idx, value);\n}\n'
    wr(sie_cpp, c)
    print("OK: sie.cpp patched with SIE_ScaleZ_Helper extern C wrapper")

# === 3. Patch cpu_recompiler_codegen.cpp for MFC2 ===
codegen = DS + "/src/core/cpu_recompiler_codegen.cpp"
c = rd(codegen)
if c and "SIE_ScaleZ_Helper" not in c:
    # Find MFC2 case — look for the pattern where GTE::ReadRegister is called
    # The exact pattern varies by DuckStation version
    # Look for: case MFC2: or case MFC2_RAW:
    
    # Try to find the MFC2 handler
    mfc2_patterns = [
        # Pattern 1: Standard MFC2 with GTE::ReadRegister
        'case MFC2:',
        'case MFC2_RAW:',
        'case COP2::MFC2:',
    ]
    
    found_mfc2 = False
    for pat in mfc2_patterns:
        idx = c.find(pat)
        if idx >= 0:
            # Find the next line after the case that has ReadRegister or similar
            # Insert SIE scaling after the value is read
            # We need to find where val is obtained and insert scaling after it
            
            # Simple approach: add SIE include at top and a scaling call
            # after the GTE read in the MFC2 case
            
            # Find the end of the MFC2 case (next case or break)
            case_end = c.find("break;", idx)
            if case_end < 0:
                case_end = c.find("case ", idx + len(pat))
            
            if case_end > idx:
                # Insert SIE scaling before break
                insert_point = case_end
                sie_code = """
    // SIE Z-scaling: scale SZ/OTZ registers
    {
        Value sie_idx = ConstantPC(static_cast<u32>(inst.r.rd.GetValue()));
        val = CallFunction(&SIE_ScaleZ_Helper, sie_idx, val);
    }
"""
                c = c[:insert_point] + sie_code + c[insert_point:]
                found_mfc2 = True
                print(f"OK: MFC2 patched at pattern '{pat}'")
                break
    
    if not found_mfc2:
        print("WARN: MFC2 case not found in cpu_recompiler_codegen.cpp")
        # Try broader search
        if "MFC2" in c:
            print("  MFC2 exists in file but pattern not matched")
            # Show context around first MFC2
            idx = c.find("MFC2")
            print(f"  Context: {repr(c[idx:idx+200])}")
        else:
            print("  MFC2 not found at all — DuckStation may use different naming")

# === 4. Add SIE include to codegen ===
c = rd(codegen)
if c and "sise/sie.h" not in c and "SIE_ScaleZ_Helper" in c:
    # Add include after the last include
    last_include = c.rfind('#include "')
    if last_include >= 0:
        end_line = c.find('\n', last_include)
        c = c[:end_line+1] + '#include "sise/sie.h"\n' + c[end_line+1:]
        wr(codegen, c)
        print("OK: sise/sie.h include added to cpu_recompiler_codegen.cpp")

print("=== Recompiler patch complete ===")

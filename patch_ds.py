import os, re

DS = "duckstation"

def rd(p):
    if not os.path.exists(p): return ""
    with open(p, "r", encoding="utf-8", errors="replace") as f: return f.read()

def wr(p, c):
    d = os.path.dirname(p)
    if d: os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(c)

def patch(path, anchor, ins, after=True):
    c = rd(path)
    if ins.strip() in c: return
    i = c.find(anchor)
    if i < 0:
        print("  WARN: " + path + ": anchor not found: " + anchor[:60])
        return
    if after:
        e = c.find("\n", i) + 1
        c = c[:e] + ins + "\n" + c[e:]
    else:
        c = c[:i] + ins + "\n" + c[i:]
    wr(path, c)
    print("  OK: " + os.path.basename(path))

# system.h
patch(DS + "/src/core/system.h", "bool IsReplayingGPUDump();",
      "// RSIL\nnamespace rsil { class RSILSubsystem; }\nrsil::RSILSubsystem* GetRSIL();")

# system.cpp includes
patch(DS + "/src/core/system.cpp", '#include "gpu_dump.h"',
      '// RSIL\n#include "rsil/RSILSubsystem.h"\n#include "rsil/Config.h"\n#include "duckstation/DuckStationHostAdapter.h"\n#include "gpu_dump.h"', after=False)

# s_state member
c = rd(DS + "/src/core/system.cpp")
if "std::unique_ptr<::rsil::RSILSubsystem> rsil;" not in c:
    c = c.replace("u32 frame_number = 0;", "u32 frame_number = 0;\n  std::unique_ptr<::rsil::RSILSubsystem> rsil;", 1)
    wr(DS + "/src/core/system.cpp", c)
    print("  OK: s_state.rsil")

# GetRSIL
patch(DS + "/src/core/system.cpp", "return s_state.frame_number;",
      "return s_state.frame_number;\n}\n\nrsil::RSILSubsystem* System::GetRSIL()\n{\n  return s_state.rsil.get(); // returns ::rsil::RSILSubsystem*")

# Initialize
patch(DS + "/src/core/system.cpp", "s_state.state = State::Running;",
      "s_state.state = State::Running;\n  // RSIL\n  if (!s_state.rsil) {\n    rsil::RSILConfig cfg = rsil::RSILConfig::defaults();\n    static rsil::DuckStationHostAdapter s_host;\n    s_state.rsil = rsil::RSILSubsystem::create(std::move(cfg), s_host, nullptr, nullptr);\n  }\n  if (s_state.rsil) {\n    s_state.rsil->set_scan_deferred(true);\n    GTE::SetRSILZScale(0.5f);\n    GTE::SetRSILZScaleActive(true);")

# DestroySystem
c = rd(DS + "/src/core/system.cpp")
if "s_state.rsil.reset()" not in c:
    c = c.replace("void System::DestroySystem()\n{", "void System::DestroySystem()\n{\n  s_state.rsil.reset();", 1)
    wr(DS + "/src/core/system.cpp", c)
    print("  OK: DestroySystem")

# FrameDone
c = rd(DS + "/src/core/system.cpp")
if "Auto-activate Enhanced mode" not in c:
    c = c.replace("void System::FrameDone()\n{",
      'void System::FrameDone()\n{\n  // RSIL: Auto-activate Enhanced mode after scan finds patches.\n  if (s_state.rsil) [[unlikely]]\n  {\n    s_state.rsil->Pump(s_state.frame_number);\n    if (s_state.rsil->scan_deferred() && Bus::g_ram && Bus::g_ram_size > 0)\n    {\n      if (Bus::g_ram_code_bits.any())\n      {\n        std::vector<u8> snap(Bus::g_ram, Bus::g_ram + std::min<u32>(Bus::g_ram_size, 0x200000));\n        s_state.rsil->auto_discover_patches(snap);\n        s_state.rsil->set_scan_deferred(false);\n        if (s_state.rsil->scan_stats().total_candidates > 0)\n        {\n          static rsil::DuckStationRamAccess s_ram;\n          s_state.rsil->set_emulation_mode(rsil::EmulationMode::Enhanced, &s_ram, "");\n        }\n      }\n    }\n  }', 1)
    wr(DS + "/src/core/system.cpp", c)
    print("  OK: FrameDone")

# gpu.cpp
patch(DS + "/src/core/gpu.cpp", '#include "video_thread_commands.h"',
      '#include "video_thread_commands.h"\n// RSIL\n#include "rsil/RSILSubsystem.h"', after=False)
c = rd(DS + "/src/core/gpu.cpp")
if "RSIL: tap GP0" not in c:
    c = c.replace("s_locals.fifo.Push(value);\n      ExecuteCommands();",
      "s_locals.fifo.Push(value);\n      // RSIL: tap GP0\n      if (rsil::RSILSubsystem* rs = System::GetRSIL()) [[unlikely]]\n        rs->GetTap().emit_gpu_command(0, value, System::GetFrameNumber());\n      ExecuteCommands();", 1)
    wr(DS + "/src/core/gpu.cpp", c)
    print("  OK: GP0 tap")

# imgui_overlays.cpp
patch(DS + "/src/core/imgui_overlays.cpp", '#include "system.h"',
      '#include "system.h"\n// RSIL\n#include "rsil/RSILSubsystem.h"', after=False)
c = rd(DS + "/src/core/imgui_overlays.cpp")
if "RSIL: draw overlay" not in c:
    c = c.replace("void ImGuiManager::RenderDebugWindows()\n{",
      "void ImGuiManager::RenderDebugWindows()\n{\n  // RSIL: draw overlay\n  if (System::IsValid() && System::GetRSIL())\n    System::GetRSIL()->DrawOverlay();", 1)
    wr(DS + "/src/core/imgui_overlays.cpp", c)
    print("  OK: overlay")

# gte.h
patch(DS + "/src/core/gte.h", "} // namespace GTE",
      "// RSIL: GTE Z-scale\nvoid SetRSILZScale(float scale);\nvoid SetRSILZScaleActive(bool active);", after=False)

# gte.cpp
c = rd(DS + "/src/core/gte.cpp")
if "SetRSILZScale" not in c:
    c = c.replace("} // namespace GTE",
      "// RSIL: GTE Z-scale\nstatic float s_rsil_zs = 1.0f; static bool s_rsil_zs_a = false;\nvoid GTE::SetRSILZScale(float s) { s_rsil_zs = s; }\nvoid GTE::SetRSILZScaleActive(bool a) { s_rsil_zs_a = a; }\n} // namespace GTE", 1)
    wr(DS + "/src/core/gte.cpp", c)
    print("  OK: GTE Z-scale")


# Fix DebugOverlay.cpp: const bool* → bool* for ImGui::Begin
do_path = DS + "/dep/rsil/src/DebugOverlay.cpp"
c = rd(do_path)
if "const_cast<bool*>(&cfg_.flags.overlay)" not in c:
    c = c.replace("&cfg_.flags.overlay", "const_cast<bool*>(&cfg_.flags.overlay)")
    wr(do_path, c)
    print("  OK: DebugOverlay.cpp const_cast fix")


# Fix RSILSubsystem.cpp: INFO_LOG is a DuckStation macro not available to RSIL
rsilsub = DS + "/dep/rsil/src/RSILSubsystem.cpp"
c = rd(rsilsub)
if "INFO_LOG" in c and "rsil_log" not in c:
    c = c.replace("INFO_LOG(", "printf(")
    wr(rsilsub, c)
    print("  OK: RSILSubsystem.cpp INFO_LOG -> printf")

# Generate rsil.vcxproj
vcxproj = '''<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup Label="ProjectConfigurations">
    <ProjectConfiguration Include="Debug|x64"><Configuration>Debug</Configuration><Platform>x64</Platform></ProjectConfiguration>
    <ProjectConfiguration Include="Release|x64"><Configuration>Release</Configuration><Platform>x64</Platform></ProjectConfiguration>
    <ProjectConfiguration Include="Debug|Win32"><Configuration>Debug</Configuration><Platform>Win32</Platform></ProjectConfiguration>
    <ProjectConfiguration Include="Release|Win32"><Configuration>Release</Configuration><Platform>Win32</Platform></ProjectConfiguration>
    <ProjectConfiguration Include="Debug|ARM64"><Configuration>Debug</Configuration><Platform>ARM64</Platform></ProjectConfiguration>
    <ProjectConfiguration Include="Release|ARM64"><Configuration>Release</Configuration><Platform>ARM64</Platform></ProjectConfiguration>
  </ItemGroup>
  <Import Project="..\\vsprops\\Configurations.props" />
  <ItemGroup>
    <ClCompile Include="src\\AdjacencyGraph.cpp" /><ClCompile Include="src\\ClusterSignature.cpp" />
    <ClCompile Include="src\\DebugOverlay.cpp" /><ClCompile Include="src\\GpuPacketParser.cpp" />
    <ClCompile Include="src\\HeadlessPrePass.cpp" /><ClCompile Include="src\\HostPreRegistrar.cpp" />
    <ClCompile Include="src\\MipsPatternScanner.cpp" /><ClCompile Include="src\\Persistence.cpp" />
    <ClCompile Include="src\\Predictor.cpp" /><ClCompile Include="src\\RSILSubsystem.cpp" />
    <ClCompile Include="src\\ScenePatchLayer.cpp" /><ClCompile Include="src\\SpatialCatalog.cpp" />
    <ClCompile Include="src\\TelemetryTap.cpp" /><ClCompile Include="src\\Validator.cpp" />
          </ItemGroup>
  <PropertyGroup Label="Globals"><ProjectGuid>''' + os.environ.get("RSIL_GUID", "{B5E8D2F1-3A4C-4E6F-9B7A-1C2D3E4F5A6B}") + '''</ProjectGuid></PropertyGroup>
  <Import Project="..\\vsprops\\StaticLibrary.props" />
  <ItemDefinitionGroup><ClCompile>
    <AdditionalIncludeDirectories>$(ProjectDir)\\include;$(SolutionDir)src;$(SolutionDir)dep\\imgui\\include;$(SolutionDir)dep\\imgui;$(SolutionDir)dep\prebuilt\windows-x64\include;%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>
    <PreprocessorDefinitions>RSIL_DUCKSTATION_INTEGRATED;RSIL_HAS_SQLITE=1;RSIL_HAS_IMGUI=1;%(PreprocessorDefinitions)</PreprocessorDefinitions>
    <LanguageStandard>stdcpp20</LanguageStandard><ConformanceMode>false</ConformanceMode>
    <DisableSpecificWarnings>4244;4267;4146;4458;4324</DisableSpecificWarnings>
  </ClCompile></ItemDefinitionGroup>
  <Import Project="..\\vsprops\\Targets.props" />
</Project>
'''
wr(DS + "/dep/rsil/rsil.vcxproj", vcxproj)
print("  OK: rsil.vcxproj generated")

# Patch .sln
guid = os.environ.get("RSIL_GUID", "{B5E8D2F1-3A4C-4E6F-9B7A-1C2D3E4F5A6B}")
with open(DS + "/duckstation.sln", "r") as f: sln = f.read()
if "rsil.vcxproj" not in sln:
    pe = '\nProject("{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}") = "rsil", "dep\\rsil\\rsil.vcxproj", "' + guid + '"\nEndProject\n'
    sln = re.sub(r'(Project\([^}]+\{BA490C0E[^}]+\}[^)]*\)[^\n]*\nEndProject)', lambda m: m.group(1) + pe, sln)
    cfg = ""
    for c in ["Debug|ARM64","Debug|x64","Debug|Win32","Debug-Clang|ARM64","Debug-Clang|x64","Debug-Clang|Win32","Debug-Clang-SSE2|ARM64","Debug-Clang-SSE2|x64","Debug-Clang-SSE2|Win32","DebugFast|ARM64","DebugFast|x64","DebugFast|Win32","DebugFast-Clang|ARM64","DebugFast-Clang|x64","DebugFast-Clang|Win32","Devel-Clang|ARM64","Devel-Clang|x64","Devel-Clang|Win32","Release|ARM64","Release|x64","Release|Win32","Release-Clang|ARM64","Release-Clang|x64","Release-Clang|Win32","ReleaseLTCG|ARM64","ReleaseLTCG|x64","ReleaseLTCG|Win32","ReleaseLTCG-Clang|ARM64","ReleaseLTCG-Clang|x64","ReleaseLTCG-Clang|Win32"]:
        config, plat = c.split("|")
        target = "Debug|x64" if ("Debug" in config or "Devel" in config) else "Release|x64"
        cfg += "\t" + guid + "." + c + ".ActiveCfg = " + target + "\n"
        if plat == "x64":
            cfg += "\t" + guid + "." + c + ".Build.0 = " + target + "\n"
    sln = re.sub(r"(GlobalSection\(ProjectConfigurationPlatforms\)[^\n]*\n)", lambda m: m.group(1) + cfg, sln)
    with open(DS + "/duckstation.sln", "w") as f: f.write(sln)
    print("  OK: .sln patched")

# Patch core.vcxproj
with open(DS + "/src/core/core.vcxproj", "r") as f: p = f.read()
if "rsil" not in p:
    p = p.replace("dep\\fast_float\\include;", "dep\\fast_float\\include;$(SolutionDir)dep\\rsil\\include;")
    p = p.replace("</ProjectReference>", '</ProjectReference>\n    <ProjectReference Include="..\\..\\dep\\rsil\\rsil.vcxproj"></ProjectReference>', 1)
    with open(DS + "/src/core/core.vcxproj", "w") as f: f.write(p)
    print("  OK: core.vcxproj patched")

print("=== ALL PATCHES APPLIED ===")

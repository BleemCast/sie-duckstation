// SPDX-License-Identifier: BSD-3-Clause
// SIE v0.8 — Static MIPS Scanner only (Z-scaling disabled)
// On-the-fly toggle support: reads settings every frame, toggles instantly.
#include <cmath>

#include "sise/sie.h"

#include "common/log.h"
#include "core/bus.h"
#include "core/core.h"
#include "core/cpu_core.h"
#include "core/settings.h"
#include "core/system.h"

#include <algorithm>
#include <cstring>
#include <vector>

LOG_CHANNEL(GPU);

namespace SIE {

bool g_enabled = false;
u32 g_z_scale = 1;
u32 g_z_scale_threshold = 200;

// Static analysis state
static bool m_scan_done = false;
static u32 s_patch_addr = 0;
static u32 s_patch_word = 0;
static u32 s_original_word = 0;  // Saved for restore on toggle-off
static bool s_was_enabled = false;

// MIPS helpers
static inline u32 bits(u32 w, int hi, int lo) {
  return (w >> lo) & ((1u << (hi - lo + 1)) - 1);
}
static inline s16 imm16(u32 w) { return static_cast<s16>(bits(w, 15, 0)); }
static inline bool is_branch(u32 w) {
  u32 op = bits(w, 31, 26);
  u32 rt = bits(w, 20, 16);
  if (op >= 0x04 && op <= 0x07) return true;
  if (op == 0x01 && (rt == 0x00 || rt == 0x01)) return true;
  if (op == 0x11 && bits(w, 25, 21) == 0x08) return true;
  return false;
}
static bool has_branch_near(const u8* ram, u32 offset, u32 size, int max_dist) {
  for (int j = 1; j <= max_dist; j++) {
    u32 off = offset + static_cast<u32>(j * 4);
    if (off + 4 > size) break;
    u32 w;
    std::memcpy(&w, ram + off, 4);
    if (is_branch(w)) return true;
  }
  return false;
}

static void run_static_scan() {
  const u8* ram = Bus::g_ram;
  const u32 ram_size = Bus::g_ram_size;
  if (!ram || ram_size == 0) { m_scan_done = true; return; }

  u32 num_pages = ram_size >> 12;
  for (u32 page = 0; page < num_pages; page++) {
    if (!Bus::IsRAMCodePage(page)) continue;
    u32 start = page << 12;
    u32 end = std::min(start + 4096, ram_size);

    for (u32 i = start; i + 16 <= end && i + 16 <= ram_size; i += 4) {
      u32 word;
      std::memcpy(&word, ram + i, 4);
      u32 op = bits(word, 31, 26);

      // slti/sltiu with value 50-1000 + branch
      if (op == 0x0A || op == 0x0B) {
        s16 imm = imm16(word);
        if (imm >= 50 && imm <= 1000 && has_branch_near(ram, i, ram_size, 4)) {
          u32 rs = bits(word, 25, 21), rt = bits(word, 20, 16);
          u32 patch = (op << 26) | (rs << 21) | (rt << 16) | (32767 & 0xFFFF);
          u32 addr = 0x80000000 | i;
          s_original_word = word;
          if (CPU::SafeWriteMemoryWord(addr, patch)) {
            s_patch_addr = addr;
            s_patch_word = patch;
            INFO_LOG("SIE: patched slti at 0x{:08X} (val={} -> 32767)", addr, imm);
            m_scan_done = true;
            return;
          }
        }
      }

      // addiu with negative immediate + bltz
      if (op == 0x09) {
        s16 imm = imm16(word);
        if (imm < 0 && std::abs(imm) >= 50 && std::abs(imm) <= 1000) {
          u32 rt = bits(word, 20, 16);
          if (i + 4 < ram_size) {
            u32 nw;
            std::memcpy(&nw, ram + i + 4, 4);
            if (bits(nw, 31, 26) == 0x01 && bits(nw, 20, 16) <= 0x01 && bits(nw, 25, 21) == rt) {
              u32 rs = bits(word, 25, 21);
              u32 patch = (0x09 << 26) | (rs << 21) | (rt << 16) | ((-32767) & 0xFFFF);
              u32 addr = 0x80000000 | i;
              s_original_word = word;
              if (CPU::SafeWriteMemoryWord(addr, patch)) {
                s_patch_addr = addr;
                s_patch_word = patch;
                INFO_LOG("SIE: patched addiu+bltz at 0x{:08X} (val={} -> 32767)", addr, std::abs(imm));
                m_scan_done = true;
                return;
              }
            }
          }
        }
      }
    }
  }
  INFO_LOG("SIE: static scan found no patchable culling instructions");
  m_scan_done = true;
}

static void restore_patch() {
  if (s_patch_addr != 0 && s_original_word != 0) {
    CPU::SafeWriteMemoryWord(s_patch_addr, s_original_word);
    INFO_LOG("SIE: restored original instruction at 0x{:08X}", s_patch_addr);
  }
  s_patch_addr = 0;
  s_patch_word = 0;
  s_original_word = 0;
}

float Vec3f::DistanceTo(const Vec3f& o) const {
  return std::sqrt((x-o.x)*(x-o.x) + (y-o.y)*(y-o.y) + (z-o.z)*(z-o.z));
}

SIEEngine::SIEEngine() = default;
SIEEngine::~SIEEngine() = default;

SIEEngine& SIEEngine::Get() {
  static SIEEngine instance;
  return instance;
}

bool SIEEngine::IsScanDone() const { return m_scan_done; }

void SIEEngine::Initialize() {
  std::lock_guard<std::mutex> lock(m_mutex);
  ReloadSettings();
  s_was_enabled = m_settings.enabled;
  g_enabled = m_settings.enabled;
  g_z_scale = m_settings.z_scale_enabled ? static_cast<u32>(m_settings.z_scale_factor) : 1;
  if (g_z_scale < 1) g_z_scale = 1;
  g_z_scale_threshold = m_settings.z_scale_threshold;
  INFO_LOG("SIE v0.9: initialized (enabled={}, z_scale={}, threshold={})",
           m_settings.enabled, g_z_scale, g_z_scale_threshold);
  m_scan_done = false;
  s_patch_addr = 0;
  s_patch_word = 0;
  s_original_word = 0;
  m_state = m_settings.enabled ? State::Active : State::Disabled;
}

void SIEEngine::Shutdown() {
  std::lock_guard<std::mutex> lock(m_mutex);
  restore_patch();
  g_enabled = false;
  m_scan_done = false;
  s_was_enabled = false;
  m_state = State::Disabled;
}

void SIEEngine::ReloadSettings() {
  m_settings.enabled = Core::GetBaseBoolSettingValue("sise", "enabled", false);
  m_settings.z_scale_factor = Core::GetBaseFloatSettingValue("sise", "z_scale_factor", 4.0f);
  m_settings.z_scale_enabled = Core::GetBaseBoolSettingValue("sise", "z_scale_enabled", false);
  m_settings.z_scale_threshold = Core::GetBaseUIntSettingValue("sise", "z_scale_threshold", 200);
  m_settings.show_overlay = Core::GetBaseBoolSettingValue("sise", "show_overlay", true);
}

void SIEEngine::OnFrameEnd() {
  // On-the-fly toggle: reload settings every frame
  bool new_enabled = Core::GetBaseBoolSettingValue("sise", "enabled", false);

  if (new_enabled != s_was_enabled) {
    s_was_enabled = new_enabled;
    g_enabled = new_enabled;
    // Reload z_scale setting on toggle
    bool zs = Core::GetBaseBoolSettingValue("sise", "z_scale_enabled", false);
    float zsf = Core::GetBaseFloatSettingValue("sise", "z_scale_factor", 4.0f);
    g_z_scale = (new_enabled && zs) ? static_cast<u32>(zsf) : 1;
    if (g_z_scale < 1) g_z_scale = 1;
    g_z_scale_threshold = Core::GetBaseUIntSettingValue("sise", "z_scale_threshold", 200);
    if (new_enabled) {
      m_scan_done = false;
      s_patch_addr = 0;
      s_patch_word = 0;
      s_original_word = 0;
      m_state = State::Active;
      INFO_LOG("SIE: toggled ON (z_scale={})", g_z_scale);
    } else {
      // Just turned off — restore original instruction
      restore_patch();
      m_scan_done = false;
      m_state = State::Disabled;
      INFO_LOG("SIE: toggled OFF at runtime");
    }
  }

  if (!g_enabled) return;

  // Run static scan on first frame after game code loads
  if (!m_scan_done) {
    const u32 num_pages = Bus::g_ram_size >> 12;
    bool has_code = false;
    for (u32 i = 0; i < num_pages && i < Bus::g_ram_code_bits.size(); i++) {
      if (Bus::g_ram_code_bits[i]) { has_code = true; break; }
    }
    if (has_code) {
      run_static_scan();
    }
  }

  // Re-apply MIPS patch if game overwrote it
  if (s_patch_addr != 0 && s_patch_word != 0) {
    u32 current;
    if (CPU::SafeReadMemoryWord(s_patch_addr, &current) && current != s_patch_word) {
      CPU::SafeWriteMemoryWord(s_patch_addr, s_patch_word);
    }
  }
}

}  // namespace SIE

#ifdef WITH_SISE
extern "C" void SIE_CaptureGTE() {}

// SIE_ScaleZ — called by the x86-64 / ARM recompiler after every MFC2 and
// before every SWC2. Divides the Z of SZ0-SZ3 (idx 16-19) and OTZ (idx 7)
// by g_z_scale so the game's far-clip comparison sees a smaller depth and
// does not cull distant geometry (eliminates pop-in). Values <= 200 are
// left untouched to protect near OT buckets. The high 16 bits are preserved.
extern "C" u32 SIE_ScaleZ(u32 idx, u32 original_z)
{
  if (!SIE::g_enabled || SIE::g_z_scale <= 1)
    return original_z;

  // Only scale Z registers: OTZ (7) and SZ0-SZ3 (16-19)
  if (idx != 7 && (idx < 16 || idx > 19))
    return original_z;

  u16 z = static_cast<u16>(original_z & 0xFFFF);
  if (z <= SIE::g_z_scale_threshold)  // protect near geometry / OT buckets
    return original_z;

  z = static_cast<u16>(z / SIE::g_z_scale);
  if (z < 1)
    z = 1;

  return (original_z & 0xFFFF0000u) | static_cast<u32>(z);
}
#endif

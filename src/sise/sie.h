// SPDX-License-Identifier: BSD-3-Clause
// SIE v0.6 — GTE Z-Scaling
// Decouples the Z used for perspective from the Z used for culling.
// The GTE already computed screen coords with real Z. We scale Z on read
// so the game's culling comparison sees a smaller depth → doesn't cull.
// No MIPS patching. No code scanning. One GTE register hook. Universal.
#pragma once

#include "common/types.h"
#include <mutex>

namespace SIE {

struct Settings {
  bool enabled = false;
  float z_scale_factor = 1.0f;       // 1 = disabled. 4 = 4x draw distance.
  bool z_scale_enabled = false;      // Separate toggle for Z-scaling (can garble some games)
  u32 z_scale_threshold = 200;       // Don't scale Z below this (near geometry OT safety)
  bool show_overlay = true;
};

struct Vec3f {
  float x, y, z;
  float DistanceTo(const Vec3f& o) const;
};

class SIEEngine {
public:
  static SIEEngine& Get();
  void Initialize();
  void Shutdown();
  void ReloadSettings();
  void OnFrameEnd();

  enum class State : u8 { Disabled, Active };
  State GetState() const { return m_state; }
  const Settings& GetSettings() const { return m_settings; }
  bool IsScanDone() const;

private:
  SIEEngine();
  ~SIEEngine();
  SIEEngine(const SIEEngine&) = delete;
  SIEEngine& operator=(const SIEEngine&) = delete;

  Settings m_settings;
  std::mutex m_mutex;
  State m_state = State::Disabled;
};

extern bool g_enabled;
extern u32 g_z_scale;             // Integer scale factor (1 = disabled, 4 = 4x draw distance)
extern u32 g_z_scale_threshold;   // Don't scale Z at or below this (protects near OT buckets)

}  // namespace SIE

#ifdef WITH_SISE
extern "C" void SIE_CaptureGTE();

// SIE_ScaleZ: called by the recompiler after every MFC2 (GTE -> CPU register)
// and before every SWC2 memory store. Scales the Z value of SZ0-SZ3 / OTZ
// registers so the game's culling comparison sees a smaller depth, preventing
// far-clip pop-in. Returns original_z unchanged when SIE is disabled or the
// register is not a Z register. PGXP always receives the ORIGINAL value.
extern "C" u32 SIE_ScaleZ(u32 idx, u32 original_z);
#endif

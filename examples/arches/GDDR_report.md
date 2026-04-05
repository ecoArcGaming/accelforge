GDDR6-AiM AccelForge YAML Production Report

  Architectural Decision: Two Separate Specs

  Like LongSight, the GDDR6-AiM system is heterogeneous — a host CPU baseline vs. a
  processing-in-memory accelerator. These are modeled as two independent specs with results combined
   in the Python evaluation script. The same evaluate_mapping join limitation from LongSight
  applies, so both domains use map_workload_to_arch (auto-mapper).

  Data Sources

  Two sources were used:
  1. GDDDR.md — the paper description (Sections 1-4)
  2. aim_simulator/ — a Ramulator-based cycle-accurate simulator cloned into the repo, containing
  exact timing presets, power models, and memory organization in GDDR6.cpp and
  cellar_power_calculator.py

  Where the paper gave high-level specs and the simulator gave cycle-accurate parameters, the
  simulator values were preferred.

  ---
  1. gddr6aim_host.yaml (Architecture)

  Sources: GDDDR.md Section 4 (verification baseline) + standard Xeon specs.

  ┌─────────────┬──────────┬──────────────────────┬────────────────────────────────────────────┐
  │  Component  │  Value   │        Source        │                   Notes                    │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ HostDRAM    │ inf      │ Convention           │ Backing store                              │
  │ size        │          │                      │                                            │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ HostDRAM    │ 102.4    │ Paper: "4 channels   │                                            │
  │ bandwidth   │ GB/s     │ of DDR4-3200" → 4 ×  │                                            │
  │             │          │ 25.6 GB/s            │                                            │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ HostDRAM    │ 7.03     │ tpu_v4i.yaml DDR     │ Same energy model used across accelforge   │
  │ energy      │ pJ/bit   │ reference            │ examples                                   │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ L3_Cache    │ 28 MB    │ Xeon Gold 6230       │ 28 MB shared L3                            │
  │ size        │          │ datasheet            │                                            │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ L3_Cache    │          │ Estimated aggregate  │                                            │
  │ bandwidth   │ 300 GB/s │ L3 BW across 20      │                                            │
  │             │          │ cores                │                                            │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ L3_Cache    │ 0.8      │ Standard SRAM        │                                            │
  │ energy      │ pJ/bit   │ estimate at 14nm     │                                            │
  ├─────────────┼──────────┼──────────────────────┼────────────────────────────────────────────┤
  │ CPU_MAC     │ 1.34     │ Peak 2.688 TFlop/s × │ Peak: 20 cores × 2 FMA × 32 BF16 × 2.1     │
  │ throughput  │ TFlop/s  │  50% utilization     │ GHz. Matvec is memory-bandwidth-bound, so  │
  │             │          │                      │ ~50% efficiency is typical                 │
  └─────────────┴──────────┴──────────────────────┴────────────────────────────────────────────┘

  ---
  2. gddr6aim_aim.yaml (Architecture)

  Sources: GDDDR.md Section 1B + aim_simulator/src/dram/impl/GDDR6.cpp (organization and timing
  presets) + aim_simulator/scripts/cellar_power_calculator.py (energy model).

  Component: HostDRAM (PCIe)
  Value: 12.8 GB/s, 4.4 pJ/bit
  Source: Simulator: PCIE_ENERGY = 4.4 pJ/bit
  Derivation: PCIe Gen3 x16 ≈ 12.8 GB/s effective. Energy from cellar_power_calculator.py line 124
  ────────────────────────────────────────
  Component: FPGA_GPR
  Value: 512 KB
  Source: Paper Section 1A: "512 KB General Purpose Register"
  Derivation: Energy/BW estimated (FPGA BRAM ~100 GB/s, ~0.5 pJ/bit)
  ────────────────────────────────────────
  Component: ChannelArray
  Value: 32-way spatial
  Source: Simulator: CH_PER_DV = 32.00 (line 10); GDDR6_AiM_org preset: 32 channels
  Derivation: Jinja template N_CHANNELS defaults to 32
  ────────────────────────────────────────
  Component: AiM_GDDR6 size
  Value: 512 KB/ch
  Source: Simulator: 128 Mb total / 32 ch = 4 Mb = 512 KB per channel
  Derivation: GDDR6_AiM_org: "128 << 10" density
  ────────────────────────────────────────
  Component: AiM_GDDR6 bandwidth
  Value: 4 GB/s/ch
  Source: Simulator: 2 GHz clock, 256-bit burst, 2 beats. Total: 128 GB/s / 32 ch
  Derivation: Full speed 16 Gb/s/pin × 16 pins × 2 ch / 8 = 64 GB/s/chip
  ────────────────────────────────────────
  Component: AiM_GDDR6 energy
  Value: 5.5 pJ/bit
  Source: Simulator: DQ_ENERGY = 5.5 (line 123)
  Derivation: Data bus energy per bit transferred
  ────────────────────────────────────────
  Component: BankArray
  Value: 16-way spatial
  Source: Simulator: GDDR6_AiM_org: 4 bank groups × 4 banks/BG = 16 banks/channel
  Derivation:
  ────────────────────────────────────────
  Component: GlobalBuffer size
  Value: 2 KB
  Source: Paper Section 2A: "2KB Global Buffer"
  Derivation: 256-bit access width, SRAM
  ────────────────────────────────────────
  Component: GlobalBuffer energy
  Value: 0.55 fJ/bit read, 0.64 fJ/bit write
  Source: Simulator: SRAM_POWER["GB"] = {read: 0.279 mW, write: 0.325 mW}
  Derivation: Converted: 0.279 mW × 0.5 ns / 256 bits ≈ 0.55 fJ/bit
  ────────────────────────────────────────
  Component: GlobalBuffer leak
  Value: 0.067 mW
  Source: Simulator: SRAM_POWER["GB"]["STT"] = 0.06702
  Derivation: Static power per GB instance
  ────────────────────────────────────────
  Component: PU_MAC throughput
  Value: 32 GFlop/s per PU
  Source: Simulator: 1 MAC/cycle × 16 FP16 elements × 2 GHz = 32 GFlop/s
  Derivation: 512 PUs total → 1 TFLOPS system (matches paper Section 1B)
  ────────────────────────────────────────
  Component: PU_MAC energy
  Value: 0.1 pJ/op
  Source: Estimated from DRAM activation energy budget
  Derivation: Dominated by DRAM access, not compute logic

  Timing parameters available but not directly used in accelforge (from GDDR6.cpp):
  - nCL = 50 cycles (column access latency, folded into AiM_GDDR6 read latency)
  - nRCDRDMAC = 56 cycles (ACT-to-MAC, specific to PIM operations)
  - tRC = 44.5 ns, tBL = 1.25 ns (used in energy calculations)
  - nRCDRDAF = 86 cycles, nRCDEWMUL = 25 cycles (activation function / element-wise timings)

  Parameterization: The architecture uses Jinja templates for N_CHANNELS and FREQ_GHZ, allowing the
  evaluation script to model both full-speed (32ch, 2 GHz) and underclocked (4ch, 0.25 GHz)
  configurations from a single YAML file.

  ---
  3. gddr6aim_gpt3_13B.yaml (Workload)

  Sources: GDDDR.md Sections 2-3 + GPT-3 13B model specs.

  Model parameters: GPT-3 13B has d_model=5120, d_ff=20480, 40 layers, 40 heads.

  Rank sizes:

  ┌─────────┬─────────┬────────────────────┬──────────────┐
  │  Rank   │ Default │ Actual (GPT-3 13B) │    Ratio     │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ D_IN    │ 64      │ 5120               │ 1x           │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ D_QKV   │ 192     │ 15360              │ 3x           │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ D_OUT   │ 64      │ 5120               │ 1x           │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ D_FF    │ 256     │ 20480              │ 4x           │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ D_FINAL │ 64      │ 5120               │ 1x           │
  ├─────────┼─────────┼────────────────────┼──────────────┤
  │ M       │ 1       │ 1                  │ Decode phase │
  └─────────┴─────────┴────────────────────┴──────────────┘

  Why small defaults: AccelForge's mapper explores all possible loop tilings, and the search space
  grows combinatorially with rank sizes. At D=5120 and D_FF=20480, the mapper did not complete
  within several minutes. Defaults are scaled down to D=64 (80x smaller) maintaining the 1:3:1:4:1
  ratio. The evaluation script computes a MAC-count scale factor (actual_MACs / model_MACs) and
  multiplies all energy and latency results accordingly.

  Einsums:

  1. QKV — Fused query/key/value projection: [B,M,D] × [D,3D] → [B,M,3D]. Paper Section 2A describes
   the MAC operation processing 16 BF16 elements per column access.
  2. O — Output projection: [B,M,D] × [D,D] → [B,M,D]. Uses Attn_out as input (attention output, not
   chained from QKV) because QKV and O have different output dimensions (D_QKV vs D_OUT) and the
  attention computation between them is not modeled.
  3. FFN_up — Feed-forward up projection: [B,M,D] → [B,M,4D]. Chained from O via the D_OUT: d_out
  rank remapping syntax.
  4. FFN_down — Feed-forward down projection: [B,M,4D] → [B,M,D]. Chained from FFN_up.

  Renames: Each einsum has an explicit renames: {input: <tensor>} because the default rename pattern
   (Inputs & Intermediates if len(All)==3 else Inputs) fails for the first einsum where X is a pure
  Input (not an Intermediate). The default rename block only defines output and weight.

  ---
  4. gddr6aim_host.yaml (Mapping)

  An explicit mapping file was created but is not used in the final evaluation. The evaluate_mapping
   join algorithm failed on QKV <--> O because these einsums don't share a tensor at any common
  storage level (QKV produces tensor QKV, but O reads Attn_out — attention happens between them
  off-model). The evaluation script uses map_workload_to_arch instead, which generates and joins
  mappings automatically.

  ---
  5. evaluate_gddr6aim.py (Evaluation Script)

  Approach:
  - Loads the same workload YAML for both host CPU and AiM architectures
  - Uses map_workload_to_arch for both (auto-mapper)
  - Runs three configurations: host CPU, AiM full-speed (32ch/2GHz), AiM underclocked (4ch/0.25GHz)
  - Scales all results by MAC-count ratio to project to full GPT-3 13B dimensions
  - Reports per-layer and 40-layer latency, energy, and speedup vs CPU baseline

  Evaluation status: The mapper did not complete within the time budget, even with reduced rank
  sizes (D=64). The 4-einsum workload on a 5-level hierarchy (HostDRAM → FPGA_GPR → AiM_GDDR6 →
  GlobalBuffer → PU_MAC) with two spatial fanouts (32 channels × 16 banks = 512 PUs) creates a very
  large mapping search space. Further rank reduction or mapper tuning (max_fused_loops, time_limit)
  would be needed to get results.

  ---
  Summary of Simplifications

  ┌───────────────────────────────┬────────────────────────┬───────────────────────────────────┐
  │         Paper Feature         │     Simplification     │              Reason               │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Full GPT-3 13B dimensions     │ Scaled down to D=64,   │ Mapper too slow at full size      │
  │ (D=5120)                      │ results projected      │                                   │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Activation functions          │                        │ AccelForge has no built-in AF     │
  │ (sigmoid, tanh, GELU, etc.)   │ Omitted                │ model; would need a Toll or       │
  │                               │                        │ separate einsum                   │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Extended DRAM command set     │ Folded into PU_MAC     │ AccelForge models data movement,  │
  │ (ACT4/ACT16,                  │ latency/energy         │ not DRAM command scheduling       │
  │ MACSB/MAC4B/MACAB)            │                        │                                   │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Multi-bank activation         │ Modeled via 16-way     │ Fanout captures the parallel bank │
  │ parallelism                   │ BankArray spatial      │  access pattern                   │
  │                               │ fanout                 │                                   │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ DRAM timing (nCL=50,          │ Folded into AiM_GDDR6  │ AccelForge uses bandwidth-based   │
  │ nRCDRDMAC=56, nRP=32, etc.)   │ read/write latency     │ latency, not cycle-accurate DRAM  │
  │                               │                        │ timing                            │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Column/row-major tiling       │ Left to auto-mapper    │ Mapper explores tiling            │
  │ strategies                    │                        │ automatically                     │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Attention computation between │ Not modeled (O reads   │ Attention is not a linear layer;  │
  │  QKV and O                    │ fresh input)           │ paper focuses on offloaded linear │
  │                               │                        │  layers only                      │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ FPGA QDMA engine and          │ FPGA_GPR modeled as    │ AccelForge doesn't model DMA      │
  │ multicasting interconnect     │ simple buffer          │ engines or multicast              │
  ├───────────────────────────────┼────────────────────────┼───────────────────────────────────┤
  │ Shared Buffer, Instruction    │ Omitted                │ Only GlobalBuffer (per-bank) and  │
  │ Buffer power                  │                        │ DRAM power modeled                │
  └───────────────────────────────┴────────────────────────┴───────────────────────────────────┘

  Parameters Sourced from aim_simulator (vs. paper alone)

  ┌───────────────┬────────────────┬──────────────────────────────────────┬───────────────────┐
  │   Parameter   │  Paper Value   │         aim_simulator Value          │       Used        │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ Channels per  │ "2 Channels    │ CH_PER_DV = 32 (32 internal          │ 32 (simulator)    │
  │ device        │ per chip"      │ channels)                            │                   │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ DQ energy     │ Not specified  │ DQ_ENERGY = 5.5 pJ/bit               │ 5.5 pJ/bit        │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ PCIe energy   │ Not specified  │ PCIE_ENERGY = 4.4 pJ/bit             │ 4.4 pJ/bit        │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ DRAM read     │ Not specified  │ DRAM_POWER["RD"] = 438.15 mW         │ Used for energy   │
  │ power         │                │                                      │ derivation        │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ GB SRAM power │ Not specified  │ SRAM_POWER["GB"] = {STT: 0.067, RD:  │ 0.55/0.64 fJ/bit  │
  │               │                │ 0.279, WR: 0.325} mW                 │                   │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ Clock         │ "1 GHz"        │ 2 GHz (timing preset tCK_ps = 500)   │ 2 GHz (simulator) │
  │ frequency     │ (compute)      │                                      │                   │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ Banks per     │ Not specified  │ 4 BG × 4 banks = 16                  │ 16                │
  │ channel       │                │                                      │                   │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ Burst timing  │ Not specified  │ nBL=2, tBL=1.25 ns                   │ Used in energy    │
  │               │                │                                      │ calc              │
  ├───────────────┼────────────────┼──────────────────────────────────────┼───────────────────┤
  │ MAC command   │ Not specified  │ 1 cycle (from m_command_latencies)   │ Folded into       │
  │ latency       │                │                                      │ PU_MAC            │
  └───────────────┴────────────────┴──────────────────────────────────────┴───────────────────┘


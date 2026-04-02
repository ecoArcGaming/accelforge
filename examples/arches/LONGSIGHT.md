Please understand how this library, accelforge works by fully reading the documentation in the ./docs/source folder, and then the examples in ./examples/arches, ./example/workloads and ./example/mappings. Then, follow the instruction to produce three yaml files for the architecture, mapping, and workload of the following paper called longsight, make appropriate simplifications if applicable. 


1. System Architecture & Hardware Parameters
To simulate LongSight, the environment must combine a traditional host system (CPU/GPU) with the DReX compute-enabled Compute Express Link (CXL) memory expander.


A. Host System Details

CPU: 16 x Intel Xeon Max 9462 at 3.5 GHz (SMT off).

Host Memory: 8×128 GB DDR5-4400 DRAM (3.5 TFlop/s, 282 GB/s).

GPU: NVIDIA H100 SXM.

Compute capability: 989 TFlop/s.

Memory: 80 GB HBM3 with 3.35 TB/s bandwidth.

B. DReX CXL Memory Expander

DReX functions as a Type-3 CXL disaggregated memory device, exposing its internal DRAM and Memory-Mapped I/O (MMIO) to the host via standard load/store instructions.


Total Capacity: 512 GB of LPDDR5X memory.


Physical Layout: 8 LPDDR5X packages. Each package has 8 channels, and each channel contains 128 banks.

Near-Memory Accelerators (NMA): 8 NMAs total (one per LPDDR5X package). Total compute: 26.11 TFlop/s. NMA Bandwidth: 1.1 TB/s.


Processing-In-Memory Filtering Units (PFU): 8,192 PFUs total (one near each LPDDR bank). Total compute: 104.9 TB/s.


C. Timing & Latency Simulation Parameters

For cycle-accurate simulation (e.g., using DRAMSim3 and Ramulator), apply the following timing parameters:

PFU Bitmap Generation Latency: d×1.25 ns (where d is the dimension length).

Bitmap Read Latency (into NMA): 120.4 ns.

Address Generation Overhead (Memory Controller): 1,024 ns.

CXL Polling Overhead: Simulate CXL interface delays using a dual-socket Intel Xeon (5th Gen) platform to model memory copies and polling.

D. Area and Power Modeling

To model energy efficiency and chip area, use the following synthesized parameters (scaled to 7 nm technology, with a 10x area-efficiency penalty for DRAM logic):

NMA: Occupies 15.1 mm² of area and has a peak power of 1.072 W per NMA (at 16 nm).

PFU Area Overhead: 6.7% relative to the total DRAM die area.

LPDDR5X Package Peak Power: Up to 18.7 W.

Total DReX Peak Power: 158.2 W.

2. Algorithmic Configuration
LongSight uses a hybrid dense-sparse attention algorithm. The simulation must route short-range attention to the GPU and offload long-range retrieval to DReX.

A. Model Specifications

Llama-3-1B: 32 Query heads, 8 KV heads (Grouped Query Attention), Head Dimension = 64, 16 Layers, BF16 Quantization.

Llama-3-8B: 32 Query heads, 8 KV heads, Head Dimension = 128, 32 Layers, BF16 Quantization.

B. Attention Hyperparameters

Dense Sliding Window (W): 1,024 tokens processed directly on the GPU HBM.

Attention Sink: The first 16 tokens of the context are always retained as an attention sink for stability.

Top-k Retrieval (k): Set to 1,024 Values retrieved from DReX.

Sign-Concordance Filtering (SCF) Thresholds: Tune thresholds per KV head to achieve an average ~20x filtering ratio while keeping the perplexity degradation under 5%.

Iterative Quantization (ITQ): Implement a learned rotation matrix applied at runtime to queries and keys to balance sign-bit distributions before SCF.

C. Data Layout and Mapping

When writing the simulator's memory allocator, map the data following these rules:

PFU Parallelism: A PFU filters 128 Keys per cycle; thus, Sign Objects (1-bit quantized) for 128 Keys must be entirely contained within a single DRAM bank.

Key Interleaving: Full-precision Key Vectors must be strided across all 8 memory channels within a package to saturate LPDDR5X bandwidth during NMA dot-product calculations.

Context Slices: A Context Slice spans up to 128 banks in a channel, storing up to 131,072 Keys for a single head, layer, and user.

3. Workload Evaluation Setup
To evaluate the simulation and replicate the paper's results, utilize the appropriate datasets and testing phases.

A. Datasets

Project Gutenberg (PG): Segment complete, contiguous books into token sequences of the target context length.

Wikitext2 (Wiki2): Concatenate passages to meet the long-context requirements.

B. Evaluation Dimensions

Context Lengths: Sweep input context lengths from 32K tokens up to 1 Million tokens.

Metrics to Track:

Decode-phase Total Throughput: Measured in tokens/sec across all concurrent users.

Single-Token Latency: Measured in ms.

Accuracy/Perplexity: Ensure the perplexity remains within 5% of a full dense attention baseline.


4. Verification Targets
When your simulation is complete, run the workloads and verify the outputs against LongSight's reported benchmarks:

Filtering Efficiency: With ITQ enabled, the KV Cache filter ratio should improve by up to 6.4x (Llama-3-1B) and 46x (Llama-3-8B) compared to non-ITQ hybrid attention.

Long-Context Throughput: At the maximum context length supported by a single H100 GPU running dense attention, the LongSight simulation should demonstrate 8.1x to 9.6x higher throughput.


Long-Context Latency: At this same maximum length boundary, LongSight should exhibit 3.6x to 11.9x lower per-token latency than the 1-GPU baseline.

Capacity Limit Check: Validate that a single simulated GPU combined with a single 512GB DReX unit can successfully serve inference for 1 Million tokens.


To re-iterate, please understand how this library, accelforge works by fully reading the documentation in the ./docs/source folder, and then the examples in ./examples/arches, ./example/workloads and ./example/mappings. Then, follow the instruction to produce three yaml files for the architecture, mapping, and workload of the following paper called longsight, make appropriate simplifications if applicable. 

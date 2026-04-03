#!/usr/bin/env python3
"""
Evaluate the LongSight hybrid dense-sparse attention model.

Uses two separate specs (GPU and NMA) since accelforge evaluates
each hardware domain independently. Results are combined to report
total system energy, latency, and area.
"""

import pathlib
import accelforge as af

EXAMPLES = pathlib.Path(__file__).resolve().parent

# GPU path: projections + local attention + merge + output
GPU_ARCH = EXAMPLES / "arches" / "longsight_gpu.yaml"
GPU_WORK = EXAMPLES / "workloads" / "longsight_gpu.yaml"
GPU_MAP = EXAMPLES / "mappings" / "longsight_gpu.yaml"

# NMA path: remote attention on DReX (top-k filtered candidates)
NMA_ARCH = EXAMPLES / "arches" / "longsight_nma.yaml"
NMA_WORK = EXAMPLES / "workloads" / "longsight_nma.yaml"

DEFAULTS = {
    "BATCH_SIZE": 1,
    "N_CONTEXT": 131072,
    "W": 1024,
    "TOP_K": 1024,
}

N_LAYERS = 32  # Llama-3-8B has 32 layers


def print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def evaluate_gpu(params):
    """Evaluate GPU domain with explicit mapping."""
    print(f"  Loading GPU spec...")
    spec = af.Spec.from_yaml(GPU_ARCH, GPU_WORK, GPU_MAP, jinja_parse_data=params)
    print(f"  Evaluating GPU mapping...")
    return spec.evaluate_mapping()


def evaluate_nma(params):
    """Evaluate NMA domain using the mapper (auto-generated mapping)."""
    print(f"  Loading NMA spec...")
    spec = af.Spec.from_yaml(NMA_ARCH, NMA_WORK, jinja_parse_data=params)
    spec.mapper.metrics = af.Metrics.ENERGY | af.Metrics.LATENCY
    print(f"  Running NMA mapper...")
    return spec.map_workload_to_arch(print_progress=False)


def print_result(name, result):
    """Print energy/latency breakdown for one domain."""
    energy = result.energy()
    latency = result.latency()
    print(f"\n  [{name}] Total energy: {energy:.6e} J, latency: {latency:.6e} s")

    energy_by_comp = result.energy(per_component=True)
    print(f"  {'Component':<20} {'Energy (J)':>14}")
    print(f"  {'-' * 36}")
    for comp, e in sorted(energy_by_comp.items(), key=lambda x: -x[1]):
        print(f"  {comp:<20} {e:>14.6e}")

    energy_by_ein = result.energy(per_einsum=True)
    latency_by_ein = result.latency(per_einsum=True)
    print(f"\n  {'Einsum':<25} {'Energy (J)':>14} {'Latency (s)':>14}")
    print(f"  {'-' * 55}")
    for name_e in energy_by_ein:
        e = energy_by_ein[name_e]
        t = latency_by_ein.get(name_e, 0)
        print(f"  {name_e:<25} {e:>14.6e} {t:>14.6e}")


def evaluate(jinja_data: dict | None = None):
    """Run full LongSight evaluation across GPU and NMA domains."""
    params = {**DEFAULTS, **(jinja_data or {})}

    ctx = params["N_CONTEXT"]
    w = params["W"]
    top_k = params["TOP_K"]
    print(f"LongSight Evaluation: context={ctx}, window={w}, top_k={top_k}")
    print(f"Model: Llama-3-8B, {N_LAYERS} layers, GQA (32Q/8KV heads, dim=128)")

    # --- Component area ---
    print_separator("Component Area")
    for label, arch_path in [("GPU", GPU_ARCH), ("NMA", NMA_ARCH)]:
        spec = af.Spec.from_yaml(arch_path, jinja_parse_data=params)
        spec = spec.calculate_component_area_energy_latency_leak()
        for name, area in spec.arch.per_component_total_area.items():
            if area > 0:
                print(f"  {label}/{name}: {area * 1e6:.4f} mm²")

    # --- GPU Domain ---
    print_separator("GPU Domain (Projections + Local Attention + Output)")
    gpu_result = evaluate_gpu(params)
    print_result("GPU", gpu_result)

    # --- NMA Domain ---
    print_separator("NMA Domain (Remote Attention on DReX)")
    nma_result = evaluate_nma(params)
    print_result("NMA", nma_result)

    # --- Combined results ---
    gpu_energy = gpu_result.energy()
    gpu_latency = gpu_result.latency()
    nma_energy = nma_result.energy()
    nma_latency = nma_result.latency()

    layer_energy = gpu_energy + nma_energy
    layer_latency = gpu_latency + nma_latency

    total_energy = layer_energy * N_LAYERS
    total_latency = layer_latency * N_LAYERS

    print_separator("Combined Results (Single Layer)")
    print(f"  GPU energy:  {gpu_energy:.6e} J   latency: {gpu_latency * 1e6:.2f} us")
    print(f"  NMA energy:  {nma_energy:.6e} J   latency: {nma_latency * 1e6:.2f} us")
    print(f"  Layer total: {layer_energy:.6e} J   latency: {layer_latency * 1e6:.2f} us")

    print_separator(f"Full Model ({N_LAYERS} Layers)")
    throughput = 1.0 / total_latency if total_latency else float("inf")
    print(f"  Single-token latency : {total_latency * 1e3:.4f} ms")
    print(f"  Decode throughput    : {throughput:.1f} tokens/s")
    print(f"  Total energy/token   : {total_energy:.6e} J")
    print(f"  GPU fraction (energy): {gpu_energy / layer_energy * 100:.1f}%")
    print(f"  NMA fraction (energy): {nma_energy / layer_energy * 100:.1f}%")

    return gpu_result, nma_result


def context_sweep():
    """Sweep across context lengths and report latency scaling."""
    context_lengths = [32_768, 65_536, 131_072, 262_144, 524_288, 1_048_576]

    print_separator("Context Length Sweep (Full Model)")
    print(f"  {'Context':<12} {'Latency (ms)':>14} {'Throughput':>14} {'GPU (ms)':>12} {'NMA (ms)':>12}")
    print(f"  {'-' * 68}")

    for ctx in context_lengths:
        params = {**DEFAULTS, "N_CONTEXT": ctx}
        try:
            gpu_r = evaluate_gpu(params)
            nma_r = evaluate_nma(params)

            gpu_lat = gpu_r.latency() * N_LAYERS
            nma_lat = nma_r.latency() * N_LAYERS
            total_lat = gpu_lat + nma_lat
            tput = 1.0 / total_lat if total_lat else float("inf")

            print(f"  {ctx:<12,} {total_lat * 1e3:>14.4f} {tput:>12.1f} t/s"
                  f" {gpu_lat * 1e3:>12.4f} {nma_lat * 1e3:>12.4f}")
        except Exception as e:
            print(f"  {ctx:<12,} {'ERROR':>14}  {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate LongSight on accelforge")
    parser.add_argument("--context", type=int, default=131072,
                        help="Context length in tokens (default: 131072)")
    parser.add_argument("--window", type=int, default=1024,
                        help="Sliding window size (default: 1024)")
    parser.add_argument("--top-k", type=int, default=1024,
                        help="Top-k retrieved keys (default: 1024)")
    parser.add_argument("--batch", type=int, default=1,
                        help="Batch size (default: 1)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run context-length sweep")
    args = parser.parse_args()

    if args.sweep:
        context_sweep()
    else:
        evaluate(jinja_data={
            "BATCH_SIZE": args.batch,
            "N_CONTEXT": args.context,
            "W": args.window,
            "TOP_K": args.top_k,
        })

#!/usr/bin/env python3
"""
Evaluate GDDR6-AiM vs CPU baseline for GPT-3 13B linear layers.

Uses small rank sizes for fast mapper execution, then scales results
to full GPT-3 13B dimensions (d=5120, d_ff=20480).
"""

import pathlib
import accelforge as af

EXAMPLES = pathlib.Path(__file__).resolve().parent

HOST_ARCH = EXAMPLES / "arches" / "gddr6aim_host.yaml"
AIM_ARCH = EXAMPLES / "arches" / "gddr6aim_aim.yaml"
WORKLOAD = EXAMPLES / "workloads" / "gddr6aim_gpt3_13B.yaml"

N_LAYERS = 40  # GPT-3 13B

# Small sizes for fast mapper; actual sizes for scaling
MODEL_D = 64
MODEL_D_QKV = 192
MODEL_D_FF = 256
ACTUAL_D = 5120
ACTUAL_D_QKV = 15360
ACTUAL_D_FF = 20480

# Compute scale factor: ratio of actual MACs to model MACs
# QKV: D*D_QKV, O: D*D, FFN_up: D*D_FF, FFN_down: D_FF*D
ACTUAL_MACS = ACTUAL_D * ACTUAL_D_QKV + ACTUAL_D * ACTUAL_D + ACTUAL_D * ACTUAL_D_FF + ACTUAL_D_FF * ACTUAL_D
MODEL_MACS = MODEL_D * MODEL_D_QKV + MODEL_D * MODEL_D + MODEL_D * MODEL_D_FF + MODEL_D_FF * MODEL_D
SCALE = ACTUAL_MACS / MODEL_MACS


def print_separator(title: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}")


def print_result(name, result, scale=1.0):
    energy = result.energy() * scale
    latency = result.latency() * scale
    print(f"\n  [{name}] Energy: {energy:.6e} J, Latency: {latency:.6e} s")

    energy_by_comp = result.energy(per_component=True)
    print(f"  {'Component':<20} {'Energy (J)':>14}")
    print(f"  {'-' * 36}")
    for comp, e in sorted(energy_by_comp.items(), key=lambda x: -x[1]):
        print(f"  {comp:<20} {e * scale:>14.6e}")

    energy_by_ein = result.energy(per_einsum=True)
    latency_by_ein = result.latency(per_einsum=True)
    print(f"\n  {'Einsum':<20} {'Energy (J)':>14} {'Latency (s)':>14}")
    print(f"  {'-' * 50}")
    for ein in energy_by_ein:
        print(f"  {ein:<20} {energy_by_ein[ein] * scale:>14.6e} {latency_by_ein.get(ein, 0) * scale:>14.6e}")


def run_mapper(arch, params):
    spec = af.Spec.from_yaml(arch, WORKLOAD, jinja_parse_data=params)
    spec.mapper.metrics = af.Metrics.ENERGY | af.Metrics.LATENCY
    return spec.map_workload_to_arch(print_progress=True)


def evaluate():
    base_params = {
        "BATCH_SIZE": 1,
        "D": MODEL_D,
        "D_QKV": MODEL_D_QKV,
        "D_FF": MODEL_D_FF,
    }

    print("GDDR6-AiM Evaluation: GPT-3 13B Linear Layers")
    print(f"Model dims: D={MODEL_D}, D_QKV={MODEL_D_QKV}, D_FF={MODEL_D_FF}")
    print(f"Scaled to actual: D={ACTUAL_D}, D_QKV={ACTUAL_D_QKV}, D_FF={ACTUAL_D_FF}")
    print(f"Scale factor: {SCALE:.1f}x")

    # --- Component area ---
    print_separator("Component Area")
    for label, arch_path in [("Host", HOST_ARCH), ("AiM", AIM_ARCH)]:
        spec = af.Spec.from_yaml(arch_path, jinja_parse_data=base_params)
        spec = spec.calculate_component_area_energy_latency_leak()
        for name, area in spec.arch.per_component_total_area.items():
            if area > 0:
                print(f"  {label}/{name}: {area * 1e6:.4f} mm^2")

    # --- Host CPU ---
    print_separator("Host CPU Baseline (Xeon Gold 6230 + DDR4-3200)")
    print("  Running host mapper...")
    host_result = run_mapper(HOST_ARCH, base_params)
    print_result("Host CPU", host_result, SCALE)

    # --- AiM full speed ---
    print_separator("GDDR6-AiM (32ch, 512 PUs, full speed 16 Gb/s/pin)")
    print("  Running AiM mapper...")
    aim_full = run_mapper(AIM_ARCH, {**base_params, "N_CHANNELS": 32, "FREQ_GHZ": 2.0})
    print_result("AiM Full", aim_full, SCALE)

    # --- AiM underclocked (2 Gb/s/pin → 0.25 GHz effective) ---
    print_separator("GDDR6-AiM (32ch, 512 PUs, underclocked 2 Gb/s/pin)")
    print("  Running AiM mapper (underclocked)...")
    # At 2 Gb/s/pin: per-channel BW = 2*16*2/8 = 8 GB/s... but per pin = 2 Gb/s
    # vs full speed 16 Gb/s: bandwidth scales by 2/16 = 0.125x
    # Compute clock also scales: 0.25 GHz
    aim_slow = run_mapper(AIM_ARCH, {**base_params, "N_CHANNELS": 4, "FREQ_GHZ": 0.25})
    print_result("AiM Slow", aim_slow, SCALE)

    # --- Summary ---
    host_lat = host_result.latency() * SCALE
    aim_full_lat = aim_full.latency() * SCALE
    aim_slow_lat = aim_slow.latency() * SCALE

    print_separator("Per-Layer Speedup Summary (Scaled to GPT-3 13B)")
    print(f"  Host CPU latency:         {host_lat * 1e6:>12.2f} us")
    print(f"  AiM (underclocked):       {aim_slow_lat * 1e6:>12.2f} us"
          f"  -> {host_lat / aim_slow_lat:>6.2f}x speedup")
    print(f"  AiM (full speed):         {aim_full_lat * 1e6:>12.2f} us"
          f"  -> {host_lat / aim_full_lat:>6.2f}x speedup")

    total_host = host_lat * N_LAYERS
    total_aim_full = aim_full_lat * N_LAYERS
    total_aim_slow = aim_slow_lat * N_LAYERS

    print_separator(f"Full Model ({N_LAYERS} Layers)")
    print(f"  Host CPU:          {total_host * 1e3:>10.4f} ms"
          f"   ({1 / total_host:>8.1f} tokens/s)")
    print(f"  AiM (underclk):   {total_aim_slow * 1e3:>10.4f} ms"
          f"   ({1 / total_aim_slow:>8.1f} tokens/s)"
          f"   {total_host / total_aim_slow:>6.2f}x")
    print(f"  AiM (full speed): {total_aim_full * 1e3:>10.4f} ms"
          f"   ({1 / total_aim_full:>8.1f} tokens/s)"
          f"   {total_host / total_aim_full:>6.2f}x")

    print(f"\n  Paper targets: 6.73x (underclocked), 16.64-18.05x (full speed)")


if __name__ == "__main__":
    evaluate()
